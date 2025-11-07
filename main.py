import argparse
import json
import sys
import sqlite3
import hashlib
import time
from typing import List, Dict, Any, Optional
from collections import OrderedDict
from database import init_database, create_indexes, load_school_aliases
from query_parser import parse_simple_query
from search import compile_ast_to_sql, execute_query, explain_query
from indexing import scrape_and_cache_lawyers, cleanup_bad_names
from llm_utils import llm, get_embedding
from scraping_utils import parse_page, parse_text
from query_classifier import classify_query
from semantic_search import semantic_search
from llm_filter import parallel_llm_filter
from keyword_filter import smart_filter_candidates


# Query result cache (LRU cache with TTL)
class QueryCache:
    """Simple LRU cache for query results with time-to-live."""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        self.cache = OrderedDict()
        self.timestamps = {}
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds

    def _get_key(self, query: str, db_path: str) -> str:
        """Generate cache key from query and db path."""
        combined = f"{query.lower().strip()}:{db_path}"
        return hashlib.md5(combined.encode()).hexdigest()

    def get(self, query: str, db_path: str) -> Optional[List[Dict[str, Any]]]:
        """Get cached results if they exist and are not expired."""
        key = self._get_key(query, db_path)

        if key not in self.cache:
            return None

        # Check if expired
        if time.time() - self.timestamps[key] > self.ttl_seconds:
            # Remove expired entry
            del self.cache[key]
            del self.timestamps[key]
            return None

        # Move to end (most recently used)
        self.cache.move_to_end(key)
        return self.cache[key]

    def set(self, query: str, db_path: str, results: List[Dict[str, Any]]) -> None:
        """Store results in cache."""
        key = self._get_key(query, db_path)

        # Remove oldest if at capacity
        if len(self.cache) >= self.max_size and key not in self.cache:
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
            del self.timestamps[oldest_key]

        self.cache[key] = results
        self.timestamps[key] = time.time()
        self.cache.move_to_end(key)

    def clear(self) -> None:
        """Clear all cached results."""
        self.cache.clear()
        self.timestamps.clear()


# Global query cache instance
_query_cache = QueryCache(max_size=100, ttl_seconds=3600)


def passes_criterion(lawyer_url: str, query: str) -> bool:
    """
    Evaluate if a lawyer passes a given criterion based on their profile.

    Args:
        lawyer_url (str): URL of the lawyer's profile
        query (str): Criterion to evaluate against

    Returns:
        bool: True if lawyer passes the criterion, False otherwise
    """
    text = parse_page(lawyer_url)
    
    system_prompt = """
    You are evaluating a lawyer whether they pass a given criterion.
    
    Respond in the following format:
    <thinking>...</thinking>, within which you include your detailed thought process.
    <answer>...</answer>, within which you include your final answer. "Pass" or "Fail".
    """.strip()
    
    user_prompt = f"""
    Here is the query: {query}
    Here is the lawyer's profile: {text}
    """.strip()
    
    response = llm(system_prompt=system_prompt, user_prompt=user_prompt)
    return response.split('<answer>')[1].split('</answer>')[0].strip() == 'Pass'


