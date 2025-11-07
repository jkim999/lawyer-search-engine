"""
Query classification module to distinguish between simple and complex queries.
"""

import re
from typing import Literal
from llm_utils import llm, MINI_MODEL


def classify_query_fast(query: str) -> Literal['simple', 'complex', 'unknown']:
    """
    Fast pattern-based classification for obvious cases.

    Returns:
        'simple', 'complex', or 'unknown' if ambiguous
    """
    query_lower = query.lower().strip()

    # Simple query patterns - can be answered with direct database lookups
    simple_patterns = [
        r'\b(named|called|with name)\b',  # "lawyers named John"
        r'\b(went to|graduated from|attended|studied at)\s+\w+',  # "went to Yale"
        r'\b(partner|associate|counsel|senior)s?\b',  # titles
        r'\b(speak|speaks|speaking)\s+\w+',  # "speak Spanish"
        r'\b(graduated|graduation)\s+(after|before|in)\s+\d{4}',  # "graduated after 2015"
        r'\b(office|location|based|located)\s+(in|at)',  # "office in London"
        r'\b(practice|practices|area)\b',  # practice areas
        r'^\w+\s+\w+$',  # Simple name search like "John Smith"
    ]

    # Complex query patterns - require semantic understanding
    complex_patterns = [
        r'\b(worked on|represented|defended|prosecuted|handled)\b',  # experience-based
        r'\b(case|deal|transaction|matter|litigation|ipo|merger|acquisition)\b',  # specific work
        r'\b(experience|expertise|background)\s+(with|in)\b',  # expertise-based
        r'\b(fortune\s*500|tech\s*(company|companies|startup)|pharma|bank)\b',  # company types
        r'\b(tv\s*network|streaming|broadcast|media)\b',  # specific industries
    ]

    # Check simple patterns first
    for pattern in simple_patterns:
        if re.search(pattern, query_lower):
            # But check if it also matches complex patterns
            has_complex = any(re.search(p, query_lower) for p in complex_patterns)
            if not has_complex:
                return 'simple'

    # Check complex patterns
    for pattern in complex_patterns:
        if re.search(pattern, query_lower):
            return 'complex'

    # Ambiguous - needs LLM
    return 'unknown'


def classify_query(query: str) -> Literal['simple', 'complex']:
    """
    Classify a query as 'simple' or 'complex'.

    Uses fast pattern matching for obvious cases, falls back to LLM for ambiguous queries.

    Simple queries: Can be answered with direct database lookups
    Complex queries: Require semantic understanding and searching through unstructured text

    Args:
        query: The user's search query

    Returns:
        'simple' or 'complex'
    """
    # Try fast classification first
    fast_result = classify_query_fast(query)
    if fast_result != 'unknown':
        return fast_result

    # Fall back to LLM for ambiguous queries
    system_prompt = """You are a query classifier for a lawyer search system.

Classify queries into two categories:

SIMPLE queries - can be answered with direct database lookups:
- Name searches: "lawyers named John", "John Smith"
- Title searches: "partners", "associates", "counsel"
- School searches: "went to Yale", "graduated from Harvard", "attended Stanford"
- Practice area searches: "tax lawyers", "lawyers in corporate"
- Language searches: "lawyers who speak Spanish", "French-speaking lawyers"
- Graduation year comparisons: "graduated after 2015", "graduated before 2020", "graduated in 2018"
- Location/region: "lawyers in Asia", "London office", "New York partners"
- Combinations of the above: "partners who went to Yale", "tax lawyers who speak Spanish"

IMPORTANT: Date comparisons (after, before, in + year) are ALWAYS simple queries.

COMPLEX queries - require understanding context and searching through unstructured text:
- Experience with specific companies: "worked with Google", "represented Apple"
- Industry expertise: "lawyers who worked on a case for a TV network"
- Deal types: "handled IPOs", "worked on mergers", "M&A experience"
- Specific legal work: "defended pharmaceutical companies", "prosecuted antitrust cases"
- Case types: "worked on litigation", "handled patent disputes"
- Contextual understanding: "lawyers who helped tech startups go public"
- Any query requiring inference: "lawyers experienced with streaming services"

Respond with only one word: 'simple' or 'complex'"""

    user_prompt = f"Classify this query: {query}"
    
    response = llm(
        model=MINI_MODEL,
        system_prompt=system_prompt,
        user_prompt=user_prompt
    ).strip().lower()
    
    # Ensure we only return valid values
    if response not in ['simple', 'complex']:
        # Default to complex for safety - better to over-process than miss results
        return 'complex'
    
    return response


if __name__ == '__main__':
    # Test the classifier
    test_queries = [
        # Simple queries
        "lawyers named David",
        "partners",
        "lawyers who went to Yale",
        "tax lawyers",
        "lawyers who speak Mandarin",
        "graduated after 2015",
        "partners in the London office",
        
        # Complex queries
        "lawyers who worked on a case for a TV network",
        "represented Fortune 500 companies",
        "handled IPO for tech companies",
        "experience with cryptocurrency regulations",
        "defended banks in fraud cases",
        "worked with streaming platforms",
    ]
    
    print("Query Classification Tests:")
    print("-" * 60)
    
    for query in test_queries:
        classification = classify_query(query)
        print(f"{classification:8} | {query}")
