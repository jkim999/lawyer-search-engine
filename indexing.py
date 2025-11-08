import csv
import re
import sqlite3
from typing import Dict, List, Optional, Tuple, Any
from tqdm import tqdm
from scraping_utils import parse_page, parse_text
from database import init_database, upsert_lawyer, create_indexes, load_school_aliases, get_school_normalized
from embedding_generator import extract_experience_text, store_embedding
from llm_utils import get_embedding, EMBEDDING_MODEL_SMALL


def degree_tokenizer(education_line: str) -> Dict[str, Any]:
    """
    Parse education entry to extract degree, school, and honors.

    Note: Davis Polk website does not publish graduation years (common practice
    to avoid age discrimination), so year is not extracted.

    Args:
        education_line: Raw education line (e.g., "J.D., Yale Law School" or "LL.M., Tax, New York University School of Law")

    Returns:
        Dictionary with degree_type, school_name, honors, is_law_degree
    """
    result = {
        'degree_type': None,
        'school_name': None,
        'honors': None,
        'is_law_degree': 0
    }

    # Common degree patterns
    law_degrees = ['J.D.', 'LL.M.', 'LL.B.', 'J.D', 'LL.M', 'LL.B']
    undergrad_degrees = ['B.A.', 'B.S.', 'A.B.', 'B.A', 'B.S', 'A.B']
    grad_degrees = ['M.A.', 'M.S.', 'MBA', 'Ph.D.', 'M.A', 'M.S', 'Ph.D']

    all_degrees = law_degrees + undergrad_degrees + grad_degrees

    # Find degree type
    degree_type = None
    for degree in all_degrees:
        if degree in education_line:
            degree_type = degree.strip('.')
            result['degree_type'] = degree_type
            if degree in law_degrees:
                result['is_law_degree'] = 1
            break

    # Extract school name - look for University, College, School, Institute
    # Remove degree from the line first
    cleaned = education_line
    if degree_type:
        cleaned = cleaned.replace(degree_type + '.', '').replace(degree_type, '')
    
    # Remove common separators and extra words
    cleaned = re.sub(r'^[,\s]+', '', cleaned)  # Remove leading commas/spaces
    cleaned = re.sub(r'[,\s]+$', '', cleaned)  # Remove trailing commas/spaces
    
    # Look for school indicators
    school_patterns = [
        r'([A-Z][^,]+(?:University|College|School|Institute)[^,]*?)',
        r'([A-Z][^,]+(?:Law School|Law)[^,]*?)',
    ]
    
    school_name = None
    for pattern in school_patterns:
        match = re.search(pattern, cleaned)
        if match:
            school_name = match.group(1).strip()
            # Clean up extra commas and spaces
            school_name = re.sub(r'[,\s]+', ' ', school_name).strip()
            break
    
    # If no pattern match, try to extract meaningful text
    if not school_name:
        # Split by comma and take the longest meaningful part
        parts = [p.strip() for p in cleaned.split(',')]
        parts = [p for p in parts if len(p) > 5 and not p.lower() in ['tax', 'economics', 'law']]
        if parts:
            school_name = parts[0]
    
    if school_name:
        result['school_name'] = school_name
    
    # Extract honors (common patterns: magna cum laude, summa cum laude, etc.)
    honors_patterns = [
        r'magna cum laude',
        r'summa cum laude',
        r'cum laude',
        r'with honors',
        r'with distinction',
    ]
    
    for pattern in honors_patterns:
        if re.search(pattern, education_line, re.IGNORECASE):
            result['honors'] = re.search(pattern, education_line, re.IGNORECASE).group(0)
            break
    
    return result


