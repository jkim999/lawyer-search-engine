import requests
import re
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Union

# Official Davis Polk practice areas
VALID_PRACTICES = {
    'Antitrust & Competition',
    'Capital Markets',
    'Civil Litigation',
    'Corporate',
    'Corporate Governance',
    'Data Privacy & Cybersecurity',
    'Derivatives & Structured Products',
    'Environmental',
    'Executive Compensation',
    'Finance',
    'Financial Institutions',
    'Investment Management',
    'IP & Commercial Transactions',
    'IP Litigation',
    'Liability Management & Special Opportunities',
    'Litigation',
    'Mergers & Acquisitions',
    'Private Credit',
    'Private Equity',
    'Private Wealth',
    'Public Company Advisory',
    'Real Estate',
    'Restructuring',
    'Shareholder Activism Defense',
    'Sponsor Finance',
    'Tax',
    'White Collar Defense & Investigations',
}

# Official Davis Polk offices
VALID_OFFICES = {
    'New York',
    'Northern California',
    'Washington DC',
    'São Paulo',
    'London',
    'Brussels',
    'Madrid',
    'Hong Kong',
    'Beijing',
    'Tokyo',
}

# Official Davis Polk industries
VALID_INDUSTRIES = {
    'Artificial Intelligence',
    'Cleantech',
    'Consumer Products & Retail',
    'Data Centers & Digital Infrastructure',
    'Energy, Power & Infrastructure',
    'Fintech & Cryptocurrency',
    'Healthcare & Life Sciences',
    'Industrials',
    'Sports',
    'Tech, Media & Telecom',
}

# Official Davis Polk regions (only in capabilities section)
VALID_REGIONS = {
    'Asia',
    'China',
    'Japan',
    'Europe',
    'Latin America',
    'Israel',
}


def parse_page(url: str) -> str:
    """
    Parse the content of a web page and extract its text.

    Args:
        url (str): The URL of the web page to parse.

    Returns:
        str: The extracted text content of the web page.

    Raises:
        requests.RequestException: If there's an error fetching the page.
    """
    try:
        response = requests.get(url.strip())
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'lxml')
        return soup.body.get_text()
    except requests.RequestException as e:
        raise requests.RequestException(f"Error fetching the page: {e}")

def extract_from_valid_set(text: str, valid_set: set) -> List[str]:
    """
    Extract all items from a valid set that appear in the text.
    Searches the entire text for exact matches (case-sensitive).

    Args:
        text: The text to search
        valid_set: Set of valid values to look for

    Returns:
        List of found values
    """
    found = []
    for item in valid_set:
        if item in text:
            found.append(item)
    return found


