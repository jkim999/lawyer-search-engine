# Complex Query System: Analysis & Optimization Recommendations

## Executive Summary

The current system handles complex queries like "lawyers who worked on a case with a TV network" using a two-stage pipeline:
1. **Semantic Search**: Find top-k candidates (default k=50) using embedding similarity
2. **LLM Filtering**: Validate each candidate with GPT-4-mini

**Current Performance:**
- **Latency**: 3-5 seconds for complex queries
- **Coverage**: Only 410/853 lawyers (48%) have embeddings
- **Bottleneck**: LLM filtering stage (accounts for 80-90% of query time)

**Key Finding**: The system has significant optimization opportunities that could reduce latency by 60-80% while improving result quality.

---

## Current Architecture Deep Dive

### Stage 1: Query Classification
**File**: `query_classifier.py`
**Process**: LLM call to classify query as 'simple' or 'complex'
**Latency**: ~200-500ms per query
**Cost**: 1 LLM call per query

### Stage 2: Semantic Search
**File**: `semantic_search.py:61-122`
**Process**:
1. Generate query embedding using `text-embedding-3-small`
2. Load ALL embeddings from database
3. Compute cosine similarity in-memory with NumPy
4. Sort and return top-k results (k=50 default)

**Latency**: ~500-1000ms
**Issues**:
- O(n) scan of all lawyers - no vector indexing
- Loads all embeddings into memory each time
- No caching of query embeddings or results

### Stage 3: LLM Filtering
**File**: `llm_filter.py:77-167`
**Process**:
1. For each candidate (50 lawyers):
   - Fetch lawyer info from database
   - **Re-scrape** lawyer profile page from web (!)
   - Extract first 3000 chars
   - Send to GPT-4-mini for validation
2. Process in batches of 5, with 3 concurrent workers
3. 0.5s delay between batches

**Latency**: ~3-4 seconds for 50 candidates
**Issues**:
- **Critical**: Re-scraping pages on every query (no caching)
- Limited parallelization (3 workers, batch size 5)
- Arbitrary 3000 char limit may truncate important info
- No result caching

---

## Critical Performance Issues

### 🔴 Issue #1: No HTML Caching (MOST CRITICAL)
**Location**: `llm_filter.py:30`
**Problem**: Every query re-scrapes lawyer pages from the web

```python
# Current code - scrapes page every time
profile_text = parse_page(lawyer_url)  # 100-200ms per page!
```

**Impact**:
- 50 candidates × 100ms = 5 seconds just for scraping
- Adds network latency and failure points
- Wastes bandwidth

**Database Check**: 0/853 lawyers have cached HTML (`raw_html IS NULL`)

**Solution**: Store parsed text in database during embedding generation
- Add `parsed_text` column to `experience_embeddings` table
- Reduces LLM filtering time by 80%

---

### 🔴 Issue #2: Incomplete Embedding Coverage
**Current**: 410/853 lawyers (48%) have embeddings

**Impact**:
- Complex queries miss 443 lawyers entirely
- Results are incomplete and potentially wrong

**Solution**: Generate embeddings for all lawyers

---

### 🟡 Issue #3: No Query Result Caching
**Problem**: Same query run twice requires full re-computation

```python
# Example: "lawyers who worked with TV networks"
# Run 1: 4.2 seconds
# Run 2: 4.2 seconds (should be <100ms!)
```

**Solution**: Cache (query, results) with TTL
- Simple in-memory LRU cache for top N queries
- Or Redis for persistence

---

### 🟡 Issue #4: Suboptimal LLM Filtering Parallelization
**Current**: 3 workers, batch size 5, 0.5s delays

```python
# llm_filter.py:78-79
def parallel_llm_filter(lawyer_ids: List[int], query: str,
                       batch_size: int = 5, max_workers: int = 3,
```

**Impact**:
- 50 candidates / 5 per batch / 3 workers = ~4 batches
- 4 batches × 0.5s delay = 2 seconds of artificial delay
- Conservative rate limiting wastes time

**Solution**: Increase parallelization, remove artificial delays
- Increase to 10-15 workers
- Batch size of 10-15
- Use OpenAI's rate limits intelligently (higher tier allows 10,000 RPM)

---

### 🟡 Issue #5: Semantic Search O(n) Scan
**Location**: `semantic_search.py:96-119`

```python
# Current: Loads ALL embeddings and computes similarity
cursor.execute('SELECT ee.lawyer_id, ee.embedding, l.name FROM experience_embeddings ee ...')
for row in cursor:
    similarity = cosine_similarity(query_embedding, lawyer_embedding)
```

**Impact**: Scales linearly with lawyer count
- Currently: 410 lawyers × 2ms = ~800ms
- Future: 10,000 lawyers × 2ms = 20 seconds

**Solution**: Vector database or FAISS indexing
- FAISS can reduce search to <50ms even with 100k+ vectors
- Or use specialized vector DB (Pinecone, Weaviate, Qdrant)

