# Davis Polk Lawyer Search Engine

A high-performance search tool for querying lawyers on the Davis Polk website with natural language queries and advanced filtering capabilities.
## Overview
Davis Polk & Wardwell LLP is a prestigious international law firm with approximately 1,000 lawyers. This project provides an intelligent search interface to query their lawyer directory using natural language, supporting complex filters and criteria.
Website: https://www.davispolk.com/

## Features

Natural Language Queries: Search using conversational language instead of complex filters

Complex Criteria Support: Filter by education, case history, clerkships, practice areas, and more
Low Latency: Optimized for fast response times with streaming results

Multi-Query Support: Handle multiple consecutive queries efficiently
Query Complexity Detection: Simple queries return faster than complex ones

Embedding-Based Search: Semantic similarity for efficient matching

Keyword Ranking: Fast filtering using keyword extraction

Hybrid Search: Combination of keyword and semantic search

## Example Queries
The tool supports a wide range of search criteria:

- "Lawyers named David"
- "Lawyers who went to Yale"
- "Lawyers who worked on a case with a TV network"
- "Lawyers who clerked for the Supreme Court"
- "Lawyers who graduated law school after 2015"
- "Lawyers who have represented pharmaceutical companies"


## Installation

Clone the repository

Install dependencies

bash   pip install -r requirements.txt

Set up API keys (if required)

bash   export OPENAI_KEY="your-api-key-here"
Usage
Run the main program:
bashpython main.py
The program will prompt you to enter search queries. Type your query in natural language and press Enter.



Search Methods: Embeddings, keyword extraction, hybrid approaches
