"""
Semantic search module for finding lawyers based on experience similarity.
"""

import sqlite3
import numpy as np
import pickle
from typing import List, Tuple, Dict, Any
from database import init_database
from llm_utils import get_embedding, EMBEDDING_MODEL_SMALL
from embedding_generator import load_embedding


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Calculate cosine similarity between two vectors.
    
    Args:
        a: First vector
        b: Second vector
        
    Returns:
        Cosine similarity score between -1 and 1
    """
    # Ensure vectors are 1D
    a = a.flatten()
    b = b.flatten()
    
    # Calculate cosine similarity
    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    return dot_product / (norm_a * norm_b)


def check_embeddings_exist(db_path: str = 'lawyers.db') -> Tuple[bool, int]:
    """
    Check if embeddings exist in the database.
    
    Args:
        db_path: Path to the database
        
    Returns:
        Tuple of (embeddings_exist: bool, count: int)
    """
    conn = init_database(db_path)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) as count FROM experience_embeddings')
    row = cursor.fetchone()
    count = row['count'] if row else 0
    
    conn.close()
    return count > 0, count


def semantic_search(query: str, k: int = 50, db_path: str = 'lawyers.db') -> List[Tuple[int, float]]:
    """
    Perform semantic search to find lawyers with relevant experience.
    
    Args:
        query: The search query
        k: Number of top results to return
        db_path: Path to the database
        
    Returns:
        List of (lawyer_id, similarity_score) tuples, sorted by relevance
        
    Raises:
        ValueError: If no embeddings exist in the database
    """
    conn = init_database(db_path)
    cursor = conn.cursor()
    
    # Check if embeddings exist
    cursor.execute('SELECT COUNT(*) as count FROM experience_embeddings')
    row = cursor.fetchone()
    embedding_count = row['count'] if row else 0
    
    if embedding_count == 0:
        conn.close()
        raise ValueError(
            "No embeddings found in database. Please generate embeddings first by running:\n"
            "  python main.py --generate-embeddings"
        )
    
    # Generate embedding for the query
    query_embedding = get_embedding([query], size=EMBEDDING_MODEL_SMALL)[0]
    query_embedding = np.array(query_embedding, dtype=np.float32)
    
    # Get all lawyers with embeddings
    cursor.execute('''
        SELECT ee.lawyer_id, ee.embedding, l.name
        FROM experience_embeddings ee
        JOIN lawyers l ON ee.lawyer_id = l.id
    ''')
    
    results = []
    
    for row in cursor:
        lawyer_id = row['lawyer_id']
        embedding_blob = row['embedding']
        
        if embedding_blob:
            # Load embedding
            lawyer_embedding = pickle.loads(embedding_blob)
            
            # Calculate similarity
            similarity = cosine_similarity(query_embedding, lawyer_embedding)
            
            results.append((lawyer_id, similarity))
    
    conn.close()
    
    # Sort by similarity (descending) and return top k
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:k]


def get_lawyer_experience_preview(lawyer_id: int, db_path: str = 'lawyers.db') -> Dict[str, Any]:
    """
    Get a preview of a lawyer's experience for debugging.
    
    Args:
        lawyer_id: ID of the lawyer
        db_path: Path to the database
        
    Returns:
        Dictionary with lawyer info and experience preview
    """
    conn = init_database(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT l.name, l.url, ee.content
        FROM lawyers l
        LEFT JOIN experience_embeddings ee ON l.id = ee.lawyer_id
        WHERE l.id = ?
    ''', (lawyer_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        content = row['content'] or 'No experience data'
        # Truncate content for preview
        if len(content) > 200:
            content = content[:200] + '...'
            
        return {
            'id': lawyer_id,
            'name': row['name'],
            'url': row['url'],
            'experience_preview': content
        }
    
    return None


def explain_search_results(query: str, results: List[Tuple[int, float]], 
                          db_path: str = 'lawyers.db', top_n: int = 10) -> None:
    """
    Print detailed explanation of search results for debugging.
    
    Args:
        query: The search query
        results: List of (lawyer_id, similarity_score) tuples
        db_path: Path to the database
        top_n: Number of results to explain
    """
    print(f"\nSemantic Search Results for: '{query}'")
    print("=" * 80)
    
    for i, (lawyer_id, score) in enumerate(results[:top_n]):
        info = get_lawyer_experience_preview(lawyer_id, db_path)
        if info:
            print(f"\n{i+1}. {info['name']} (Score: {score:.4f})")
            print(f"   URL: {info['url']}")
            print(f"   Experience: {info['experience_preview']}")
    
    print(f"\nTotal results: {len(results)}")


if __name__ == '__main__':
    # Test semantic search
    test_queries = [
        "lawyers who worked on a case for a TV network",
        "represented tech companies in IPO",
        "experience with cryptocurrency",
        "defended banks in litigation",
        "mergers and acquisitions in healthcare",
    ]
    
    print("Testing Semantic Search")
    print("-" * 80)
    
    for query in test_queries:
        print(f"\nQuery: {query}")
        
        try:
            # Perform search
            results = semantic_search(query, k=5)
            
            if results:
                print(f"Found {len(results)} results")
                # Show top 3
                for i, (lawyer_id, score) in enumerate(results[:3]):
                    info = get_lawyer_experience_preview(lawyer_id)
                    if info:
                        print(f"  {i+1}. {info['name']} (Score: {score:.4f})")
            else:
                print("No results found (no embeddings in database)")
                
        except Exception as e:
            print(f"Error: {e}")
    
    # Detailed test with one query
    if test_queries:
        print("\n" + "=" * 80)
        print("Detailed results for first query:")
        results = semantic_search(test_queries[0], k=10)
        explain_search_results(test_queries[0], results)
