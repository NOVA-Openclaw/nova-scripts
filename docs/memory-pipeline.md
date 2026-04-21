# Memory Pipeline Documentation

This document describes the memory extraction, embedding, recall, and maintenance scripts.

## Overview

The memory pipeline transforms unstructured chat messages and logs into searchable vector embeddings, enabling semantic recall and proactive context injection.

## Scripts

| Script | Purpose | Input | Output | Dependencies |
|--------|---------|-------|--------|--------------|
| `extract-memories.sh` | Extract structured memories from a message | Raw text (stdin or arg) | JSON (entities, facts, opinions, etc.) | `jq`, `curl`, `psql`, Anthropic API key |
| `embed-memories.py` | Embed memory sources into pgvector | Daily logs, MEMORY.md, lessons, events, SOPs | `memory_embeddings` table entries | `openai`, `psycopg2`, PostgreSQL with pgvector |
| `embed-memories-cron.sh` | Cron wrapper for embedding pipeline | (none) | Log file (`~/clawd/logs/embed-memories.log`) | Python virtual environment with dependencies |
| `decay-confidence.sh` | Decay confidence scores of old lessons | (none) | Updates `lessons.confidence` in DB | `psql` |
| `proactive-recall.py` | Retrieve relevant memories for a query | Query string | JSON or formatted text | `openai`, `psycopg2` |
| `recall-benchmark.py` | Evaluate recall accuracy | (none) | Pass/fail summary with per‑query results | `openai`, `psycopg2`, `proactive-recall.py` |
| `semantic-search.py` | Command‑line semantic search | Query string | List of matching memories (JSON or plain) | `openai`, `psycopg2` |

## Usage Examples

### 1. Extract Memories

```bash
# Via stdin
echo "I love pizza, feel free to share that" | ./extract-memories.sh

# As argument
./extract-memories.sh "Just between us, I'm thinking of quitting"

# With sender context
SENDER_NAME="Alice" SENDER_ID="+1234567890" IS_GROUP=false \
  ./extract-memories.sh "My birthday is May 27."
```

**Environment variables:**
- `ANTHROPIC_API_KEY` – required (can be in `~/.secrets/anthropic-api-key`)
- `SENDER_NAME`, `SENDER_ID`, `IS_GROUP` – optional, used for attribution and privacy detection

**Output example:**
```json
{
  "entities": [
    {
      "name": "Alice",
      "type": "person",
      "source_person": "Alice",
      "visibility": "private",
      "visibility_reason": "Just between us"
    }
  ],
  "facts": [
    {
      "subject": "Alice",
      "predicate": "birthday",
      "value": "May 27",
      "source_person": "Alice",
      "confidence": 0.9,
      "visibility": "private",
      "visibility_reason": "Just between us"
    }
  ]
}
```

### 2. Embed Memories

```bash
# Embed all sources
python embed-memories.py

# Embed only daily logs
python embed-memories.py --source daily_log

# Force re‑embedding of everything
python embed-memories.py --reindex
```

**Environment variables:**
- `OPENAI_API_KEY` – required (or stored in `~/.clawdbot/clawdbot.json` under `skills.entries.openai-image-gen.apiKey`)

**Database connection:** assumes local PostgreSQL database `nova_memory` with user `nova` (no password). Modify the `psycopg2.connect()` call in the script if your setup differs.

### 3. Proactive Recall

```bash
# Get JSON results
python proactive-recall.py "What is I)ruid's real name?"

# Get formatted context for injection
python proactive-recall.py "What is I)ruid's real name?" --inject
```

**Environment variables:** `OPENAI_API_KEY` as above.

**Output (JSON):**
```json
{
  "query": "What is I)ruid's real name?",
  "memories": [
    {
      "source": "daily_log/2026-04-20.md:chunk2",
      "content": "I)ruid's real name is Dustin Trammell...",
      "similarity": 0.872
    }
  ],
  "count": 1
}
```

### 4. Semantic Search

```bash
python semantic-search.py "what did we discuss about the app?"
python semantic-search.py "I)ruid's health" --limit 10 --threshold 0.4
python semantic-search.py "bitcoin" --json
```

### 5. Run Recall Benchmark

```bash
python recall-benchmark.py --verbose
python recall-benchmark.py --json
```

Exits with code 0 if hit rate ≥ 60%, otherwise 1.

### 6. Schedule Cron Jobs

Example crontab entries:

```cron
# Daily embedding at 2 AM
0 2 * * * /home/nova/clawd/scripts/embed-memories-cron.sh

# Nightly confidence decay at 4 AM
0 4 * * * /home/nova/clawd/scripts/decay-confidence.sh
```

Adjust paths to match your installation.

## Database Schema Notes

### memory_embeddings

```sql
CREATE TABLE memory_embeddings (
    id SERIAL PRIMARY KEY,
    source_type TEXT NOT NULL,      -- 'daily_log', 'memory_md', 'lesson', 'event', 'sop'
    source_id TEXT NOT NULL,        -- file name or identifier
    content TEXT NOT NULL,          -- text chunk
    embedding vector(1536),         -- OpenAI text-embedding-3-small dimension (requires pgvector)
    created_at TIMESTAMP DEFAULT NOW()
);
```

Create the pgvector extension if not present:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### lessons

```sql
CREATE TABLE lessons (
    id SERIAL PRIMARY KEY,
    lesson TEXT NOT NULL,           -- the lesson learned
    context TEXT,                   -- when/where it was learned
    confidence FLOAT DEFAULT 1.0,   -- decayed by decay-confidence.sh
    last_referenced TIMESTAMP,      -- updated when lesson is recalled
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Other tables

The scripts also read from `events` and `sops` tables; their exact schema can be inferred from the embedding code (see `embed-memories.py`).

## Troubleshooting

### `extract-memories.sh` fails with "exit 1"

- Check that `ANTHROPIC_API_KEY` is set or exists in `~/.secrets/anthropic-api-key`.
- Ensure `jq` and `curl` are installed.

### Embedding script cannot connect to database

- Verify PostgreSQL is running and accessible.
- Check that the `nova_memory` database exists and the `nova` user can connect without password (or modify the script to use a password/connection string).

### No results from semantic search

- Confirm that `memory_embeddings` table has data (run `SELECT COUNT(*) FROM memory_embeddings;`).
- Lower the similarity threshold (default 0.5) with `--threshold 0.3`.

### Recall benchmark fails most queries

- The benchmark expects specific facts (e.g., "I)ruid's real name") to be present in embedded memories. If those facts aren't in your database, the benchmark will fail. Consider adapting the query list in `recall-benchmark.py` to match your own knowledge base.

## Unclear Parts / TODO

- **`extract-memories.sh` database lookup**: The script queries `entity_facts` to determine a user's default visibility. The exact schema of `entity_facts` is not documented here; it may be part of a larger entity‑resolution system.
- **Lesson confidence decay**: The `decay-confidence.sh` script assumes a `lessons` table with `confidence` and `last_referenced` columns. How `last_referenced` is updated is not shown in this repository.
- **Memory source directories**: The scripts assume daily logs are in `~/clawd/memory/*.md` and `MEMORY.md` is in `~/clawd/`. These paths are hardcoded and may need adjustment for your environment.

## Related Files

- `ARCHITECTURE.md` – high‑level pipeline diagram and integration notes.
- `docs/` – other documentation files.

---

*Made with 💜 by NOVA*