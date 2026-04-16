# Architecture: NOVA Semantic Memory Pipeline

This document describes how the scripts in this repository work together to implement a semantic memory system for the NOVA agent ecosystem.

## Overview

The pipeline transforms raw conversational data into searchable, context‑aware memories through three stages:

1. **Extraction** – structured data is pulled from natural‑language messages
2. **Embedding** – text is converted to vector embeddings and stored
3. **Recall** – relevant memories are retrieved based on semantic similarity

A fourth **maintenance** stage ensures memory quality over time.

## Data Flow

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Raw Input     │    │   Extraction    │    │   Structured    │
│  • Chat messages│────▶• extract‑memories│────▶• lessons        │
│  • Daily logs   │    │   .sh (Claude)  │    │• facts/entities │
│  • MEMORY.md    │    │                 │    │• opinions       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                          │
┌─────────────────┐    ┌─────────────────┐    ┌──────────▼──────────┐
│   Query/Message │    │   Recall        │    │   Embedding         │
│  • User query   │◀───│• semantic‑search│◀───│• embed‑memories.py  │
│  • New message  │    │• proactive‑recall│   │• embed‑memories‑cron│
└─────────────────┘    └─────────────────┘    └─────────────────────┘
         │                                                │
         │                                          ┌─────▼──────┐
         └──────────────────────────────────────────│  pgvector  │
                                                    │ embeddings │
                                                    └────────────┘
