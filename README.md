# Davis Polk Lawyer Query Challenge

## Introduction

Davis Polk is a big law firm with ~1000 lawyers. Here is their website: https://www.davispolk.com/

The goal is to develop a tool that can search for lawyers on their website with extreme specificity.

## Task Description

We want to create a program that can query the lawyers on the Davis Polk website and filter them based on a specific query.

### Example queries that you should be able to support:
- Lawyers named David
- Lawyers who went to Yale
- Lawyers who worked on a case with a TV network
- Lawyers who clerked for the Supreme Court
- Lawyers who graduated law school after 2015
- Lawyers who have represented pharmaceutical companies
... and so on.

## Constraints
- Latency is **extremely** important. Not only time until all results are returned, but also time until the first result is returned.
- You must be able to query multiple queries back-to-back quickly.

## Level 1: Support one query

Your task is to write a program that returns a list of all lawyers who have **worked on a case with a TV network.**

## Level 2: Support multiple queries

You now have a while loop, where you can keep querying the program with new queries.

## Level 3: Latency optimizations

For example, "lawyers who went to Yale" is a much simpler query than "lawyers who worked on a case for a TV network". It should thus be faster.

Consider how embeddings could be used. Consider how keywords/keyword ranking could be used.

Extensions:
- Hybrid search
- Hybrid search -> Reranker model (like Cohere)

### Expected Output
Your program should produce a list or file containing the names and relevant information of lawyers who meet the criteria.

## Setup and Running the Code

1. Clone this repository to your local machine.
2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the main program:
   ```
   python main.py
   ```

## Requirements and Constraints

- Use Python for your implementation.
- You may use any libraries listed in the `requirements.txt` file.
- Feel free to use Cursor, ChatGPT, internet, etc.
- In fact, please use Cursor. This will make it much faster for you to build this
- Efficiency and latency are extremely important.

## Ideas of directions to go in
- Make the prompt better. Create benchmarks, test it, etc.
- Pre-process the profiles (convert to JSON maybe, clean the useless text)
- Pre-process the prompts

## Miscellaneous
I made an OpenAI key just for this interview with a pretty low daily limit. If you run out of credits, feel free to reach out to me at david@noon.ai, and I'll try to respond ASAP.

Also, feel free to use any other LLM API. Gemini 2.5 Flash is **extremely** good and very cheap. I just used OpenAI for this assignment for the sake of simplicity.

## Provided Files

- `README.md`: This file, containing challenge instructions.
- `requirements.txt`: List of required Python packages.
- `main.py`: The main script to run your program.
- `llm_utils.py`: Utility functions for working with language models (if applicable).
- `scraping_utils.py`: Utility functions for web scraping.
- `lawyers.csv`: A CSV file containing initial lawyer data (if provided).

Good luck! 🚀