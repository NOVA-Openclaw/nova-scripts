#!/usr/bin/env python3
"""
Embed memory content using OpenAI and store in PostgreSQL pgvector.

Usage:
    python embed-memories.py                    # Embed all sources
    python embed-memories.py --source daily_log # Embed only daily logs
    python embed-memories.py --reindex          # Drop and recreate all embeddings
"""

import os
import sys
import json
import argparse
import hashlib
from pathlib import Path
from datetime import datetime
import psycopg2
from psycopg2.extras import execute_values
import openai

# Configuration
MEMORY_DIR = Path.home() / "clawd" / "memory"
MEMORY_MD = Path.home() / "clawd" / "MEMORY.md"
CHUNK_SIZE = 1000  # Characters per chunk (with overlap)
CHUNK_OVERLAP = 200
EMBEDDING_MODEL = "text-embedding-3-small"
DB_NAME = "nova_memory"

def get_openai_client():
    """Get OpenAI client with API key from environment or 1Password."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        # Try to get from skills config
        config_path = Path.home() / ".clawdbot" / "clawdbot.json"
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
                api_key = config.get("skills", {}).get("entries", {}).get("openai-image-gen", {}).get("apiKey")
    
    if not api_key:
        print("Error: No OpenAI API key found", file=sys.stderr)
        sys.exit(1)
    
    return openai.OpenAI(api_key=api_key)

def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap
    return chunks

def get_embedding(client, text):
    """Get embedding vector from OpenAI."""
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text
    )
    return response.data[0].embedding

def content_hash(text):
    """Hash content to detect changes."""
    return hashlib.md5(text.encode()).hexdigest()[:16]

def embed_daily_logs(conn, client, force=False):
    """Embed daily memory log files."""
    cur = conn.cursor()
    count = 0
    
    for log_file in sorted(MEMORY_DIR.glob("*.md")):
        source_id = log_file.name
        content = log_file.read_text()
        
        if not content.strip():
            continue
        
        # Check if already embedded (unless force)
        if not force:
            cur.execute(
                "SELECT id FROM memory_embeddings WHERE source_type = 'daily_log' AND source_id = %s",
                (source_id,)
            )
            if cur.fetchone():
                print(f"  Skipping {source_id} (already embedded)")
                continue
        
        # Chunk and embed
        chunks = chunk_text(content)
        for i, chunk in enumerate(chunks):
            chunk_id = f"{source_id}:chunk{i}"
            embedding = get_embedding(client, chunk)
            
            cur.execute("""
                INSERT INTO memory_embeddings (source_type, source_id, content, embedding)
                VALUES ('daily_log', %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (chunk_id, chunk, embedding))
            count += 1
        
        print(f"  Embedded {source_id} ({len(chunks)} chunks)")
    
    conn.commit()
    return count

def embed_memory_md(conn, client, force=False):
    """Embed MEMORY.md file."""
    cur = conn.cursor()
    
    if not MEMORY_MD.exists():
        return 0
    
    content = MEMORY_MD.read_text()
    source_id = "MEMORY.md"
    
    # Check if already embedded
    if not force:
        cur.execute(
            "SELECT id FROM memory_embeddings WHERE source_type = 'memory_md' AND source_id LIKE %s",
            (f"{source_id}%",)
        )
        if cur.fetchone():
            print(f"  Skipping {source_id} (already embedded)")
            return 0
    else:
        # Delete old embeddings for this file
        cur.execute("DELETE FROM memory_embeddings WHERE source_type = 'memory_md'")
    
    chunks = chunk_text(content)
    count = 0
    for i, chunk in enumerate(chunks):
        chunk_id = f"{source_id}:chunk{i}"
        embedding = get_embedding(client, chunk)
        
        cur.execute("""
            INSERT INTO memory_embeddings (source_type, source_id, content, embedding)
            VALUES ('memory_md', %s, %s, %s)
        """, (chunk_id, chunk, embedding))
        count += 1
    
    conn.commit()
    print(f"  Embedded {source_id} ({count} chunks)")
    return count