def extract_education_info(parsed_data: Dict[str, Any], conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """
    Extract education information from parsed data using degree tokenizer.
    
    Args:
        parsed_data: Parsed lawyer data from parse_text()
        conn: Database connection for school normalization
        
    Returns:
        List of education dictionaries
    """
    educations = []
    
    if not parsed_data.get('school'):
        return educations
    
    school_entries = parsed_data['school']
    if isinstance(school_entries, str):
        school_entries = [school_entries]
    
    for entry in school_entries:
        if not entry:
            continue
        
        # Use tokenizer to parse
        edu_info = degree_tokenizer(entry)
        
        # Normalize school name
        if edu_info.get('school_name'):
            normalized = get_school_normalized(conn, edu_info['school_name'])
            edu_info['school_normalized'] = normalized
        else:
            edu_info['school_normalized'] = None
        
        # Store full text
        edu_info['full_text'] = entry
        
        educations.append(edu_info)
    
    return educations


def normalize_school_name(conn: sqlite3.Connection, school_name: str) -> str:
    """
    Normalize school name using alias mapping.
    
    Args:
        conn: Database connection
        school_name: School name to normalize
        
    Returns:
        Normalized school name
    """
    return get_school_normalized(conn, school_name)


def scrape_and_cache_lawyers(csv_file: str = 'lawyers.csv',
                              db_path: str = 'lawyers.db',
                              store_html: bool = False,
                              generate_embeddings: bool = True,
                              force_rescrape: bool = False) -> int:
    """
    Scrape all lawyer profiles, parse, and store in SQLite database.
    Optionally generates embeddings during scraping for efficiency.

    Args:
        csv_file: Path to lawyers.csv file
        db_path: Path to SQLite database
        store_html: Whether to store raw HTML (gzipped)
        generate_embeddings: Whether to generate embeddings during scraping (recommended)
        force_rescrape: Whether to re-scrape even if lawyer exists

    Returns:
        Number of lawyers processed
    """
    # Initialize database
    conn = init_database(db_path)
    create_indexes(conn)
    load_school_aliases(conn)
    
    # Load URLs from CSV
    urls = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        for line in f:
            url = line.strip()
            if url and url.startswith('http'):
                urls.append(url)
    
    print(f"Found {len(urls)} lawyer URLs")
    
    # Check which lawyers already exist
    cursor = conn.cursor()
    existing_urls = set()
    if not force_rescrape:
        cursor.execute('SELECT url FROM lawyers')
        existing_urls = {row['url'] for row in cursor.fetchall()}
        print(f"Found {len(existing_urls)} existing lawyers in database")
    
    # Process each URL
    processed = 0
    skipped = 0
    errors = 0
    failed_urls = []
    
    for url in tqdm(urls, desc="Scraping lawyers"):
        # Skip if already exists and not forcing rescrape
        if url in existing_urls and not force_rescrape:
            skipped += 1
            continue
        
        try:
            # Scrape and parse
            raw_html = parse_page(url)
            parsed_data = parse_text(raw_html)
            
            # Store raw HTML if requested
            html_bytes = raw_html.encode('utf-8') if store_html else None
            
            # Upsert lawyer basic info
            lawyer_id = upsert_lawyer(conn, url, parsed_data, html_bytes, store_html)
            
            if not lawyer_id:
                errors += 1
                failed_urls.append((url, "Failed to get lawyer_id from database"))
                continue
            
            # Insert education entries
            educations = extract_education_info(parsed_data, conn)
            cursor = conn.cursor()
            
            for edu in educations:
                cursor.execute('''
                    INSERT INTO educations
                    (lawyer_id, degree_type, school_name, school_normalized,
                     is_law_degree, honors, full_text)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (lawyer_id,
                      edu.get('degree_type'),
                      edu.get('school_name'),
                      edu.get('school_normalized'),
                      edu.get('is_law_degree', 0),
                      edu.get('honors'),
                      edu.get('full_text')))

            # Generate embedding if requested (while HTML is already in memory)
            if generate_embeddings:
                try:
                    experience_text = extract_experience_text(raw_html)
                    if experience_text:
                        # Generate embedding for experience section
                        embedding = get_embedding([experience_text], size=EMBEDDING_MODEL_SMALL)[0]
                        # Store embedding with full parsed text for LLM filtering
                        store_embedding(conn, lawyer_id, experience_text, embedding, raw_html)
                except Exception as e:
                    # Don't fail the whole scrape if embedding generation fails
                    print(f"\nWarning: Failed to generate embedding for lawyer {lawyer_id}: {e}")

            conn.commit()
            processed += 1
            
        except Exception as e:
            # Rollback any partial transaction
            conn.rollback()
            error_msg = f"Error processing {url}: {e}"
            print(f"\n{error_msg}")
            errors += 1
            failed_urls.append((url, str(e)))
            continue
    
    conn.close()
    
    print(f"\nScraping complete:")
    print(f"  Processed: {processed}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")
    
    # Save failed URLs to file for later retry
    if failed_urls:
        failed_file = 'failed_urls.txt'
        with open(failed_file, 'w', encoding='utf-8') as f:
            f.write("# Failed URLs - can be retried by adding to lawyers.csv\n")
            for url, error in failed_urls:
                f.write(f"{url}\n")
        print(f"  Failed URLs saved to: {failed_file}")
    
    return processed


def cleanup_bad_names(db_path: str = 'lawyers.db'):
    """
    Clean up lawyers with invalid names (like "Print this page") by re-parsing or using email.
    
    Args:
        db_path: Path to SQLite database
    """
    conn = init_database(db_path)
    # Ensure triggers are set up correctly (fixes broken FTS5 update trigger)
    create_indexes(conn)
    cursor = conn.cursor()
    
    # Get all lawyers with potentially bad names
    name_blacklist = {
        'print this page', 'download address card', 'back to top', 'back to',
        'lawyers', 'capabilities', 'insights', 'experience', 'education',
        'skip to main content', 'top of page', 'davis polk'
    }
    
    cursor.execute('SELECT id, url, name, email FROM lawyers')
    lawyers = cursor.fetchall()
    
    fixed = 0
    for lawyer in lawyers:
        lawyer_id, url, name, email = lawyer['id'], lawyer['url'], lawyer['name'], lawyer['email']
        
        if not name:
            continue
        
        name_lower = name.lower().strip()
        
        # Check if name is in blacklist
        if name_lower in name_blacklist or any(blacklisted in name_lower for blacklisted in name_blacklist):
            # Try to fix from email
            new_name = None
            if email and '@' in email:
                email_local = email.split('@')[0]
                potential_name = email_local.replace('.', ' ').replace('-', ' ').title()
                if len(potential_name.split()) >= 2 and len(potential_name) < 50:
                    new_name = potential_name
            
            # If email doesn't work, try to re-parse from URL or set to None
            if not new_name:
                # Extract from URL slug (e.g., /lawyers/alon-gurfinkel -> Alon Gurfinkel)
                if '/lawyers/' in url:
                    slug = url.split('/lawyers/')[-1].split('?')[0]
                    potential_name = slug.replace('-', ' ').title()
                    if len(potential_name.split()) >= 2 and len(potential_name) < 50:
                        new_name = potential_name
            
            if new_name:
                # Update name
                name_parts = new_name.split(maxsplit=1)
                first_name = name_parts[0] if name_parts else ''
                last_name = name_parts[1] if len(name_parts) > 1 else ''
                
                # Update lawyers table - the fixed trigger will automatically update FTS5
                cursor.execute('''
                    UPDATE lawyers 
                    SET name = ?, first_name = ?, last_name = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (new_name, first_name, last_name, lawyer_id))
                
                fixed += 1
                print(f"Fixed lawyer {lawyer_id}: '{name}' -> '{new_name}'")
            else:
                print(f"Could not fix lawyer {lawyer_id}: '{name}' (URL: {url})")
    
    conn.commit()
    conn.close()
    
    print(f"\nFixed {fixed} lawyers with invalid names.")


if __name__ == '__main__':
    # For testing
    import sys
    store_html = '--store-html' in sys.argv
    force = '--force' in sys.argv
    cleanup = '--cleanup' in sys.argv
    
    if cleanup:
        cleanup_bad_names()
    else:
        scrape_and_cache_lawyers(store_html=store_html, force_rescrape=force)

