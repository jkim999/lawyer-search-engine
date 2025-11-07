"""
Module for generating and storing embeddings for lawyer experience sections.
"""

import sqlite3
import numpy as np
import pickle
from typing import List, Tuple, Optional
from tqdm import tqdm
from database import init_database
from scraping_utils import parse_page, parse_text
from llm_utils import get_embedding, EMBEDDING_MODEL_SMALL
import re


def extract_experience_text(scraped_content: str) -> Optional[str]:
    """
    Extract the experience section from scraped lawyer profile content.
    
    Args:
        scraped_content: Raw scraped HTML/text content
        
    Returns:
        Experience text if found, None otherwise
    """
    lines = scraped_content.split('\n')
    cleaned_lines = [line.strip() for line in lines if line.strip()]
    
    experience_start = False
    experience_lines = []
    
    # Sections that indicate end of experience
    stop_sections = [
        'Education', 'Languages', 'Qualifications', 'Prior experience',
        'Clerkship', 'Back to', 'Download', 'Print', 'Offices',
        'News', 'Contact', 'Careers', 'Alumni', 'Connect', 'Archive'
    ]
    
    # Navigation items that indicate we're still in the header/nav area
    nav_indicators = [
        'Skip to main content', 'Top of page', 'Davis Polk',
        'Lawyers', 'Capabilities', 'Insights', 'Client Updates',
        'Webinars & CLE Programs', 'Resource Centers', 'Offices',
        'About Us', 'Overview', 'Business Services Leadership'
    ]
    
    for i, line in enumerate(cleaned_lines):
        # Look for Experience section header
        if line == 'Experience' or (line.startswith('Experience') and len(line) < 20):
            # Check if this is likely the actual experience section (not navigation)
            # The real experience section usually comes after the lawyer's name and basic info
            # and is followed by actual content, not navigation items
            is_nav = False
            if i < len(cleaned_lines) - 1:
                next_line = cleaned_lines[i + 1] if i + 1 < len(cleaned_lines) else ""
                # If next line is a navigation item, this is probably nav
                if any(nav in next_line for nav in nav_indicators):
                    is_nav = True
                # If previous lines contain nav indicators, this is probably nav
                if i > 0 and any(nav in cleaned_lines[max(0, i-5):i] for nav in nav_indicators):
                    is_nav = True
            
            if not is_nav:
                experience_start = True
                continue
            
        if experience_start:
            # Stop at next major section
            if any(section in line for section in stop_sections):
                # But allow "Prior experience" as it's part of experience
                if line != 'Prior experience':
                    break
                
            # Skip empty lines and navigation elements
            if line and not any(skip in line.lower() for skip in 
                              ['view more experience', 'see more experience', 'download', 'print', 'back to',
                               'address card', 'skip to', 'see all results']):
                experience_lines.append(line)
    
    if experience_lines:
        # Join lines and clean up
        experience_text = ' '.join(experience_lines)
        # Remove excessive whitespace
        experience_text = re.sub(r'\s+', ' ', experience_text).strip()
        # Only return if we have substantial content (more than just a few words)
        if len(experience_text) > 50:
            return experience_text
    
    return None


def store_embedding(conn: sqlite3.Connection, lawyer_id: int, 
                   content: str, embedding: List[float]) -> None:
    """
    Store an embedding in the database.
    
    Args:
        conn: Database connection
        lawyer_id: ID of the lawyer
        content: The text content that was embedded
        embedding: The embedding vector
    """
    cursor = conn.cursor()
    
    # Convert embedding to binary format
    embedding_blob = pickle.dumps(np.array(embedding, dtype=np.float32))
    
    # Delete existing embedding if any
    cursor.execute('DELETE FROM experience_embeddings WHERE lawyer_id = ?', (lawyer_id,))
    
    # Insert new embedding
    cursor.execute('''
        INSERT INTO experience_embeddings (lawyer_id, content, embedding)
        VALUES (?, ?, ?)
    ''', (lawyer_id, content, embedding_blob))
    
    conn.commit()