def embed_lessons(conn, client, force=False):
    """Embed lessons from database."""
    cur = conn.cursor()
    
    cur.execute("SELECT id, lesson, context FROM lessons")
    lessons = cur.fetchall()
    
    count = 0
    for lesson_id, lesson, context in lessons:
        source_id = f"lesson:{lesson_id}"
        
        if not force:
            cur.execute(
                "SELECT id FROM memory_embeddings WHERE source_type = 'lesson' AND source_id = %s",
                (source_id,)
            )
            if cur.fetchone():
                continue
        
        content = f"Lesson: {lesson}"
        if context:
            content += f"\nContext: {context}"
        
        embedding = get_embedding(client, content)
        
        cur.execute("""
            INSERT INTO memory_embeddings (source_type, source_id, content, embedding)
            VALUES ('lesson', %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (source_id, content, embedding))
        count += 1
    
    conn.commit()
    if count:
        print(f"  Embedded {count} lessons")
    return count

def embed_events(conn, client, force=False):
    """Embed events from database."""
    cur = conn.cursor()
    
    cur.execute("SELECT id, title, description, event_date FROM events ORDER BY event_date DESC LIMIT 100")
    events = cur.fetchall()
    
    count = 0
    for event_id, title, description, event_date in events:
        source_id = f"event:{event_id}"
        
        if not force:
            cur.execute(
                "SELECT id FROM memory_embeddings WHERE source_type = 'event' AND source_id = %s",
                (source_id,)
            )
            if cur.fetchone():
                continue
        
        content = f"Event ({event_date}): {title}"
        if description:
            content += f"\n{description}"
        
        embedding = get_embedding(client, content)
        
        cur.execute("""
            INSERT INTO memory_embeddings (source_type, source_id, content, embedding)
            VALUES ('event', %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (source_id, content, embedding))
        count += 1
    
    conn.commit()
    if count:
        print(f"  Embedded {count} events")
    return count

def embed_sops(conn, client, force=False):
    """Embed SOPs (Standard Operating Procedures) from database."""
    cur = conn.cursor()
    
    cur.execute("SELECT id, name, description, steps FROM sops")
    sops = cur.fetchall()
    
    count = 0
    for sop_id, name, description, steps in sops:
        source_id = f"sop:{sop_id}"
        
        if not force:
            cur.execute(
                "SELECT id FROM memory_embeddings WHERE source_type = 'sop' AND source_id = %s",
                (source_id,)
            )
            if cur.fetchone():
                continue
        else:
            # Delete old embedding for this SOP
            cur.execute("DELETE FROM memory_embeddings WHERE source_type = 'sop' AND source_id = %s", (source_id,))
        
        # Build content: name, description, and steps
        content = f"SOP: {name}\n"
        if description:
            content += f"Description: {description}\n"
        
        # Parse steps (can be array of strings or array of objects)
        if steps:
            content += "Steps:\n"
            if isinstance(steps, str):
                steps = json.loads(steps)
            for i, step in enumerate(steps, 1):
                if isinstance(step, str):
                    content += f"  {i}. {step}\n"
                elif isinstance(step, dict):
                    action = step.get('action', step.get('step', ''))
                    content += f"  {i}. {action}\n"
                    if 'command' in step:
                        content += f"     Command: {step['command']}\n"
                    if 'sql' in step:
                        content += f"     SQL: {step['sql']}\n"
        
        embedding = get_embedding(client, content)
        
        cur.execute("""
            INSERT INTO memory_embeddings (source_type, source_id, content, embedding)
            VALUES ('sop', %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (source_id, content, embedding))
        count += 1
        print(f"  Embedded SOP: {name}")
    
    conn.commit()
    if count:
        print(f"  Embedded {count} SOPs total")
    return count

def main():
    parser = argparse.ArgumentParser(description="Embed memories for semantic search")
    parser.add_argument("--source", choices=["daily_log", "memory_md", "lesson", "event", "sop", "all"], 
                        default="all", help="Which source to embed")
    parser.add_argument("--reindex", action="store_true", help="Force re-embed everything")
    args = parser.parse_args()
    
    print("Connecting to database...")
    conn = psycopg2.connect(dbname=DB_NAME, host="localhost", user="nova")
    
    print("Initializing OpenAI client...")
    client = get_openai_client()
    
    total = 0
    
    if args.source in ["daily_log", "all"]:
        print("\nEmbedding daily logs...")
        total += embed_daily_logs(conn, client, args.reindex)
    
    if args.source in ["memory_md", "all"]:
        print("\nEmbedding MEMORY.md...")
        total += embed_memory_md(conn, client, args.reindex)
    
    if args.source in ["lesson", "all"]:
        print("\nEmbedding lessons...")
        total += embed_lessons(conn, client, args.reindex)
    
    if args.source in ["event", "all"]:
        print("\nEmbedding events...")
        total += embed_events(conn, client, args.reindex)
    
    if args.source in ["sop", "all"]:
        print("\nEmbedding SOPs...")
        total += embed_sops(conn, client, args.reindex)
    
    print(f"\nDone! Embedded {total} chunks total.")
    
    # Show stats
    cur = conn.cursor()
    cur.execute("SELECT source_type, COUNT(*) FROM memory_embeddings GROUP BY source_type")
    print("\nEmbedding stats:")
    for source_type, count in cur.fetchall():
        print(f"  {source_type}: {count}")
    
    conn.close()

if __name__ == "__main__":
    main()
