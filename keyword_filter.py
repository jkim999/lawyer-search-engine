"""
Keyword-based filtering to reduce LLM candidates for complex queries.
"""

import re
from typing import List, Tuple, Set
from database import init_database


def extract_keywords(query: str) -> Set[str]:
    """
    Extract relevant keywords from a complex query.

    Args:
        query: The search query

    Returns:
        Set of lowercase keywords
    """
    # Common company/entity patterns
    company_patterns = [
        r'\b(?:CNN|NBC|Fox|ABC|CBS|HBO|ESPN|MTV)\b',  # TV networks
        r'\b(?:Netflix|Hulu|Disney\+?|Amazon\s*Prime|Apple\s*TV)\b',  # Streaming
        r'\b(?:Google|Apple|Microsoft|Amazon|Facebook|Meta|Tesla)\b',  # Big tech
        r'\b(?:Goldman\s*Sachs|JPMorgan|Morgan\s*Stanley|Bank\s*of\s*America)\b',  # Banks
        r'\b(?:Pfizer|Moderna|Johnson\s*&\s*Johnson|Merck)\b',  # Pharma
    ]

    # Industry/domain keywords
    industry_keywords = [
        'television', 'broadcast', 'tv', 'network', 'media', 'streaming',
        'cryptocurrency', 'crypto', 'bitcoin', 'blockchain', 'digital asset',
        'pharmaceutical', 'pharma', 'drug', 'clinical', 'fda',
        'technology', 'tech', 'software', 'startup',
        'ipo', 'public offering', 'merger', 'acquisition',
        'litigation', 'lawsuit', 'dispute', 'court', 'trial',
        'fortune 500', 'fortune500',
    ]

    keywords = set()

    # Extract company names
    query_upper = query  # Preserve case for company names
    for pattern in company_patterns:
        matches = re.finditer(pattern, query_upper, re.IGNORECASE)
        for match in matches:
            keywords.add(match.group(0).lower())

    # Extract industry keywords
    query_lower = query.lower()
    for keyword in industry_keywords:
        if keyword in query_lower:
            keywords.add(keyword)

    # Extract quoted phrases (high importance)
    quoted = re.findall(r'"([^"]+)"', query)
    for phrase in quoted:
        keywords.add(phrase.lower().strip())

    # Extract capitalized multi-word entities (likely company/org names)
    capitalized_entities = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', query)
    for entity in capitalized_entities:
        keywords.add(entity.lower())

    return keywords


def keyword_filter_candidates(candidate_ids: List[int], query: str,
                              db_path: str = 'lawyers.db',
                              min_keyword_matches: int = 0) -> List[int]:
    """
    Filter candidates based on keyword matching against their cached text.

    Args:
        candidate_ids: List of candidate lawyer IDs from semantic search
        query: The search query
        db_path: Path to the database
        min_keyword_matches: Minimum number of keywords that must match (0 = any match)

    Returns:
        Filtered list of lawyer IDs that match keywords
    """
    keywords = extract_keywords(query)

    # If no specific keywords extracted, return all candidates
    if not keywords:
        return candidate_ids

    conn = init_database(db_path)
    cursor = conn.cursor()

    filtered_ids = []

    for lawyer_id in candidate_ids:
        # Get cached parsed text
        cursor.execute('''
            SELECT parsed_text, content
            FROM experience_embeddings
            WHERE lawyer_id = ?
        ''', (lawyer_id,))

        row = cursor.fetchone()
        if not row:
            # No cached text, keep in candidates (fallback)
            filtered_ids.append(lawyer_id)
            continue

        # Combine parsed text and experience content
        text = (row['parsed_text'] or '') + ' ' + (row['content'] or '')
        text_lower = text.lower()

        # Count keyword matches
        matches = sum(1 for keyword in keywords if keyword in text_lower)

        # Include if meets minimum threshold
        if min_keyword_matches == 0:
            # Any match or no keywords extracted
            if matches > 0 or not keywords:
                filtered_ids.append(lawyer_id)
        else:
            if matches >= min_keyword_matches:
                filtered_ids.append(lawyer_id)

    conn.close()

    return filtered_ids


def smart_filter_candidates(candidate_ids: List[int], query: str,
                            db_path: str = 'lawyers.db') -> List[int]:
    """
    Smart filtering that adapts based on query and candidate pool size.

    Args:
        candidate_ids: List of candidate lawyer IDs
        query: The search query
        db_path: Path to the database

    Returns:
        Filtered list of lawyer IDs
    """
    keywords = extract_keywords(query)

    # If we have many keywords (specific query), be more strict
    if len(keywords) >= 3:
        # Require at least 2 keyword matches
        filtered = keyword_filter_candidates(candidate_ids, query, db_path, min_keyword_matches=2)
        # If too few results, relax to 1 match
        if len(filtered) < 5:
            filtered = keyword_filter_candidates(candidate_ids, query, db_path, min_keyword_matches=1)
    elif len(keywords) >= 1:
        # Require at least 1 keyword match
        filtered = keyword_filter_candidates(candidate_ids, query, db_path, min_keyword_matches=1)
    else:
        # No keywords, return all candidates
        filtered = candidate_ids

    # Always return at least top candidates even if no keyword matches
    # This ensures we don't completely miss results due to overly strict filtering
    if len(filtered) == 0 and len(candidate_ids) > 0:
        # Fall back to top 20 from semantic search
        return candidate_ids[:20]

    return filtered


if __name__ == '__main__':
    # Test keyword extraction
    test_queries = [
        "lawyers who worked on a case for a TV network",
        "represented Fortune 500 companies in litigation",
        "experience with cryptocurrency regulations",
        "handled IPOs for tech companies",
        "defended pharmaceutical companies",
        "worked with CNN or NBC on media deals",
    ]

    print("Keyword Extraction Tests:")
    print("=" * 80)

    for query in test_queries:
        keywords = extract_keywords(query)
        print(f"\nQuery: {query}")
        print(f"Keywords: {sorted(keywords)}")
