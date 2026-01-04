Architecture

Overview: Scrapes data, storng simple info (name, school, etc.) in SQL db and also using OpenAI embedding model for embeddings. Takes query and classifies into simple or complex. If simple do lookup in db, if complex, semantic search then pre-filter by keyword and then validate.

Two-Stage Query Pipeline
1. Query Classification

Fast regex pattern matching (80% of queries, <1ms)
LLM fallback for ambiguous cases
Routes to Simple or Complex path
2A. Simple Query Path (SQL)

Query → Parser → SQL → Results
Direct database lookups on indexed fields
Example: "senior counsel" → WHERE title = 'Senior Counsel'
2B. Complex Query Path (Semantic + LLM)

Query → Semantic Search → Keyword Filter → LLM Validation → Results
Semantic Search: OpenAI embeddings (text-embedding-3-small), cosine similarity
Keyword Filter: Extract entities, pre-filter by keyword presence (40-60% reduction)
LLM Validation: GPT-4-mini parallel processing (15 workers)
Data Storage (SQLite)


# NOTES
- (Most?) lawyer profiles do not have graduation date
- If for some reason db is missing or embeddings are gone, do 
    "python main.py --scrape"