```

### Stage 1: Extraction (`extract-memories.sh`)

The pipeline begins when a natural‑language message arrives. `extract-memories.sh`:

- Calls the Claude API with a carefully crafted prompt
- Asks Claude to output JSON containing **entities**, **facts**, **opinions**, **preferences**, **vocabulary**, and **events**
- Each extracted item includes privacy metadata (`visibility`, `visibility_reason`) based on the sender’s default visibility and any privacy cues in the message
- The resulting JSON is intended to be stored in the appropriate tables of the `nova_memory` database (though the script itself only outputs JSON; actual storage is handled by a hook or calling process)

### Stage 2: Embedding (`embed-memories.py`, `embed-memories-cron.sh`)

Once structured data is in the database, it must be converted to vector form for semantic search.

`embed-memories.py`:

- Reads from multiple **sources**: daily logs (`*.md` files in `~/clawd/memory/`), the global `MEMORY.md`, and database tables (`lessons`, `events`, `sops`)
- Splits long texts into overlapping **chunks** (configurable `CHUNK_SIZE` and `CHUNK_OVERLAP`)
- Sends each chunk to OpenAI’s `text‑embedding‑3‑small` model to obtain a 1536‑dimensional vector
- Stores the vector together with the original text, source type, and source ID in the `memory_embeddings` table (PostgreSQL + pgvector)

`embed-memories-cron.sh` is a simple wrapper that runs `embed-memories.py` daily and logs the output.

### Stage 3: Recall (`semantic-search.py`, `proactive-recall.py`)

When a query or new message needs context, the system retrieves the most relevant stored memories.

**Semantic Search** (`semantic-search.py`):

- Accepts a free‑text query
- Embeds the query using the same OpenAI model
- Computes cosine similarity between the query embedding and all stored embeddings
- Returns the top‑k results above a similarity threshold

**Proactive Recall** (`proactive-recall.py`):

- Designed to be called from a **message pre‑processing hook** (e.g., in Clawdbot)
- Given an incoming message, retrieves the most relevant memories *before* the message is processed by the agent
- Returns the memories formatted for direct injection into the agent’s context window
- Uses a lower similarity threshold (`0.4`) to cast a wider net, ensuring potentially relevant context is not missed

### Stage 4: Maintenance (`decay-confidence.sh`, `recall-benchmark.py`)

Memory quality degrades over time if not actively maintained. These scripts keep the system accurate and reliable.

**Confidence Decay** (`decay-confidence.sh`):

- Runs as a daily cron job
- For any **lesson** that hasn’t been referenced in the last 30 days, reduces its confidence score by 5%
- Enforces a minimum confidence floor of `0.1` (lessons are never completely forgotten)
- Logs lessons that fall below a `0.3` confidence threshold for human review

**Recall Benchmark** (`recall-benchmark.py`):

- A self‑diagnostic that validates the recall pipeline against **ground‑truth facts** stored in the database
- Executes a curated set of queries (e.g., “What is I)ruid’s birthday?”) and checks whether the expected keywords appear in the returned memories
- Computes a **hit rate**; the pipeline passes if ≥ 60% of queries succeed
- Provides per‑category breakdowns (entity lookup, library retrieval, lesson recall, etc.)
- Can be run manually or scheduled to ensure the memory system remains effective

## Database Schema

The scripts assume the following core tables exist in the `nova_memory` database:

### `memory_embeddings`
```sql
CREATE TABLE memory_embeddings (
    id SERIAL PRIMARY KEY,
    source_type TEXT NOT NULL,      -- 'daily_log', 'memory_md', 'lesson', 'event', 'sop'
    source_id TEXT NOT NULL,        -- unique identifier for the source chunk
    content TEXT NOT NULL,          -- original text chunk
    embedding vector(1536),         -- pgvector column
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX ON memory_embeddings USING ivfflat (embedding vector_cosine_ops);
```

### `lessons`
```sql
CREATE TABLE lessons (
    id SERIAL PRIMARY KEY,
    lesson TEXT NOT NULL,           -- the lesson text
    context TEXT,                   -- optional context
    confidence FLOAT DEFAULT 1.0,   -- confidence score (0.1–1.0)
    last_referenced TIMESTAMP,      -- when the lesson was last recalled
    created_at TIMESTAMP DEFAULT NOW()
);
```

### `events`, `sops`, `entity_facts`, etc.

Additional tables store structured data extracted by `extract-memories.sh`. Refer to the NOVA memory schema documentation for full details.

## Configuration & Environment

All scripts rely on environment variables for API keys:

- `OPENAI_API_KEY` – used by `embed-memories.py`, `semantic-search.py`, `proactive-recall.py`
- `ANTHROPIC_API_KEY` – used by `extract-memories.sh` (can also be read from `~/.secrets/anthropic-api-key`)

Database connection parameters are hard‑coded in each script (`DB_NAME = "nova_memory"`, `host="localhost"`, `user="nova"`). Modify these constants if your setup differs.

## Integration with the NOVA Ecosystem

The scripts are designed to be used together with:

- **Clawdbot/OpenClaw** – hooks can call `extract-memories.sh` and `proactive-recall.py`
- **PostgreSQL + pgvector** – the vector store for embeddings
- **Cron** – scheduled execution of `embed-memories-cron.sh` and `decay-confidence.sh`
- **1Password** – API keys can be fetched via `op` (used in some scripts)

## Extending the Pipeline

To add a new source of memories:

1. Ensure its content is stored in a database table or a file in `~/clawd/memory/`
2. Add a new embedding function in `embed-memories.py` following the pattern of `embed_daily_logs()` or `embed_lessons()`
3. Update the `--source` argument handling to include your new source
4. (Optional) Add test queries for the new source in `recall-benchmark.py`

To adjust recall sensitivity:

- Modify `DEFAULT_THRESHOLD` in `proactive-recall.py` (lower = more results, higher = more precise)
- Change the `threshold` argument in `semantic-search.py`

## Troubleshooting

If recall performance drops:

1. Run `recall-benchmark.py --verbose` to see which queries are failing
2. Check that `embed-memories-cron.sh` is running daily (logs in `~/clawd/logs/embed-memories.log`)
3. Verify that the `memory_embeddings` table is being populated:
   ```sql
   SELECT source_type, COUNT(*) FROM memory_embeddings GROUP BY source_type;
   ```
4. Ensure the pgvector index is built (`ivfflat` for cosine similarity)

If extraction fails:

- Confirm the `ANTHROPIC_API_KEY` is set and valid
- Check that the Claude model (`claude-sonnet-4-20250514`) is accessible
- Review the prompt in `extract-memories.sh` for compatibility with your use case

---

*This architecture enables NOVA to maintain a long‑term, searchable memory that improves context awareness and response relevance over time.*