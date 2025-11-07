"""
Query classification module to distinguish between simple and complex queries.
"""

from typing import Literal
from llm_utils import llm, MINI_MODEL


def classify_query(query: str) -> Literal['simple', 'complex']:
    """
    Classify a query as 'simple' or 'complex'.
    
    Simple queries: Can be answered with direct database lookups
    Complex queries: Require semantic understanding and searching through unstructured text
    
    Args:
        query: The user's search query
        
    Returns:
        'simple' or 'complex'
    """
    system_prompt = """You are a query classifier for a lawyer search system.

Classify queries into two categories:

SIMPLE queries - can be answered with direct database lookups:
- Name searches: "lawyers named John", "John Smith"
- Title searches: "partners", "associates", "counsel"
- School searches: "went to Yale", "graduated from Harvard"
- Practice area searches: "tax lawyers", "lawyers in corporate"
- Language searches: "lawyers who speak Spanish"
- Graduation year: "graduated after 2015"
- Location/region: "lawyers in Asia", "London office"
- Combinations of the above: "partners who went to Yale"

COMPLEX queries - require understanding context and searching through unstructured text:
- Experience with specific companies: "worked with Google", "represented Apple"
- Industry expertise: "lawyers who worked on a case for a TV network"
- Deal types: "handled IPOs", "worked on mergers"
- Specific legal work: "defended pharmaceutical companies", "prosecuted antitrust cases"
- Contextual understanding: "lawyers who helped tech startups go public"
- Any query requiring inference: "lawyers experienced with streaming services" (requires knowing Netflix/Hulu are streaming services)

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
