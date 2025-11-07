import sqlite3
import gzip
from typing import Optional, Dict, List, Any
import os


def init_database(db_path: str = 'lawyers.db') -> sqlite3.Connection:
    """
    Initialize SQLite database with schema for lawyers, educations, practices, etc.
    
    Args:
        db_path: Path to SQLite database file
        
    Returns:
        Database connection
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    cursor = conn.cursor()
    
    # Lawyers table - core lawyer information
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lawyers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            name TEXT,
            first_name TEXT,
            last_name TEXT,
            email TEXT,
            phone TEXT,
            title TEXT,
            office_location TEXT,
            clerkship TEXT,
            raw_html BLOB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Educations table - normalized education entries
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS educations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lawyer_id INTEGER NOT NULL,
            degree_type TEXT,
            year INTEGER,
            school_name TEXT,
            school_normalized TEXT,
            is_law_degree INTEGER DEFAULT 0,
            honors TEXT,
            full_text TEXT,
            FOREIGN KEY (lawyer_id) REFERENCES lawyers(id) ON DELETE CASCADE
        )
    ''')
    
    # Practices table - practice areas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS practices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lawyer_id INTEGER NOT NULL,
            practice_type TEXT NOT NULL,
            FOREIGN KEY (lawyer_id) REFERENCES lawyers(id) ON DELETE CASCADE
        )
    ''')
    
    # Industries table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS industries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lawyer_id INTEGER NOT NULL,
            industry TEXT NOT NULL,
            FOREIGN KEY (lawyer_id) REFERENCES lawyers(id) ON DELETE CASCADE
        )
    ''')
    
    # Regions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS regions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lawyer_id INTEGER NOT NULL,
            region TEXT NOT NULL,
            FOREIGN KEY (lawyer_id) REFERENCES lawyers(id) ON DELETE CASCADE
        )
    ''')
    
    # Languages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS languages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lawyer_id INTEGER NOT NULL,
            language TEXT NOT NULL,
            FOREIGN KEY (lawyer_id) REFERENCES lawyers(id) ON DELETE CASCADE
        )
    ''')
    
    # Schools table - normalized school names and aliases
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            normalized_name TEXT UNIQUE NOT NULL,
            alias TEXT UNIQUE
        )
    ''')
    
    # Experience embeddings table for semantic search
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS experience_embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lawyer_id INTEGER NOT NULL,
            content TEXT,
            parsed_text TEXT,
            embedding BLOB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lawyer_id) REFERENCES lawyers(id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    return conn


def create_indexes(conn: sqlite3.Connection):
    """
    Create database indexes and FTS5 virtual table for fast lookups.
    
    Args:
        conn: Database connection
    """
    cursor = conn.cursor()
    
    # Regular indexes
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_educations_lawyear 
        ON educations(year) WHERE is_law_degree=1
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_educations_school 
        ON educations(school_normalized)
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_educations_lawyer 
        ON educations(lawyer_id)
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_practices_type 
        ON practices(practice_type)
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_practices_lawyer 
        ON practices(lawyer_id)
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_lawyers_title 
        ON lawyers(title)
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_lawyers_name 
        ON lawyers(first_name, last_name)
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_experience_embeddings_lawyer 
        ON experience_embeddings(lawyer_id)
    ''')
    
    # FTS5 virtual table for full-text search
    # Note: We use a contentless FTS5 table and manage it manually via triggers
    # This avoids column name mismatches between FTS5 and the lawyers table
    # Drop triggers first (they reference the table)
    cursor.execute('DROP TRIGGER IF EXISTS lawyers_fts_insert')
    cursor.execute('DROP TRIGGER IF EXISTS lawyers_fts_update')
    cursor.execute('DROP TRIGGER IF EXISTS lawyers_fts_delete')
    cursor.execute('DROP TABLE IF EXISTS lawyers_fts')
    cursor.execute('''
        CREATE VIRTUAL TABLE lawyers_fts USING fts5(
            full_name,
            title
        )
    ''')
    
    # Repopulate FTS5 table with existing lawyers data
    cursor.execute('''
        INSERT INTO lawyers_fts(rowid, full_name, title)
        SELECT id, name, title FROM lawyers
    ''')
    
    # Trigger to keep FTS in sync on insert
    cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS lawyers_fts_insert AFTER INSERT ON lawyers BEGIN
            INSERT INTO lawyers_fts(rowid, full_name, title)
            VALUES (new.id, new.name, new.title);
        END
    ''')
    
    # Trigger to keep FTS in sync on update
    # For contentless FTS5, UPDATE doesn't work well, so we delete and re-insert
    cursor.execute('DROP TRIGGER IF EXISTS lawyers_fts_update')
    cursor.execute('''
        CREATE TRIGGER lawyers_fts_update AFTER UPDATE ON lawyers BEGIN
            DELETE FROM lawyers_fts WHERE rowid = new.id;
            INSERT INTO lawyers_fts(rowid, full_name, title)
            VALUES (new.id, new.name, new.title);
        END
    ''')
    
    # Trigger to keep FTS in sync on delete
    cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS lawyers_fts_delete AFTER DELETE ON lawyers BEGIN
            DELETE FROM lawyers_fts WHERE rowid = old.id;
        END
    ''')
    
    conn.commit()


def upsert_lawyer(conn: sqlite3.Connection, url: str, parsed_data: Dict[str, Any], 
                  raw_html: Optional[bytes] = None, store_html: bool = False):
    """
    Insert or update lawyer data in the database.
    
    Args:
        conn: Database connection
        url: Lawyer profile URL
        parsed_data: Parsed lawyer data from parse_text()
        raw_html: Raw HTML content (will be gzipped if store_html=True)
        store_html: Whether to store raw HTML
    """
    cursor = conn.cursor()
    
    # Prepare name parts with validation
    name = parsed_data.get('name', '')
    
    # Validate name - reject common navigation text
    name_blacklist = {
        'print this page', 'download address card', 'back to top', 'back to',
        'lawyers', 'capabilities', 'insights', 'experience', 'education',
        'skip to main content', 'top of page', 'davis polk'
    }
    
    if name:
        name_lower = name.lower().strip()
        # Check if name is in blacklist or contains blacklisted phrases
        if name_lower in name_blacklist or any(blacklisted in name_lower for blacklisted in name_blacklist):
            # If name is invalid, try to extract from email or URL
            name = None
            email = parsed_data.get('email', '')
            if email and '@' in email:
                # Try to extract name from email (e.g., alon.gurfinkel@davispolk.com -> Alon Gurfinkel)
                email_local = email.split('@')[0]
                # Replace dots and hyphens with spaces, then title case
                potential_name = email_local.replace('.', ' ').replace('-', ' ').title()
                # Only use if it looks reasonable (at least 2 words)
                if len(potential_name.split()) >= 2 and len(potential_name) < 50:
                    name = potential_name
    
    name_parts = name.split(maxsplit=1) if name else ('', '')
    first_name = name_parts[0] if name_parts else ''
    last_name = name_parts[1] if len(name_parts) > 1 else ''
    
    # Compress HTML if storing
    html_blob = None
    if store_html and raw_html:
        html_blob = gzip.compress(raw_html)
    
    # Upsert lawyer
    cursor.execute('''
        INSERT INTO lawyers (url, name, first_name, last_name, email, phone, 
                           title, office_location, clerkship, raw_html, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(url) DO UPDATE SET
            name = excluded.name,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            email = excluded.email,
            phone = excluded.phone,
            title = excluded.title,
            office_location = excluded.office_location,
            clerkship = excluded.clerkship,
            raw_html = excluded.raw_html,
            updated_at = CURRENT_TIMESTAMP
    ''', (url, name, first_name, last_name, 
          parsed_data.get('email'), parsed_data.get('phone'),
          parsed_data.get('title'), parsed_data.get('office_location'),
          parsed_data.get('clerkship'), html_blob))
    
    lawyer_id = cursor.lastrowid
    
    # Get lawyer_id if it was an update (lastrowid is 0 for UPDATE)
    if lawyer_id == 0:
        cursor.execute('SELECT id FROM lawyers WHERE url = ?', (url,))
        row = cursor.fetchone()
        lawyer_id = row['id'] if row else None
    
    if not lawyer_id:
        return None
    
    # Delete existing related records
    cursor.execute('DELETE FROM educations WHERE lawyer_id = ?', (lawyer_id,))
    cursor.execute('DELETE FROM practices WHERE lawyer_id = ?', (lawyer_id,))
    cursor.execute('DELETE FROM industries WHERE lawyer_id = ?', (lawyer_id,))
    cursor.execute('DELETE FROM regions WHERE lawyer_id = ?', (lawyer_id,))
    cursor.execute('DELETE FROM languages WHERE lawyer_id = ?', (lawyer_id,))
    
    # Insert educations (will be populated by indexing.py with proper parsing)
    # This is a placeholder - actual education insertion happens in indexing.py
    
    # Insert practices
    if parsed_data.get('practice_type'):
        for practice in parsed_data['practice_type']:
            cursor.execute('''
                INSERT INTO practices (lawyer_id, practice_type)
                VALUES (?, ?)
            ''', (lawyer_id, practice))
    
    # Insert industries
    if parsed_data.get('industry'):
        for industry in parsed_data['industry']:
            cursor.execute('''
                INSERT INTO industries (lawyer_id, industry)
                VALUES (?, ?)
            ''', (lawyer_id, industry))
    
    # Insert regions
    if parsed_data.get('region'):
        regions = parsed_data['region'] if isinstance(parsed_data['region'], list) else [parsed_data['region']]
        for region in regions:
            cursor.execute('''
                INSERT INTO regions (lawyer_id, region)
                VALUES (?, ?)
            ''', (lawyer_id, region))
    
    # Insert languages
    if parsed_data.get('language'):
        for lang in parsed_data['language']:
            cursor.execute('''
                INSERT INTO languages (lawyer_id, language)
                VALUES (?, ?)
            ''', (lawyer_id, lang))
    
    conn.commit()
    return lawyer_id


def load_school_aliases(conn: sqlite3.Connection, alias_file: str = 'school_alias.csv'):
    """
    Load school aliases from CSV file into schools table.
    
    Args:
        conn: Database connection
        alias_file: Path to school_alias.csv file
    """
    if not os.path.exists(alias_file):
        # Create a default empty file if it doesn't exist
        return
    
    cursor = conn.cursor()
    
    with open(alias_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        if not lines:
            return
        
        # Assume CSV format: normalized_name,alias1,alias2,...
        for line in lines[1:]:  # Skip header if present
            line = line.strip()
            if not line:
                continue
            
            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 2:
                continue
            
            normalized_name = parts[0]
            aliases = parts[1:]
            
            # Insert normalized name (if not exists)
            cursor.execute('''
                INSERT OR IGNORE INTO schools (normalized_name, alias)
                VALUES (?, NULL)
            ''', (normalized_name,))
            
            # Insert aliases
            for alias in aliases:
                if alias:
                    cursor.execute('''
                        INSERT OR IGNORE INTO schools (normalized_name, alias)
                        VALUES (?, ?)
                    ''', (normalized_name, alias))
    
    conn.commit()


def load_practice_aliases(alias_file: str = 'practice_alias.csv') -> Dict[str, str]:
    """
    Load practice aliases from CSV file into memory mapping.
    
    Args:
        alias_file: Path to practice_alias.csv file
        
    Returns:
        Dictionary mapping aliases to normalized practice names
    """
    practice_map = {}
    
    if not os.path.exists(alias_file):
        return practice_map
    
    with open(alias_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        if not lines:
            return practice_map
        
        # Assume CSV format: normalized_name,alias1,alias2,...
        for line in lines[1:]:  # Skip header if present
            line = line.strip()
            if not line:
                continue
            
            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 2:
                continue
            
            normalized_name = parts[0]
            aliases = parts[1:]
            
            # Map normalized name to itself
            practice_map[normalized_name.lower()] = normalized_name
            
            # Map aliases to normalized name
            for alias in aliases:
                if alias:
                    practice_map[alias.lower()] = normalized_name
    
    return practice_map


def get_school_normalized(conn: sqlite3.Connection, school_name: str) -> str:
    """
    Get normalized school name from alias table.
    
    Args:
        conn: Database connection
        school_name: School name to normalize
        
    Returns:
        Normalized school name
    """
    cursor = conn.cursor()
    
    # Try exact match first
    cursor.execute('''
        SELECT normalized_name FROM schools 
        WHERE normalized_name = ? OR alias = ?
        LIMIT 1
    ''', (school_name, school_name))
    
    row = cursor.fetchone()
    if row:
        return row['normalized_name']
    
    # Try case-insensitive match
    cursor.execute('''
        SELECT normalized_name FROM schools 
        WHERE LOWER(normalized_name) = LOWER(?) OR LOWER(alias) = LOWER(?)
        LIMIT 1
    ''', (school_name, school_name))
    
    row = cursor.fetchone()
    if row:
        return row['normalized_name']
    
    # Return original if no match found
    return school_name

