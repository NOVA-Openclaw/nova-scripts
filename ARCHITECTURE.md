# Architecture Overview

This document describes how the different scripts and subprojects in `nova-scripts` interconnect.

## Memory / Embeddings Pipeline

The memory pipeline is a multi‑stage system that extracts structured knowledge from chat messages, embeds it for semantic search, and enables proactive recall.

### Flow

```
┌─────────────────────┐
│   Incoming Chat     │
│      Message        │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  extract-memories.sh│
│  (Anthropic API)    │
│  → JSON entities,   │
│    facts, opinions, │
│    preferences,     │
│    vocabulary       │
└──────────┬──────────┘
           │
           │ (manual insertion into database)
           ▼
┌─────────────────────┐
│   Daily logs,       │
│   MEMORY.md,        │
│   lessons, events,  │
│   SOPs              │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  embed-memories.py  │
│  (OpenAI embeddings)│
│  → memory_embeddings│
│    table (pgvector) │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   Semantic Search   │
│  (proactive-recall, │
│   semantic-search)  │
│  → similarity match │
└─────────────────────┘
```

### Components

1. **Extraction** (`extract-memories.sh`)
   - Input: raw chat message (stdin or argument)
   - Uses Anthropic Claude to parse the message and output structured JSON.
   - Categories: entities, facts, opinions, preferences, vocabulary, events.
   - Privacy detection: respects default visibility and overrides based on phrases.

2. **Embedding** (`embed-memories.py`)
   - Reads multiple memory sources:
     - Daily log files (`~/clawd/memory/*.md`)
     - Central `MEMORY.md`
     - Database tables: `lessons`, `events`, `sops`
   - Splits text into overlapping chunks (1000 chars, 200 overlap).
   - Calls OpenAI `text-embedding-3-small` to get vector embeddings.
   - Stores `(source_type, source_id, content, embedding)` in `memory_embeddings` table.
   - Supports `--source` to embed only specific sources, and `--reindex` to force re‑embedding.

3. **Cron Jobs**
   - `embed-memories-cron.sh`: daily embedding of all sources (logs to `~/clawd/logs/embed-memories.log`).
   - `decay-confidence.sh`: nightly decay of `lessons.confidence` for lessons not referenced in 30+ days (multiplies by 0.95, floor 0.1).

4. **Recall & Search**
   - `proactive-recall.py`: intended as a Clawdbot hook; given a message, returns top‑k relevant memories (JSON or formatted for context injection).
   - `semantic-search.py`: command‑line semantic search with similarity threshold.

5. **Benchmarking**
   - `recall-benchmark.py`: runs a suite of predefined queries against the recall system and evaluates hit rate (≥60% passes). Used for self‑diagnostic.

### Database Schema (Partial)

The pipeline assumes the following PostgreSQL tables (exact schema may evolve):

```sql
-- memory_embeddings (pgvector extension required)
CREATE TABLE memory_embeddings (
    id SERIAL PRIMARY KEY,
    source_type TEXT NOT NULL,  -- 'daily_log', 'memory_md', 'lesson', 'event', 'sop'
    source_id TEXT NOT NULL,    -- e.g., '2026-04-21.md', 'MEMORY.md:chunk0'
    content TEXT NOT NULL,
    embedding vector(1536),     -- OpenAI text-embedding-3-small dimension
    created_at TIMESTAMP DEFAULT NOW()
);

-- lessons (confidence decay target)
CREATE TABLE lessons (
    id SERIAL PRIMARY KEY,
    lesson TEXT NOT NULL,
    context TEXT,
    confidence FLOAT DEFAULT 1.0,
    last_referenced TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- events, sops, etc. (referenced by embed-memories.py)
```

### Environment Variables

- `OPENAI_API_KEY` – for embedding and recall scripts.
- `ANTHROPIC_API_KEY` – for extraction script.
- Database connection: most scripts assume a local PostgreSQL instance with database `nova_memory` and user `nova` (no password). Override via `psql` environment variables (`PGHOST`, `PGUSER`, etc.) or modify scripts.

## Git Security Hooks

A lightweight pre‑commit hook that prevents accidental commits of secrets.

### How It Works

1. `install-hooks.sh` copies `pre-commit-template` to `.git/hooks/pre-commit` and makes it executable.
2. The hook scans all staged files for:
   - Secret patterns (API keys, passwords, private keys)
   - Forbidden file names (`.env`, `*.pem`, `credentials.json`, etc.)
3. If any matches are found, the commit is blocked with a clear error message.

### Patterns Detected

- Anthropic API keys (`sk-ant-api…`)
- OpenAI API keys (`sk-…`)
- AWS access/secret keys
- Private key headers (`-----BEGIN … PRIVATE KEY-----`)
- GitHub tokens (`ghp_`, `gho_`, etc.)
- Generic `secret: "…"`, `password: "…"`, `api_key: "…"` patterns.

### Integration

The hook is repository‑specific; run `install-hooks.sh` for each repo you want to protect. It also adds common secret‑file patterns to the repo's `.gitignore`.

## Agent Chat Channel

A Clawdbot plugin that enables real‑time messaging between agents via PostgreSQL `LISTEN/NOTIFY`.

### Architecture

```
┌─────────────┐  INSERT  ┌──────────────┐  NOTIFY  ┌─────────────────┐
│   Sender    │ ────────▶│ agent_chat   │ ────────▶│  Clawdbot       │
│ (SQL, app)  │          │   table      │          │  Plugin         │
└─────────────┘          └──────────────┘          └────────┬────────┘
                                                            │ LISTEN
                                                            ▼
                                                    ┌──────────────┐
                                                    │   Agent      │
                                                    │  (Newhart)   │
                                                    └──────────────┘
```

1. **Database tables**: `agent_chat` (messages with `mentions` array), `agent_chat_processed` (deduplication).
2. **Trigger**: `notify_agent_chat()` fires `pg_notify('agent_chat', …)` on each INSERT.
3. **Plugin**: Listens on the `agent_chat` channel, polls for unprocessed messages where the agent is mentioned, routes them to the agent session, and marks them processed.
4. **Replies**: Agent replies are inserted back into `agent_chat` with `reply_to` linking to the original message.

### Integration Points

- Works with any PostgreSQL‑backed agent system.
- Mentions‑based routing allows multiple agents to share the same table.
- Can be extended with custom triggers or external applications.

## Dependencies & Cross‑Script Relationships

- **Python scripts** (`embed-memories.py`, `proactive-recall.py`, `semantic-search.py`, `recall-benchmark.py`) share `openai` and `psycopg2` dependencies.
- **Shell scripts** (`extract-memories.sh`, `decay-confidence.sh`, `embed-memories-cron.sh`) rely on `jq`, `curl`, `psql`.
- **Git hooks** are standalone but use `grep` and `git` commands.
- **Agent Chat Channel** is a Node.js Clawdbot plugin with its own `package.json`.

## Future Evolution

- The memory pipeline could be unified into a single service with a REST API.
- Embedding scripts could support additional vector databases (e.g., Qdrant, Pinecone).
- Git hooks could be extended with custom pattern files per repository.
- Agent Chat Channel could add support for WebSocket broadcasts or external messaging platforms.

---

*Made with 💜 by NOVA*