def generate_embeddings_for_all_lawyers(db_path: str = 'lawyers.db',
                                       batch_size: int = 10) -> Tuple[int, int]:
    """
    Generate and store embeddings for all lawyers' experience sections.
    
    Args:
        db_path: Path to the database
        batch_size: Number of embeddings to generate in one API call
        
    Returns:
        Tuple of (processed_count, error_count)
    """
    conn = init_database(db_path)
    cursor = conn.cursor()
    
    # Get all lawyers
    cursor.execute('SELECT id, url FROM lawyers ORDER BY id')
    lawyers = cursor.fetchall()
    
    print(f"Generating embeddings for {len(lawyers)} lawyers...")
    
    processed = 0
    errors = 0
    lawyers_with_experience = 0
    
    # Process in batches for efficiency
    for i in tqdm(range(0, len(lawyers), batch_size), desc="Processing batches"):
        batch = lawyers[i:i + batch_size]
        texts_to_embed = []
        lawyer_data = []
        
        # Collect experience texts for this batch
        for lawyer in batch:
            lawyer_id = lawyer['id']
            url = lawyer['url']
            
            try:
                # Scrape and extract experience
                raw_html = parse_page(url)
                experience_text = extract_experience_text(raw_html)
                
                if experience_text:
                    texts_to_embed.append(experience_text)
                    lawyer_data.append((lawyer_id, experience_text))
                    lawyers_with_experience += 1
                
                processed += 1
                
            except Exception as e:
                errors += 1
                print(f"\nError processing lawyer {lawyer_id}: {e}")
                continue
        
        # Generate embeddings for this batch
        if texts_to_embed:
            try:
                embeddings = get_embedding(texts_to_embed, size=EMBEDDING_MODEL_SMALL)
                
                # Store embeddings
                for (lawyer_id, content), embedding in zip(lawyer_data, embeddings):
                    store_embedding(conn, lawyer_id, content, embedding)
                    
            except Exception as e:
                print(f"\nError generating embeddings for batch: {e}")
                errors += len(texts_to_embed)
    
    conn.close()
    
    print(f"\nEmbedding generation complete:")
    print(f"  Processed: {processed}")
    print(f"  Errors: {errors}")
    print(f"  Lawyers with experience data: {lawyers_with_experience}")
    
    return processed, errors


def load_embedding(conn: sqlite3.Connection, lawyer_id: int) -> Optional[np.ndarray]:
    """
    Load an embedding from the database.
    
    Args:
        conn: Database connection
        lawyer_id: ID of the lawyer
        
    Returns:
        Embedding as numpy array, or None if not found
    """
    cursor = conn.cursor()
    cursor.execute(
        'SELECT embedding FROM experience_embeddings WHERE lawyer_id = ?',
        (lawyer_id,)
    )
    
    row = cursor.fetchone()
    if row and row['embedding']:
        return pickle.loads(row['embedding'])
    
    return None


if __name__ == '__main__':
    # Test with a small sample
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--full':
        # Generate embeddings for all lawyers
        generate_embeddings_for_all_lawyers()
    else:
        # Test with just a few lawyers
        conn = init_database()
        cursor = conn.cursor()
        
        # Get a few sample lawyers
        cursor.execute('SELECT id, url, name FROM lawyers LIMIT 5')
        samples = cursor.fetchall()
        
        print("Testing embedding generation with sample lawyers:")
        print("-" * 60)
        
        for lawyer in samples:
            try:
                # Extract experience
                raw_html = parse_page(lawyer['url'])
                experience = extract_experience_text(raw_html)
                
                if experience:
                    print(f"\n{lawyer['name']}:")
                    print(f"Experience preview: {experience[:200]}...")
                    
                    # Generate embedding
                    embedding = get_embedding([experience])[0]
                    print(f"Embedding shape: {len(embedding)}")
                    
                    # Store it
                    store_embedding(conn, lawyer['id'], experience, embedding)
                    
                    # Load it back
                    loaded = load_embedding(conn, lawyer['id'])
                    print(f"Successfully stored and loaded: {loaded is not None}")
                else:
                    print(f"\n{lawyer['name']}: No experience section found")
                    
            except Exception as e:
                print(f"\n{lawyer['name']}: Error - {e}")
        
        conn.close()