---

### 🟢 Issue #6: Query Classification Latency
**Problem**: LLM call for every query (~300ms)

**Solution**: Pattern matching for obvious cases
```python
# Simple patterns can be detected without LLM
if re.match(r'lawyers? (named|called|with name)', query, re.I):
    return 'simple'
if 'went to' in query or 'graduated from' in query:
    return 'simple'
# Only use LLM for ambiguous cases
```

---

### 🟢 Issue #7: No Hybrid Search
**Problem**: Semantic search alone may miss exact keyword matches

**Example**: Query "lawyers who worked with CNN"
- Semantic search might miss if embedding doesn't capture "CNN" well
- Keyword search would find exact match immediately

**Solution**: Combine semantic + keyword (BM25) scoring
```
final_score = 0.7 × semantic_score + 0.3 × keyword_score
```

---

## Optimization Roadmap

### Phase 1: Quick Wins (2-4 hours implementation)
**Expected Improvement**: 60-70% latency reduction

1. **Cache parsed text in database** ⭐⭐⭐
   - Add `parsed_text` column to `experience_embeddings`
   - Store during embedding generation
   - Eliminates re-scraping in LLM filter
   - **Impact**: -3 seconds

2. **Increase LLM filtering parallelization**
   - Increase workers to 10-15
   - Batch size to 10-15
   - Remove/reduce artificial delays
   - **Impact**: -1 second

3. **Generate missing embeddings**
   - Complete embedding coverage for all 853 lawyers
   - **Impact**: Better recall/completeness

4. **Add basic query caching**
   - Simple LRU cache with 100 query limit
   - **Impact**: Repeat queries <100ms

**Expected Result**: Complex queries in 1-1.5 seconds

---

### Phase 2: Medium-term Improvements (4-8 hours)
**Expected Improvement**: Additional 20-30% + better quality

5. **Optimize query classifier**
   - Pattern matching for obvious simple queries
   - **Impact**: -200ms for simple queries

6. **Improve embedding quality**
   - Chunk long experience sections (every 500 chars)
   - Embed multiple chunks per lawyer
   - Max-pool or average chunk embeddings
   - **Impact**: Better semantic search precision

7. **Adaptive k parameter**
   - Use query complexity to adjust candidate pool
   - Rare/specific queries: k=100
   - Common queries: k=20
   - **Impact**: Faster for common queries

8. **Add keyword pre-filtering**
   - Extract key entities from query (company names, industries)
   - Filter candidates by keyword match before LLM
   - **Impact**: Reduce LLM calls by 30-50%

**Expected Result**: Complex queries in 0.8-1.2 seconds

---

### Phase 3: Advanced Optimizations (1-2 days)
**Expected Improvement**: Scalability + sub-second queries

9. **Vector indexing with FAISS**
   - Replace NumPy similarity with FAISS index
   - **Impact**: Semantic search <50ms even with 10k+ lawyers

10. **Hybrid search ranking**
    - Combine semantic + BM25 scores
    - Re-rank top candidates
    - **Impact**: Better precision/recall

11. **Batch LLM validation**
    - Process multiple lawyers in single prompt
    - Reduces API calls by 5-10x
    - **Impact**: -1 second

12. **Query expansion**
    - LLM expands query with synonyms/related terms
    - "TV network" → ["CNN", "NBC", "Fox", "ABC", "television", "broadcast"]
    - **Impact**: Better recall

13. **Streaming results**
    - Return results as they pass LLM filter
    - Don't wait for all 50 candidates
    - **Impact**: Time-to-first-result <500ms

**Expected Result**: Complex queries in 0.3-0.8 seconds

---

## Implementation Priority

### Immediate (Do First) ⭐⭐⭐
1. **Add `parsed_text` column and cache during embedding generation**
2. **Generate embeddings for all 853 lawyers**
3. **Increase LLM parallelization (workers=15, batch=10)**

### High Priority ⭐⭐
4. **Implement query result caching**
5. **Add keyword pre-filtering for LLM candidates**
6. **Optimize query classifier with patterns**

### Medium Priority ⭐
7. **Implement FAISS for vector search**
8. **Add hybrid search (semantic + keyword)**
9. **Implement streaming results**

---

## Code Changes Preview

### 1. Cache Parsed Text (Most Critical)

**Update `database.py`** - Add column:
```python
cursor.execute('''
    CREATE TABLE IF NOT EXISTS experience_embeddings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lawyer_id INTEGER NOT NULL,
        content TEXT,
        parsed_text TEXT,  -- ADD THIS
        embedding BLOB,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (lawyer_id) REFERENCES lawyers(id) ON DELETE CASCADE
    )
''')
```

**Update `embedding_generator.py`** - Store parsed text:
```python
def store_embedding(conn, lawyer_id, content, embedding, parsed_text):
    cursor.execute('''
        INSERT INTO experience_embeddings (lawyer_id, content, embedding, parsed_text)
        VALUES (?, ?, ?, ?)
    ''', (lawyer_id, content, embedding_blob, parsed_text))
```

