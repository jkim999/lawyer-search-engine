import re
from typing import List, Dict, Any, Optional
from database import load_practice_aliases


def normalize_query_terms(query: str, practice_map: Optional[Dict[str, str]] = None) -> str:
    """
    Normalize query terms for case-insensitive matching and alias resolution.
    
    Args:
        query: Query string
        practice_map: Practice alias mapping
        
    Returns:
        Normalized query
    """
    query = query.lower().strip()
    
    # Normalize practice terms if map provided
    if practice_map:
        for alias, normalized in practice_map.items():
            if alias in query:
                query = query.replace(alias, normalized)
    
    return query


def parse_simple_query(query: str) -> List[Dict[str, Any]]:
    """
    Parse natural language query into structured AST format.
    
    Args:
        query: Natural language query (e.g., "lawyers named David", "graduated after 2015")
        
    Returns:
        AST representation: [{"field":"school","op":"contains","value":"yale"}, {"op":"AND"}, ...]
    """
    query = query.strip()
    if not query:
        return []
    
    ast = []
    practice_map = load_practice_aliases()
    query_lower = query.lower()
    
    # Handle temporal queries (graduated after/before/in)
    temporal_patterns = [
        (r'graduated\s+after\s+(\d{4})', 'gt'),
        (r'graduated\s+before\s+(\d{4})', 'lt'),
        (r'graduated\s+in\s+(\d{4})', 'eq'),
        (r'graduated\s+(\d{4})', 'eq'),
        (r'graduated\s+after\s+(\d{4})', 'gt'),
        (r'law\s+school\s+after\s+(\d{4})', 'gt'),
        (r'law\s+school\s+before\s+(\d{4})', 'lt'),
        (r'law\s+school\s+in\s+(\d{4})', 'eq'),
    ]
    
    for pattern, op in temporal_patterns:
        match = re.search(pattern, query_lower)
        if match:
            year = int(match.group(1))
            ast.append({
                'field': 'law_school_year',
                'op': op,
                'value': year
            })
            # Remove matched part from query
            query = re.sub(pattern, '', query, flags=re.IGNORECASE).strip()
            query_lower = query.lower()
            break
    
    # Handle name queries
    name_patterns = [
        r'lawyers?\s+named\s+([a-z\s]+)',
        r'name\s+is\s+([a-z\s]+)',
        r'name\s+([a-z\s]+)',
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, query_lower)
        if match:
            name = match.group(1).strip()
            ast.append({
                'field': 'name',
                'op': 'contains',
                'value': name
            })
            query = re.sub(pattern, '', query, flags=re.IGNORECASE).strip()
            query_lower = query.lower()
            break
    
    # Handle school queries
    school_patterns = [
        r'went\s+to\s+([a-z\s]+)',
        r'graduated\s+from\s+([a-z\s]+)',
        r'from\s+([a-z\s]+)',
        r'school\s+is\s+([a-z\s]+)',
        r'lawyers?\s+who\s+went\s+to\s+([a-z\s]+)',
    ]
    
    for pattern in school_patterns:
        match = re.search(pattern, query_lower)
        if match:
            school = match.group(1).strip()
            # Remove common words
            school = re.sub(r'\b(and|the|a|an)\b', '', school).strip()
            if school:
                ast.append({
                    'field': 'school',
                    'op': 'contains',
                    'value': school
                })
                query = re.sub(pattern, '', query, flags=re.IGNORECASE).strip()
                query_lower = query.lower()
            break
    
    # Handle practice queries
    practice_patterns = [
        r'practice\s+([a-z\s&]+)',
        r'in\s+([a-z\s&]+)',
        r'lawyers?\s+in\s+([a-z\s&]+)',
        r'practice\s+type\s+is\s+([a-z\s&]+)',
    ]
    
    for pattern in practice_patterns:
        match = re.search(pattern, query_lower)
        if match:
            practice = match.group(1).strip()
            # Normalize practice name
            practice_lower = practice.lower()
            if practice_map and practice_lower in practice_map:
                practice = practice_map[practice_lower]
            else:
                # Capitalize properly
                practice = practice.title()
            
            ast.append({
                'field': 'practice',
                'op': 'eq',
                'value': practice
            })
            query = re.sub(pattern, '', query, flags=re.IGNORECASE).strip()
            query_lower = query.lower()
            break
    
    # Handle title queries
    title_patterns = [
        r'partners?',
        r'associates?',
        r'counsel',
        r'title\s+is\s+([a-z\s]+)',
    ]
    
    for pattern in title_patterns:
        match = re.search(pattern, query_lower)
        if match:
            if 'partner' in query_lower:
                title = 'Partner'
            elif 'associate' in query_lower:
                title = 'Associate'
            elif 'counsel' in query_lower:
                title = 'Counsel'
            else:
                title = match.group(1).title() if match.groups() else None
            
            if title:
                ast.append({
                    'field': 'title',
                    'op': 'eq',
                    'value': title
                })
                query = re.sub(pattern, '', query, flags=re.IGNORECASE).strip()
                query_lower = query.lower()
            break
    
    # Handle region queries
    region_patterns = [
        r'in\s+(asia|china|japan|europe|latin\s+america|israel)',
        r'region\s+is\s+([a-z\s]+)',
    ]
    
    for pattern in region_patterns:
        match = re.search(pattern, query_lower)
        if match:
            region = match.group(1).strip()
            # Capitalize properly
            if 'latin america' in region:
                region = 'Latin America'
            else:
                region = region.title()
            
            ast.append({
                'field': 'region',
                'op': 'eq',
                'value': region
            })
            query = re.sub(pattern, '', query, flags=re.IGNORECASE).strip()
            query_lower = query.lower()
            break
    
    # Handle language queries
    language_patterns = [
        r'lawyers?\s+who\s+speak\s+([a-z\s\-]+)',
        r'speak\s+([a-z\s\-]+)',
        r'language\s+is\s+([a-z\s\-]+)',
        r'languages?\s+([a-z\s\-]+)',
    ]
    
    for pattern in language_patterns:
        match = re.search(pattern, query_lower)
        if match:
            language = match.group(1).strip()
            # Keep original case for better matching, but normalize
            # Don't use title() as it might not match database entries exactly
            # Use contains op for flexible matching
            language = language.strip()
            
            ast.append({
                'field': 'language',
                'op': 'contains',
                'value': language
            })
            query = re.sub(pattern, '', query, flags=re.IGNORECASE).strip()
            query_lower = query.lower()
            break
    
    # Handle AND logic
    if ' and ' in query_lower:
        # Split by AND and parse each part
        parts = re.split(r'\s+and\s+', query_lower)
        new_ast = []
        for i, part in enumerate(parts):
            if i > 0:
                new_ast.append({'op': 'AND'})
            part_ast = parse_simple_query(part.strip())
            new_ast.extend(part_ast)
        
        if new_ast:
            return new_ast
    
    # If no specific patterns matched, try to extract keywords
    if not ast:
        # Try to find any remaining meaningful words
        words = query.split()
        # Filter out common stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'who', 'that', 'is', 'are', 'lawyers', 'lawyer'}
        keywords = [w for w in words if w.lower() not in stop_words and len(w) > 2]
        
        if keywords:
            # Default to name search
            ast.append({
                'field': 'name',
                'op': 'contains',
                'value': ' '.join(keywords)
            })
    
    return ast


def build_ast(query_parts: List[str]) -> List[Dict[str, Any]]:
    """
    Build AST from query parts with boolean logic.
    
    Args:
        query_parts: List of query string parts
        
    Returns:
        AST representation
    """
    ast = []
    
    for i, part in enumerate(query_parts):
        if i > 0:
            ast.append({'op': 'AND'})
        
        part_ast = parse_simple_query(part.strip())
        ast.extend(part_ast)
    
    return ast


if __name__ == '__main__':
    # Test queries
    test_queries = [
        "lawyers named David",
        "lawyers who went to Yale",
        "graduated after 2015",
        "lawyers in Tax",
        "lawyers who went to Yale and practice Tax",
        "Partners",
    ]
    
    for query in test_queries:
        ast = parse_simple_query(query)
        print(f"Query: {query}")
        print(f"AST: {ast}")
        print()

