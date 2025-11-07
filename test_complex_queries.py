#!/usr/bin/env python3
"""
Test suite for complex query functionality.
"""

import time
import json
from typing import List, Dict, Any
from main import main
from query_classifier import classify_query
from semantic_search import semantic_search
from embedding_generator import generate_embeddings_for_all_lawyers, extract_experience_text
from database import init_database
from scraping_utils import parse_page


class ComplexQueryTester:
    """Test suite for complex query functionality."""
    
    def __init__(self, db_path: str = 'lawyers.db'):
        self.db_path = db_path
        self.test_queries = [
            # Complex queries requiring semantic understanding
            {
                'query': 'lawyers who worked on a case for a TV network',
                'expected_keywords': ['CNN', 'NBC', 'Fox', 'ABC', 'CBS', 'television', 'broadcast', 'media'],
                'type': 'complex'
            },
            {
                'query': 'represented Fortune 500 companies in litigation',
                'expected_keywords': ['Fortune 500', 'litigation', 'lawsuit', 'dispute', 'court'],
                'type': 'complex'
            },
            {
                'query': 'experience with cryptocurrency regulations',
                'expected_keywords': ['crypto', 'bitcoin', 'blockchain', 'digital asset', 'SEC', 'CFTC'],
                'type': 'complex'
            },
            {
                'query': 'handled IPOs for tech companies',
                'expected_keywords': ['IPO', 'initial public offering', 'technology', 'tech', 'software'],
                'type': 'complex'
            },
            {
                'query': 'defended pharmaceutical companies',
                'expected_keywords': ['pharma', 'drug', 'FDA', 'clinical', 'patent'],
                'type': 'complex'
            },
            
            # Simple queries for comparison
            {
                'query': 'partners',
                'expected_keywords': [],
                'type': 'simple'
            },
            {
                'query': 'lawyers who speak Spanish',
                'expected_keywords': [],
                'type': 'simple'
            },
            {
                'query': 'graduated from Yale',
                'expected_keywords': [],
                'type': 'simple'
            }
        ]
    
    def test_query_classification(self) -> Dict[str, Any]:
        """Test query classification accuracy."""
        print("\nTesting Query Classification")
        print("=" * 80)
        
        results = {
            'total': len(self.test_queries),
            'correct': 0,
            'incorrect': []
        }
        
        for test_case in self.test_queries:
            query = test_case['query']
            expected_type = test_case['type']
            
            classified_type = classify_query(query)
            
            if classified_type == expected_type:
                results['correct'] += 1
                print(f"✓ '{query}' -> {classified_type}")
            else:
                results['incorrect'].append({
                    'query': query,
                    'expected': expected_type,
                    'actual': classified_type
                })
                print(f"✗ '{query}' -> {classified_type} (expected: {expected_type})")
        
        accuracy = results['correct'] / results['total'] * 100
        print(f"\nAccuracy: {accuracy:.1f}% ({results['correct']}/{results['total']})")
        
        return results
    
    def test_embedding_generation(self, sample_size: int = 5) -> Dict[str, Any]:
        """Test embedding generation for a sample of lawyers."""
        print("\nTesting Embedding Generation")
        print("=" * 80)
        
        conn = init_database(self.db_path)
        cursor = conn.cursor()
        
        # Get sample lawyers
        cursor.execute(f'SELECT id, url, name FROM lawyers LIMIT {sample_size}')
        lawyers = cursor.fetchall()
        
        results = {
            'total': len(lawyers),
            'with_experience': 0,
            'embeddings_generated': 0,
            'errors': []
        }
        
        for lawyer in lawyers:
            try:
                # Extract experience
                raw_html = parse_page(lawyer['url'])
                experience = extract_experience_text(raw_html)
                
                if experience:
                    results['with_experience'] += 1
                    print(f"✓ {lawyer['name']}: Found experience ({len(experience)} chars)")
                    
                    # Check if embedding exists
                    cursor.execute(
                        'SELECT COUNT(*) as count FROM experience_embeddings WHERE lawyer_id = ?',
                        (lawyer['id'],)
                    )
                    if cursor.fetchone()['count'] > 0:
                        results['embeddings_generated'] += 1
                else:
                    print(f"- {lawyer['name']}: No experience section found")
                    
            except Exception as e:
                results['errors'].append({
                    'lawyer': lawyer['name'],
                    'error': str(e)
                })
                print(f"✗ {lawyer['name']}: Error - {e}")
        
        conn.close()
        
        print(f"\nResults:")
        print(f"  With experience: {results['with_experience']}/{results['total']}")
        print(f"  Embeddings stored: {results['embeddings_generated']}/{results['with_experience']}")
        
        return results
    
    def test_semantic_search(self) -> Dict[str, Any]:
        """Test semantic search functionality."""
        print("\nTesting Semantic Search")
        print("=" * 80)
        
        results = {
            'queries_tested': 0,
            'queries_with_results': 0,
            'average_candidates': 0,
            'timings': []
        }
        
        complex_queries = [q for q in self.test_queries if q['type'] == 'complex']
        
        for test_case in complex_queries[:3]:  # Test first 3 to save time
            query = test_case['query']
            print(f"\nQuery: '{query}'")
            
            start_time = time.time()
            candidates = semantic_search(query, k=20, db_path=self.db_path)
            search_time = time.time() - start_time
            
            results['queries_tested'] += 1
            results['timings'].append(search_time)
            
            if candidates:
                results['queries_with_results'] += 1
                results['average_candidates'] += len(candidates)
                
                print(f"  Found {len(candidates)} candidates in {search_time:.2f}s")
                print(f"  Top 3 scores: {[f'{score:.4f}' for _, score in candidates[:3]]}")
            else:
                print(f"  No candidates found")
        
        if results['queries_tested'] > 0:
            results['average_candidates'] /= results['queries_tested']
            avg_time = sum(results['timings']) / len(results['timings'])
            print(f"\nAverage search time: {avg_time:.2f}s")
        
        return results
    
    def test_end_to_end(self, limit_queries: int = 2) -> Dict[str, Any]:
        """Test end-to-end complex query processing."""
        print("\nTesting End-to-End Complex Queries")
        print("=" * 80)
        
        results = {
            'queries': [],
            'total_time': 0,
            'success_rate': 0
        }
        
        complex_queries = [q for q in self.test_queries if q['type'] == 'complex']
        
        for test_case in complex_queries[:limit_queries]:
            query = test_case['query']
            print(f"\nTesting: '{query}'")
            
            start_time = time.time()
            
            try:
                # Run the full query
                matches = main(query, self.db_path, show_sql=False)
                query_time = time.time() - start_time
                
                query_result = {
                    'query': query,
                    'time': query_time,
                    'matches': len(matches),
                    'success': True,
                    'results': matches[:3] if matches else []  # First 3 results
                }
                
                print(f"  Completed in {query_time:.2f}s")
                print(f"  Found {len(matches)} matches")
                
                if matches:
                    print("  Sample results:")
                    for i, lawyer in enumerate(matches[:3]):
                        print(f"    {i+1}. {lawyer['name']}")
                
            except Exception as e:
                query_time = time.time() - start_time
                query_result = {
                    'query': query,
                    'time': query_time,
                    'matches': 0,
                    'success': False,
                    'error': str(e)
                }
                print(f"  Error: {e}")
            
            results['queries'].append(query_result)
            results['total_time'] += query_time
        
        # Calculate success rate
        successful = sum(1 for q in results['queries'] if q['success'])
        results['success_rate'] = successful / len(results['queries']) * 100 if results['queries'] else 0
        
        print(f"\nSummary:")
        print(f"  Total queries: {len(results['queries'])}")
        print(f"  Success rate: {results['success_rate']:.1f}%")
        print(f"  Total time: {results['total_time']:.2f}s")
        print(f"  Average time: {results['total_time']/len(results['queries']):.2f}s" if results['queries'] else "N/A")
        
        return results
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all tests and return comprehensive results."""
        print("\n" + "=" * 80)
        print("COMPLEX QUERY TEST SUITE")
        print("=" * 80)
        
        all_results = {
            'classification': self.test_query_classification(),
            'embeddings': self.test_embedding_generation(),
            'semantic_search': self.test_semantic_search(),
            'end_to_end': self.test_end_to_end()
        }
        
        print("\n" + "=" * 80)
        print("TEST SUITE COMPLETE")
        print("=" * 80)
        
        # Save results to file
        with open('test_results.json', 'w') as f:
            json.dump(all_results, f, indent=2)
        print("\nDetailed results saved to test_results.json")
        
        return all_results


def check_prerequisites(db_path: str = 'lawyers.db') -> bool:
    """Check if system is ready for testing."""
    conn = init_database(db_path)
    cursor = conn.cursor()
    
    # Check if we have embeddings
    cursor.execute('SELECT COUNT(*) as count FROM experience_embeddings')
    embedding_count = cursor.fetchone()['count']
    
    # Check if we have lawyers
    cursor.execute('SELECT COUNT(*) as count FROM lawyers')
    lawyer_count = cursor.fetchone()['count']
    
    conn.close()
    
    print(f"System Status:")
    print(f"  Lawyers in database: {lawyer_count}")
    print(f"  Experience embeddings: {embedding_count}")
    
    if embedding_count == 0:
        print("\n⚠️  Warning: No embeddings found!")
        print("Run 'python main.py --generate-embeddings' to create embeddings first.")
        return False
    
    return True


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Test complex query functionality')
    parser.add_argument('--db', default='lawyers.db', help='Database path')
    parser.add_argument('--quick', action='store_true', help='Run quick tests only')
    
    args = parser.parse_args()
    
    # Check prerequisites
    if not check_prerequisites(args.db):
        print("\nPlease generate embeddings before running tests.")
        exit(1)
    
    # Run tests
    tester = ComplexQueryTester(args.db)
    
    if args.quick:
        print("\nRunning quick tests...")
        tester.test_query_classification()
        tester.test_semantic_search()
    else:
        tester.run_all_tests()
