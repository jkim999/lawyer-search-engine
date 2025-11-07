"""
Parallel LLM filtering system for validating search results against complex queries.
"""

import sqlite3
from typing import List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from database import init_database
from scraping_utils import parse_page
from llm_utils import llm, MINI_MODEL


def evaluate_lawyer_for_query(lawyer_id: int, lawyer_url: str, query: str,
                             db_path: str = 'lawyers.db') -> Tuple[int, bool, str]:
    """
    Evaluate if a lawyer matches a complex query using LLM.

    Args:
        lawyer_id: ID of the lawyer
        lawyer_url: URL of the lawyer's profile
        query: The complex query to evaluate against
        db_path: Path to the database

    Returns:
        Tuple of (lawyer_id, passes, reasoning)
    """
    try:
        # Try to get cached parsed text from database first
        conn = init_database(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT parsed_text
            FROM experience_embeddings
            WHERE lawyer_id = ?
        ''', (lawyer_id,))

        row = cursor.fetchone()
        conn.close()

        if row and row['parsed_text']:
            # Use cached parsed text (fast!)
            profile_text = row['parsed_text']
        else:
            # Fallback to scraping if no cached text (backward compatibility)
            profile_text = parse_page(lawyer_url)
        
        system_prompt = """You are evaluating whether a lawyer's profile matches a specific search query.

Focus on the EXPERIENCE section and any relevant work mentioned in their profile.
Be precise - only return "Pass" if the profile clearly indicates they have the requested experience.

For queries about specific companies or industries:
- Look for explicit mentions of those companies/industries
- Consider related terms (e.g., "TV network" includes CNN, NBC, Fox, ABC, CBS, etc.)
- Look for relevant deal types or case descriptions

Respond in the following format:
<thinking>Analyze the profile and query step by step</thinking>
<answer>Pass or Fail</answer>"""

        user_prompt = f"""Query: {query}

Lawyer Profile:
{profile_text[:3000]}  # Limit context to avoid token limits

Does this lawyer's experience match the query?"""

        response = llm(
            model=MINI_MODEL,
            system_prompt=system_prompt,
            user_prompt=user_prompt
        )
        
        # Extract answer
        answer = "Fail"
        reasoning = ""
        
        if '<thinking>' in response and '</thinking>' in response:
            reasoning = response.split('<thinking>')[1].split('</thinking>')[0].strip()
        
        if '<answer>' in response and '</answer>' in response:
            answer = response.split('<answer>')[1].split('</answer>')[0].strip()
        
        passes = answer.lower() == 'pass'
        
        return lawyer_id, passes, reasoning
        
    except Exception as e:
        return lawyer_id, False, f"Error: {str(e)}"


def parallel_llm_filter(lawyer_ids: List[int], query: str,
                       batch_size: int = 15, max_workers: int = 15,
                       db_path: str = 'lawyers.db') -> List[Dict[str, Any]]:
    """
    Filter lawyer candidates using LLM in parallel batches.
    
    Args:
        lawyer_ids: List of lawyer IDs to evaluate
        query: The complex query
        batch_size: Number of lawyers to process in parallel
        max_workers: Maximum number of concurrent threads
        db_path: Path to the database
        
    Returns:
        List of lawyers that pass the criterion with their info
    """
    conn = init_database(db_path)
    cursor = conn.cursor()
    
    # Get lawyer URLs
    lawyer_info = {}
    for lawyer_id in lawyer_ids:
        cursor.execute(
            'SELECT id, name, url FROM lawyers WHERE id = ?',
            (lawyer_id,)
        )
        row = cursor.fetchone()
        if row:
            lawyer_info[lawyer_id] = {
                'id': row['id'],
                'name': row['name'],
                'url': row['url']
            }
    
    conn.close()
    
    # Process in parallel
    results = []
    total = len(lawyer_ids)
    processed = 0
    
    print(f"\nEvaluating {total} candidates for query: '{query}'")
    print("Processing", end="", flush=True)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit tasks in batches to respect rate limits
        futures = []
        
        for i in range(0, len(lawyer_ids), batch_size):
            batch = lawyer_ids[i:i + batch_size]
            
            for lawyer_id in batch:
                if lawyer_id in lawyer_info:
                    future = executor.submit(
                        evaluate_lawyer_for_query,
                        lawyer_id,
                        lawyer_info[lawyer_id]['url'],
                        query,
                        db_path
                    )
                    futures.append((future, lawyer_info[lawyer_id]))
            
            # Small delay between batches to respect rate limits
            if i + batch_size < len(lawyer_ids):
                time.sleep(0.1)  # Reduced from 0.5s - with caching we can be more aggressive
        
        # Collect results as they complete
        for future, info in futures:
            try:
                lawyer_id, passes, reasoning = future.result(timeout=30)
                processed += 1
                
                if passes:
                    results.append({
                        'id': info['id'],
                        'name': info['name'],
                        'url': info['url'],
                        'reasoning': reasoning
                    })
                    print("+", end="", flush=True)
                else:
                    print(".", end="", flush=True)
                    
            except Exception as e:
                print("x", end="", flush=True)
                processed += 1
    
    print(f"\nCompleted: {processed}/{total} evaluated, {len(results)} matches found")
    
    return results


def filter_with_reasoning(lawyer_ids: List[int], query: str,
                         db_path: str = 'lawyers.db') -> List[Dict[str, Any]]:
    """
    Filter lawyers and provide detailed reasoning for matches.
    
    Args:
        lawyer_ids: List of lawyer IDs to evaluate
        query: The complex query
        db_path: Path to the database
        
    Returns:
        List of matching lawyers with reasoning
    """
    results = parallel_llm_filter(lawyer_ids, query, db_path=db_path)
    
    # Sort by name for consistent output
    results.sort(key=lambda x: x['name'])
    
    return results


if __name__ == '__main__':
    # Test the LLM filter
    test_queries = [
        "lawyers who worked on a case for a TV network",
        "represented Fortune 500 companies in litigation",
        "experience with cryptocurrency regulations",
    ]
    
    # Get some sample lawyer IDs for testing
    conn = init_database()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM lawyers LIMIT 10')
    sample_ids = [row['id'] for row in cursor]
    conn.close()
    
    print("Testing LLM Filter")
    print("=" * 80)
    
    for query in test_queries[:1]:  # Test just one query to save API calls
        print(f"\nQuery: {query}")
        print("-" * 60)
        
        results = filter_with_reasoning(sample_ids, query)
        
        if results:
            print(f"\nFound {len(results)} matches:")
            for i, result in enumerate(results):
                print(f"\n{i+1}. {result['name']}")
                print(f"   URL: {result['url']}")
                print(f"   Reasoning: {result['reasoning'][:200]}...")
        else:
            print("\nNo matches found")