def parse_text(scraped_content: str) -> Dict[str, Union[str, List[str], None]]:
    """
    Parse Davis Polk lawyer profile information from scraped content.
    
    Parameters:
    -----------
    scraped_content : str
        The raw HTML or text content scraped from a Davis Polk lawyer profile page
        
    Returns:
    --------
    dict : Dictionary containing parsed information with the following keys:
        - name: Full name of the lawyer
        - email: Email address
        - phone: Phone number
        - office_location: Office location/city
        - practice_type: Type of legal practice (e.g., Tax, Corporate, Litigation)
        - industry: Industries they serve
        - region: List of regions from ['Asia', 'China', 'Japan', 'Europe', 'Latin America', 'Israel'] 
                  if found in Capabilities section, otherwise None
        - title: Professional title (e.g., Partner, Counsel, Associate)
        - school: Educational institutions attended
        - clerkship: Clerkship information if available
        - language: Languages spoken (if mentioned)
    """
    
    # Initialize result dictionary with None values
    result = {
        'name': None,
        'email': None,
        'phone': None,
        'office_location': None,
        'practice_type': [],
        'industry': [],
        'region': None,
        'title': None,
        'school': [],
        'clerkship': None,
        'language': []
    }
    
    # Clean the content
    content = scraped_content.strip()
    
    # Try to parse as HTML first, if that fails, treat as plain text
    try:
        soup = BeautifulSoup(content, 'html.parser')
        text_content = soup.get_text()
    except:
        text_content = content
    
    # Split into lines for line-by-line processing
    lines = text_content.split('\n')
    cleaned_lines = [line.strip() for line in lines if line.strip()]
    
    # Davis Polk specific title keywords
    # Sorted by length (longest first) to match more specific titles before general ones
    title_keywords = [
        'Managing Partner',
        'Senior Partner',
        'Senior Counsel',
        'Of Counsel',
        'Partner',
        'Counsel',
        'Associate',
        'Co-Head',
        'Head',
    ]
    
    # Blacklist of text that should never be considered a name
    name_blacklist = {
        'print this page', 'download address card', 'back to top', 'back to',
        'lawyers', 'capabilities', 'insights', 'experience', 'education',
        'languages', 'clerkship', 'qualifications', 'prior experience',
        'about us', 'offices', 'careers', 'contact', 'search', 'clear',
        'skip to main content', 'top of page', 'receive insights',
        'subscribe', 'explore', 'connect', 'legal', 'privacy notice',
        'cookie policy', 'cookie settings', 'attorney advertising',
        'prior results do not guarantee', 'davis polk', 'davis polk & wardwell'
    }
    
    def is_valid_name(name: str) -> bool:
        """Check if a string is a valid lawyer name."""
        if not name:
            return False
        
        name_lower = name.lower().strip()
        
        # Check blacklist
        if name_lower in name_blacklist:
            return False
        
        # Check if it contains any blacklisted phrases
        for blacklisted in name_blacklist:
            if blacklisted in name_lower:
                return False
        
        # Must be proper name format: First Last or First Middle Last
        # Should start with capital letter, contain letters, spaces, periods (for initials)
        if not re.match(r'^[A-Z][a-zA-Z\.\s]+$', name):
            return False
        
        # Should not be too short or too long
        if len(name) < 3 or len(name) > 50:
            return False
        
        # Should not contain special characters that indicate it's not a name
        if any(char in name for char in ['@', '+', '(', ')', '/', ':', ';', '=', '?']):
            return False
        
        # Should have at least 2 words (first and last name)
        words = name.split()
        if len(words) < 2:
            return False
        
        # Each word should be at least 2 characters (except single-letter middle initials)
        for word in words:
            if len(word) > 1 and not word.replace('.', '').isalpha():
                return False
        
        return True
    
    # Parse Name and Title (Davis Polk specific pattern)
    # Name typically appears before title in Davis Polk profiles
    for i, line in enumerate(cleaned_lines):
        if line in title_keywords or any(keyword in line for keyword in title_keywords):
            # Set title
            if not result['title']:
                for keyword in title_keywords:
                    if keyword in line:
                        result['title'] = keyword
                        break
            
            # Check previous lines for name
            if i > 0 and not result['name']:
                potential_name = cleaned_lines[i-1]
                if is_valid_name(potential_name):
                    result['name'] = potential_name
    
    # Fallback name parsing using pattern matching
    # Look for name pattern near email or phone (more reliable indicators)
    if not result['name']:
        # First try to find name near email (most reliable)
        email_pattern = r'[a-zA-Z0-9._%+-]+@davispolk\.com'
        for i, line in enumerate(cleaned_lines):
            if re.search(email_pattern, line, re.IGNORECASE):
                # Check lines before email (name is usually above email)
                for j in range(max(0, i-5), i):
                    if is_valid_name(cleaned_lines[j]):
                        result['name'] = cleaned_lines[j]
                        break
                if result['name']:
                    break
        
        # If still not found, try pattern matching in first 30 lines, but with stricter validation
        if not result['name']:
            name_pattern = r'([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?(?:\s+[A-Z][a-z]+)+)'
            for line in cleaned_lines[:30]:
                name_match = re.search(r'^' + name_pattern + r'$', line)
                if name_match:
                    potential_name = name_match.group(1).strip()
                    if is_valid_name(potential_name):
                        result['name'] = potential_name
                        break
    
    # Parse Email
    email_pattern = r'[a-zA-Z0-9._%+-]+@davispolk\.com'
    email_match = re.search(email_pattern, text_content)
    if email_match:
        result['email'] = email_match.group(0).lower()
    
    # Parse Phone Number
    phone_patterns = [
        r'\+1\s*\d{3}\s*\d{3}\s*\d{4}',  # +1 212 450 4008 format
        r'\+\d[\s\d\-\(\)]+\d',  # International format
        r'\(\d{3}\)\s*\d{3}[\-\s]\d{4}',  # (XXX) XXX-XXXX
        r'\d{3}[\-\.\s]\d{3}[\-\.\s]\d{4}',  # XXX-XXX-XXXX
    ]
    
    for pattern in phone_patterns:
        phone_match = re.search(pattern, text_content)
        if phone_match:
            result['phone'] = phone_match.group(0).strip()
            break
    
    # Parse Office Location - Search entire page for exact matches
    for office in VALID_OFFICES:
        if office in text_content:
            result['office_location'] = office
            break
    
    # Parse Practice Areas - Search entire page for exact matches from valid set
    result['practice_type'] = extract_from_valid_set(text_content, VALID_PRACTICES)

    # Parse Industries - Search entire page for exact matches from valid set
    result['industry'] = extract_from_valid_set(text_content, VALID_INDUSTRIES)

    # Parse Education/School
    education_section = False
    for i, line in enumerate(cleaned_lines):
        if 'Education' in line:
            education_section = True
            continue
        
        if education_section:
            # Stop at next section
            if any(section in line for section in ['Clerkship', 'Qualification', 'Experience', 
                                                   'Insights', 'Back to']):
                education_section = False
                continue
            
            # Extract degrees and schools
            if 'J.D.' in line or 'LL.M.' in line or 'LL.B.' in line:
                result['school'].append(line)
            elif 'B.A.' in line or 'B.S.' in line or 'A.B.' in line:
                result['school'].append(line)
            elif 'M.A.' in line or 'M.S.' in line or 'MBA' in line or 'Ph.D.' in line:
                result['school'].append(line)
            # Also capture lines with University/College/School
            elif any(edu in line for edu in ['University', 'College', 'School', 'Institute']):
                if len(line) < 100:  # Reasonable length
                    result['school'].append(line)
    
    # Parse Clerkship
    clerkship_section = False
    for i, line in enumerate(cleaned_lines):
        if 'Clerkship' in line:
            clerkship_section = True
            continue
        
        if clerkship_section:
            # Stop at next section
            if any(section in line for section in ['Qualification', 'Experience', 'Education',
                                                   'Back to', 'Insights']):
                break
            
            # Capture clerkship info
            if any(keyword in line for keyword in ['Clerk', 'Judge', 'Hon.', 'Court']):
                if not result['clerkship']:
                    result['clerkship'] = line
                else:
                    result['clerkship'] += ', ' + line
    
    # Parse Region - Only from Capabilities section (exact matches from VALID_REGIONS)
    in_capabilities = False
    capabilities_text = []

    for i, line in enumerate(cleaned_lines):
        if 'Capabilities' in line:
            in_capabilities = True
            continue

        # Stop at next major section
        if in_capabilities and any(section in line for section in
                                   ['Experience', 'Education', 'Insights', 'Languages',
                                    'Prior experience', 'Clerkship', 'Qualifications',
                                    'Back to', 'Download', 'Print']):
            if 'Capabilities' not in line:
                in_capabilities = False
                continue

        # Collect capabilities section text
        if in_capabilities and line:
            if not any(skip in line.lower() for skip in
                      ['view', 'see more', 'download', 'print', 'back to', 'address card']):
                capabilities_text.append(line)

    # Extract regions from capabilities section only
    if capabilities_text:
        capabilities_content = '\n'.join(capabilities_text)
        regions_found = extract_from_valid_set(capabilities_content, VALID_REGIONS)
        if regions_found:
            result['region'] = regions_found
    
    # Parse Languages (less common in Davis Polk profiles but included for completeness)
    # Common languages to check for explicitly
    language_keywords = ['English', 'Spanish', 'French', 'German', 'Mandarin', 'Cantonese',
                        'Japanese', 'Korean', 'Italian', 'Portuguese', 'Russian', 'Arabic',
                        'Hindi', 'Dutch', 'Swedish', 'Norwegian', 'Hebrew', 'Greek',
                        'Bosnian', 'Serbian', 'Croatian', 'Serbo-Croatian', 'Turkish', 'Polish',
                        'Czech', 'Romanian', 'Bulgarian', 'Hungarian', 'Finnish', 'Danish',
                        'Icelandic', 'Farsi', 'Urdu', 'Bengali', 'Thai', 'Vietnamese',
                        'Indonesian', 'Malay', 'Tagalog', 'Swahili', 'Afrikaans', 'Zulu',
                        'Chinese', 'Catalan', 'Basque', 'Gaelic', 'Welsh', 'Albanian',
                        'Armenian', 'Georgian', 'Ukrainian', 'Belarusian', 'Slovak', 'Slovenian',
                        'Macedonian', 'Maltese', 'Estonian', 'Latvian', 'Lithuanian']
    
    # Look for Languages section - only extract languages from this section
    languages_section = False
    
    for i, line in enumerate(cleaned_lines):
        # Check if we're in a Languages section
        if 'Language' in line:
            languages_section = True
            continue
            
        # Stop at next major section
        if languages_section and any(section in line for section in 
                                    ['Experience', 'Education', 'Qualifications', 
                                     'Prior experience', 'Back to']):
            languages_section = False
            
        # Only extract languages if we're in the Languages section
        if languages_section:
            for lang in language_keywords:
                # Check if language appears in line (case-insensitive, word boundary)
                pattern = r'\b' + re.escape(lang) + r'\b'
                if re.search(pattern, line, re.IGNORECASE):
                    result['language'].append(lang)
    
    # Remove duplicates from languages
    result['language'] = list(set(result['language']))
    
    # Clean up empty lists - convert to None
    for key in ['practice_type', 'school', 'language']:
        if not result[key]:
            result[key] = None
    
    # Industry should also be None if empty
    if not result['industry']:
        result['industry'] = None
    
    return result