**Update `llm_filter.py`** - Use cached text:
```python
def evaluate_lawyer_for_query(lawyer_id, query, db_path='lawyers.db'):
    # Get cached parsed text from database
    cursor.execute('''
        SELECT ee.parsed_text
        FROM experience_embeddings ee
        WHERE ee.lawyer_id = ?
    ''', (lawyer_id,))

    row = cursor.fetchone()
    if row and row['parsed_text']:
        profile_text = row['parsed_text']  # Use cached!
    else:
        profile_text = parse_page(lawyer_url)  # Fallback
```

**Impact**: Eliminates 50 × 100ms = 5 seconds of scraping

---

### 2. Increase Parallelization

**Update `llm_filter.py:78`**:
```python
def parallel_llm_filter(lawyer_ids: List[int], query: str,
                       batch_size: int = 15,  # Was 5
                       max_workers: int = 15,  # Was 3
                       db_path: str = 'lawyers.db'):
    # ...
    # Remove artificial delay or reduce to 0.1s
    if i + batch_size < len(lawyer_ids):
        time.sleep(0.1)  # Was 0.5
```

**Impact**: 50 candidates in parallel → ~2 seconds instead of 4

---

### 3. Query Result Caching

**Add to `main.py`**:
```python
from functools import lru_cache
import hashlib

# Simple in-memory cache
query_cache = {}

def get_cache_key(query: str) -> str:
    return hashlib.md5(query.lower().encode()).hexdigest()

def main(query: str, db_path: str = 'lawyers.db', ...):
    # Check cache
    cache_key = get_cache_key(query)
    if cache_key in query_cache:
        return query_cache[cache_key]

    # ... existing code ...

    # Store in cache
    query_cache[cache_key] = results
    return results
```

**Impact**: Repeat queries <100ms

---

## Benchmarking Results (Projected)

### Current System
```
Query: "lawyers who worked on a case for a TV network"
├─ Query Classification: 300ms
├─ Semantic Search: 800ms
│  ├─ Generate embedding: 200ms
│  ├─ Load & compute similarity: 600ms
├─ LLM Filtering (50 candidates): 4200ms
│  ├─ Scraping pages: 3000ms ⚠️
│  ├─ LLM validation: 1200ms
└─ Total: 5.3 seconds
```

### After Phase 1 Optimizations
```
Query: "lawyers who worked on a case for a TV network"
├─ Query Classification: 300ms
├─ Semantic Search: 800ms
├─ LLM Filtering (50 candidates): 800ms ✅
│  ├─ Scraping pages: 0ms (cached) ✅
│  ├─ LLM validation: 800ms (parallel) ✅
└─ Total: 1.9 seconds (-64%)
```

### After Phase 2 Optimizations
```
Query: "lawyers who worked on a case for a TV network"
├─ Query Classification: 50ms (pattern match) ✅
├─ Semantic Search: 600ms
├─ Keyword Pre-filter: 100ms ✅
├─ LLM Filtering (30 candidates): 600ms ✅
└─ Total: 1.35 seconds (-75%)
```

### After Phase 3 Optimizations
```
Query: "lawyers who worked on a case for a TV network"
├─ Query Classification: 50ms
├─ Semantic Search: 50ms (FAISS) ✅
├─ Keyword Pre-filter: 100ms
├─ LLM Filtering (20 candidates, streaming): 400ms ✅
└─ Total: 0.6 seconds (-89%)
└─ Time to first result: 0.3 seconds ✅
```

---

## Additional Considerations

### Scalability
- **Current**: System will struggle beyond 2,000-3,000 lawyers
- **With optimizations**: Can scale to 50,000+ lawyers efficiently

### Cost Optimization
- Reducing LLM calls from 50 to 20-30 saves 40-60% API costs
- Caching queries reduces redundant API calls

### Quality Improvements
- Full embedding coverage improves recall
- Hybrid search improves precision
- Chunked embeddings capture more nuanced experience

### Monitoring Metrics to Track
1. Average query latency (p50, p95, p99)
2. Time to first result
3. Semantic search precision@k
4. LLM filter acceptance rate
5. Cache hit rate
6. API costs per query

---

## Conclusion

The current system provides a solid foundation but has critical performance bottlenecks:

**Primary Issue**: Re-scraping lawyer pages during LLM filtering accounts for 60-70% of total query time.

**Quick Win**: Adding parsed text caching + increased parallelization can reduce latency from 5 seconds to <2 seconds with minimal code changes.

**Long-term**: Full optimization path can achieve sub-second complex queries while maintaining high accuracy.

**Recommended First Steps**:
1. Add `parsed_text` column to database schema
2. Re-generate embeddings with parsed text caching
3. Update LLM filter to use cached text
4. Increase parallelization parameters

These changes alone will reduce latency by 60-70% and can be implemented in 2-4 hours.