def main(query: str, db_path: str = 'lawyers.db', show_sql: bool = False,
         format_output: str = 'table', use_cache: bool = True) -> List[Dict[str, Any]]:
    """
    Takes in a string as a query and returns the list of lawyers.

    Args:
        query (str): The search query.
        db_path (str): Path to SQLite database.
        show_sql (bool): Whether to show compiled SQL and execution plan.
        format_output (str): Output format ('json' or 'table').
        use_cache (bool): Whether to use query result caching.

    Returns:
        list: A list of lawyers matching the query.
    """
    # Check cache first
    if use_cache:
        cached_results = _query_cache.get(query, db_path)
        if cached_results is not None:
            if show_sql:
                print("✓ Returning cached results")
            return cached_results

    # Classify the query
    query_type = classify_query(query)
    
    if show_sql:
        print(f"Query classified as: {query_type}")
    
    if query_type == 'simple':
        # Use existing simple query flow
        conn = init_database(db_path)
        
        # Parse query to AST
        ast = parse_simple_query(query)
        
        if not ast:
            return []
        
        # Compile AST to SQL
        sql, params = compile_ast_to_sql(ast, conn)
        
        # Show SQL and execution plan if requested
        if show_sql:
            print("=" * 80)
            print("Query AST:")
            print(json.dumps(ast, indent=2))
            print("\nCompiled SQL:")
            print(sql)
            print("\nParameters:")
            print(params)
            print("\nExecution Plan:")
            plan = explain_query(conn, sql, params)
            print(plan)
            print("=" * 80)
            print()
        
        # Execute query
        results = execute_query(conn, sql, params)

        conn.close()

        # Cache results before returning
        if use_cache:
            _query_cache.set(query, db_path, results)

    else:
        # Complex query flow
        if show_sql:
            print("Using semantic search + LLM filtering for complex query")
            print("=" * 80)
        
        # Step 1: Semantic search to find candidates
        # Adaptive k: more candidates for generic queries, fewer for specific ones
        from keyword_filter import extract_keywords
        keywords = extract_keywords(query)

        # Determine k based on keyword specificity
        if len(keywords) >= 3:
            # Very specific query - need more candidates to ensure coverage
            k = 30
        elif len(keywords) >= 1:
            # Moderately specific - standard candidate pool
            k = 40
        else:
            # Generic query - cast wider net
            k = 50

        if show_sql:
            print(f"Using k={k} for semantic search (query has {len(keywords)} keywords)")

        try:
            candidates = semantic_search(query, k=k, db_path=db_path)
        except ValueError as e:
            # Handle missing embeddings error
            error_msg = str(e)
            print(f"\nError: {error_msg}\n")
            if not show_sql:
                print("Tip: Run with --why flag to see detailed diagnostics")
            return []
        except Exception as e:
            print(f"\nError during semantic search: {e}")
            if show_sql:
                import traceback
                traceback.print_exc()
            return []
        
        if show_sql:
            print(f"Semantic search found {len(candidates)} candidates")
        
        if not candidates:
            if show_sql:
                print("Warning: Semantic search returned no candidates. This may indicate:")
                print("  - No lawyers have relevant experience")
                print("  - Embeddings may need to be regenerated")
            return []
        
        # Extract lawyer IDs from candidates
        candidate_ids = [lawyer_id for lawyer_id, score in candidates]

        if show_sql:
            print(f"Semantic search returned {len(candidate_ids)} candidates")

        # Step 1.5: Keyword pre-filtering to reduce LLM calls
        filtered_ids = smart_filter_candidates(candidate_ids, query, db_path)

        if show_sql:
            print(f"Keyword filtering reduced to {len(filtered_ids)} candidates")

        # Step 2: LLM filtering for precise matching
        results = parallel_llm_filter(filtered_ids, query, db_path=db_path)

        if show_sql:
            print(f"LLM filtering returned {len(results)} matches")
            print("=" * 80)

        # Cache results before returning
        if use_cache:
            _query_cache.set(query, db_path, results)

    return results


def format_results(results: List[Dict[str, Any]], format_type: str = 'table') -> str:
    """
    Format results for output.
    
    Args:
        results: List of result dictionaries
        format_type: 'json' or 'table'
        
    Returns:
        Formatted string
    """
    if format_type == 'json':
        return json.dumps(results, indent=2)
    else:
        # Table format
        if not results:
            return "No results found."
        
        lines = [f"Found {len(results)} lawyer(s):", ""]
        for i, result in enumerate(results, 1):
            name = result.get('name', 'Unknown')
            url = result.get('url', '')
            lines.append(f"{i}. {name}")
            if url:
                lines.append(f"   {url}")
        
        return "\n".join(lines)


