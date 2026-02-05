#!/usr/bin/env python3
"""
Semantic search across embedded memories.

Usage:
    python semantic-search.py "what did we discuss about the app?"
    python semantic-search.py "I)ruid's health" --limit 10
"""

import os
import sys
import json
import argparse
from pathlib import Path
import psycopg2
import openai

EMBEDDING_MODEL = "text-embedding-3-small"
DB_NAME = "nova_memory"

def get_openai_client():
    """Get OpenAI client with API key."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        config_path = Path.home() / ".clawdbot" / "clawdbot.json"
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
                api_key = config.get("skills", {}).get("entries", {}).get("openai-image-gen", {}).get("apiKey")
    
    if not api_key:
        print("Error: No OpenAI API key found", file=sys.stderr)
        sys.exit(1)
    
    return openai.OpenAI(api_key=api_key)

def get_embedding(client, text):
    """Get embedding vector from OpenAI."""
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text
    )
    return response.data[0].embedding

def search(query, limit=5, threshold=0.5):
    """Search memories semantically."""
    conn = psycopg2.connect(dbname=DB_NAME, host="localhost", user="nova")
    client = get_openai_client()
    
    # Get query embedding
    query_embedding = get_embedding(client, query)
    
    # Search using pgvector
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            source_type,
            source_id,
            content,
            1 - (embedding <=> %s::vector) AS similarity
        FROM memory_embeddings
        WHERE 1 - (embedding <=> %s::vector) > %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """, (query_embedding, query_embedding, threshold, query_embedding, limit))
    
    results = cur.fetchall()
    conn.close()
    
    return results

def main():
    parser = argparse.ArgumentParser(description="Semantic search across memories")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--limit", type=int, default=5, help="Max results")
    parser.add_argument("--threshold", type=float, default=0.5, help="Similarity threshold (0-1)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    results = search(args.query, args.limit, args.threshold)
    
    if args.json:
        output = []
        for source_type, source_id, content, similarity in results:
            output.append({
                "source_type": source_type,
                "source_id": source_id,
                "content": content,
                "similarity": round(similarity, 4)
            })
        print(json.dumps(output, indent=2))
    else:
        if not results:
            print("No matching memories found.")
            return
        
        print(f"Found {len(results)} relevant memories:\n")
        for i, (source_type, source_id, content, similarity) in enumerate(results, 1):
            print(f"─── Result {i} ({similarity:.1%} match) ───")
            print(f"Source: {source_type} / {source_id}")
            print(f"Content: {content[:500]}{'...' if len(content) > 500 else ''}")
            print()

if __name__ == "__main__":
    main()
