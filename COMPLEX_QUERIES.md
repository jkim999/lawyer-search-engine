# Complex Query Support Documentation

## Overview

The system now supports two types of queries:

1. **Simple Queries**: Direct database lookups (names, schools, languages, etc.)
2. **Complex Queries**: Semantic searches requiring understanding of context and relationships

## Architecture

### Query Classification
The system automatically classifies queries using an LLM to determine the appropriate processing pipeline.

**Simple Query Examples:**
- "lawyers named John"
- "partners who went to Yale"
- "lawyers who speak Spanish"
- "graduated after 2015"

**Complex Query Examples:**
- "lawyers who worked on a case for a TV network"
- "represented Fortune 500 companies in litigation"
- "experience with cryptocurrency regulations"
- "handled IPOs for tech companies"

### Processing Pipeline

#### Simple Queries
1. Parse query into AST using pattern matching
2. Compile to SQL query
3. Execute against database
4. Return results

#### Complex Queries
1. **Semantic Search**: Generate query embedding and find top-k similar lawyer profiles
2. **LLM Filtering**: Validate each candidate using LLM to ensure they match the query
3. Return filtered results with reasoning

## Setup Instructions

### 1. Initialize Database
```bash
python main.py --warm
```

### 2. Generate Experience Embeddings
```bash
python main.py --generate-embeddings
```
This will:
- Extract experience sections from all lawyer profiles
- Generate embeddings using OpenAI's text-embedding-ada-002
- Store embeddings in the database

**Note**: This process requires API calls for each lawyer and may take 10-20 minutes for ~850 lawyers.

### 3. Test the System
```bash
python test_complex_queries.py
```

## Usage Examples

### Command Line
```bash
# Simple query
python main.py "partners who went to Harvard"

# Complex query
python main.py "lawyers who worked on a case for a TV network"

# Show query processing details
python main.py "experience with streaming platforms" --why
```

### Python API
```python
from main import main

# Simple query
results = main("tax lawyers in London")

# Complex query  
results = main("defended pharmaceutical companies in patent litigation")

for lawyer in results:
    print(f"{lawyer['name']} - {lawyer['url']}")
```

## Performance Characteristics

### Latency
- **Simple queries**: < 100ms
- **Complex queries**: 3-5 seconds (depending on candidates)

### Accuracy
- **Simple queries**: 100% precision (exact matching)
- **Complex queries**: High precision through LLM validation

### Scalability
- Semantic search scales well with vector indexing
- LLM filtering is the bottleneck (can be optimized with caching)

## Technical Details

### Embedding Storage
- Model: text-embedding-ada-002 (1536 dimensions)
- Storage: SQLite BLOB with pickle serialization
- Index: B-tree index on lawyer_id for fast lookups

### Semantic Search
- Algorithm: Cosine similarity
- Candidates: Top 50 by default (configurable)
- Implementation: NumPy-based for simplicity

### LLM Filtering
- Model: GPT-4-mini for efficiency
- Parallelization: 3 concurrent threads, batch size 5
- Rate limiting: 0.5s delay between batches

## Troubleshooting

### No results for complex queries
1. Check if embeddings are generated: 
   ```sql
   SELECT COUNT(*) FROM experience_embeddings;
   ```
2. Regenerate embeddings if needed:
   ```bash
   python main.py --generate-embeddings
   ```

### Slow performance
1. Reduce candidate pool size in `semantic_search()`
2. Increase parallelization in `parallel_llm_filter()`
3. Implement result caching for common queries

### API rate limits
1. Reduce batch_size in `parallel_llm_filter()`
2. Increase delay between batches
3. Implement exponential backoff for retries

## Future Enhancements

1. **Query Expansion**: Use LLM to expand queries with synonyms and related terms
2. **Hybrid Scoring**: Combine vector similarity with keyword matching
3. **Caching Layer**: Cache embeddings and LLM responses
4. **Feedback Loop**: Learn from user interactions to improve rankings
5. **Multi-hop Reasoning**: Support queries requiring multiple inference steps