def dump_json(db_path: str = 'lawyers.db', output_file: str = 'lawyers_export.json'):
    """
    Export all lawyer data from database to JSON file.
    
    Args:
        db_path: Path to SQLite database
        output_file: Output JSON file path
    """
    conn = init_database(db_path)
    cursor = conn.cursor()
    
    # Get all lawyers with related data
    cursor.execute('''
        SELECT 
            l.id, l.url, l.name, l.email, l.phone, l.title, l.office_location, l.clerkship,
            GROUP_CONCAT(DISTINCT e.degree_type || '|' || COALESCE(e.year, '') || '|' || COALESCE(e.school_name, '') || '|' || COALESCE(e.school_normalized, '')) as educations,
            GROUP_CONCAT(DISTINCT p.practice_type) as practices,
            GROUP_CONCAT(DISTINCT ind.industry) as industries,
            GROUP_CONCAT(DISTINCT r.region) as regions,
            GROUP_CONCAT(DISTINCT lang.language) as languages
        FROM lawyers l
        LEFT JOIN educations e ON l.id = e.lawyer_id
        LEFT JOIN practices p ON l.id = p.lawyer_id
        LEFT JOIN industries ind ON l.id = ind.lawyer_id
        LEFT JOIN regions r ON l.id = r.lawyer_id
        LEFT JOIN languages lang ON l.id = lang.lawyer_id
        GROUP BY l.id
    ''')
    
    lawyers = []
    for row in cursor:
        lawyer = {
            'id': row['id'],
            'url': row['url'],
            'name': row['name'],
            'email': row['email'],
            'phone': row['phone'],
            'title': row['title'],
            'office_location': row['office_location'],
            'clerkship': row['clerkship'],
        }
        
        # Parse educations
        if row['educations']:
            educations = []
            for edu_str in row['educations'].split(','):
                parts = edu_str.split('|')
                if len(parts) >= 4:
                    educations.append({
                        'degree_type': parts[0] if parts[0] else None,
                        'year': int(parts[1]) if parts[1] else None,
                        'school_name': parts[2] if parts[2] else None,
                        'school_normalized': parts[3] if parts[3] else None,
                    })
            lawyer['educations'] = educations
        
        # Parse lists
        if row['practices']:
            lawyer['practices'] = row['practices'].split(',')
        if row['industries']:
            lawyer['industries'] = row['industries'].split(',')
        if row['regions']:
            lawyer['regions'] = row['regions'].split(',')
        if row['languages']:
            lawyer['languages'] = row['languages'].split(',')
        
        lawyers.append(lawyer)
    
    conn.close()
    
    # Write to JSON file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(lawyers, f, indent=2, ensure_ascii=False)
    
    print(f"Exported {len(lawyers)} lawyers to {output_file}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Davis Polk Lawyer Search System')
    parser.add_argument('query', nargs='?', help='Search query')
    parser.add_argument('--warm', action='store_true', help='Pre-build caches and indexes')
    parser.add_argument('--why', action='store_true', help='Show compiled SQL query and execution plan')
    parser.add_argument('--format', choices=['json', 'table'], default='table', help='Output format')
    parser.add_argument('--dump-json', metavar='FILE', help='Export all lawyer data to JSON file')
    parser.add_argument('--db', default='lawyers.db', help='Path to SQLite database')
    parser.add_argument('--scrape', action='store_true', help='Scrape and cache all lawyers')
    parser.add_argument('--store-html', action='store_true', help='Store raw HTML in database (gzipped)')
    parser.add_argument('--force', action='store_true', help='Force re-scraping even if lawyer exists')
    parser.add_argument('--cleanup-names', action='store_true', help='Clean up lawyers with invalid names (e.g., "Print this page")')
    parser.add_argument('--generate-embeddings', action='store_true', help='Generate embeddings for all lawyer experiences')
    parser.add_argument('--no-cache', action='store_true', help='Disable query result caching (useful for demos with diverse queries)')

    args = parser.parse_args()
    
    # Handle --warm flag
    if args.warm:
        print("Warming up database...")
        conn = init_database(args.db)
        create_indexes(conn)
        load_school_aliases(conn)
        conn.close()
        print("Database warmed up.")
        sys.exit(0)
    
    # Handle --dump-json flag
    if args.dump_json:
        dump_json(args.db, args.dump_json)
        sys.exit(0)
    
    # Handle --cleanup-names flag
    if args.cleanup_names:
        print("Cleaning up invalid names...")
        cleanup_bad_names(args.db)
        sys.exit(0)
    
    # Handle --generate-embeddings flag
    if args.generate_embeddings:
        print("Generating embeddings for all lawyers...")
        from embedding_generator import generate_embeddings_for_all_lawyers
        generate_embeddings_for_all_lawyers(args.db)
        sys.exit(0)
    
    # Handle --scrape flag
    if args.scrape:
        print("Scraping lawyers...")
        scrape_and_cache_lawyers(
            db_path=args.db,
            store_html=args.store_html,
            force_rescrape=args.force
        )
        sys.exit(0)
    
    # Handle query
    if args.query:
        # Single query mode
        use_cache = not args.no_cache
        results = main(args.query, args.db, args.why, args.format, use_cache)
        print(format_results(results, args.format))
    else:
        # Interactive query loop (Level 2)
        print("Davis Polk Lawyer Search System")
        print("Enter queries, or 'quit' to exit")
        print("=" * 80)

        while True:
            try:
                query = input("\nEnter your search query: ").strip()

                if not query:
                    continue

                if query.lower() in ['quit', 'exit', 'q']:
                    print("Goodbye!")
                    break

                use_cache = not args.no_cache
                results = main(query, args.db, args.why, args.format, use_cache)
                print(format_results(results, args.format))
                
            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}")
                import traceback
                traceback.print_exc()
    