# nova-scripts Architecture

> *Memory flows through stone channels,*
> *Voices carried on database waves,*
> *Knowledge held in vector space.*

This document describes how the components in this repository relate to each other and their role in the broader NOVA agent ecosystem.

---

## System Overview

This repository contains three distinct subsystems that support the NOVA agent ecosystem:

1. **Memory Pipeline** — Persistent semantic memory for agents
2. **Agent Chat Channel** — Inter-agent messaging via PostgreSQL
3. **Git Security** — Pre-commit secret scanning

```
┌─────────────────────────────────────────────────────────────┐
│                    NOVA Agent Ecosystem                      │
│                                                             │
│  ┌────────────┐    ┌──────────────┐    ┌────────────────┐  │
│  │  Memory     │    │  Agent Chat  │    │  Git Security  │  │
│  │  Pipeline   │    │  Channel     │    │  Hooks         │  │
│  └─────┬───────┘    └──────┬───────┘    └───────┬────────┘  │
│        │                   │                    │           │
│        ▼                   ▼                    ▼           │
│  ┌────────────────────────────────────────────────────┐    │
│  │              PostgreSQL (nova_memory)              │    │
│  │  memory_embeddings  │  lessons  │  events  │       │    │
│  │  agent_chat         │  sops     │           │       │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  OpenAI (text-embedding-3-small)   ◄── Embedding API        │
│  Anthropic (Claude)                ◄── Extraction API       │
└─────────────────────────────────────────────────────────────┘
```

---

## Memory Pipeline

The memory pipeline is the core of NOVA's persistent, semantically-searchable memory. It transforms raw chat messages into vector embeddings that can be retrieved at runtime for context injection.

### Data Flow

```
Chat Message
    │
    ▼
extract-memories.sh ────────────► Database tables
(Anthropic Claude API)              (entities, facts,
    │                                lessons, events,
    ▼                                preferences, etc.)
embed-memories.py ──────────────► memory_embeddings table
(OpenAI embeddings API,             (pgvector column)
 pgvector, PostgreSQL)
    │
    ▼
proactive-recall.py ◄────── New message triggers recall
(Pre-message context injection)    │
    │                               │
    ▼                               ▼
Agent session gets           semantic-search.py
relevant memory context      (Ad-hoc CLI queries)
    │
    ▼
recall-benchmark.py ─── Validates pipeline accuracy
(Self-diagnostic)               against known ground truth
    │
    ▼
decay-confidence.sh ─── Gradually reduces confidence
(Cron, daily)               of stale/unreferenced lessons
```

### Stage 1: Extraction

**Script:** `scripts/extract-memories.sh`

Incoming chat messages (from any channel — Signal, WhatsApp, Discord, etc.) are processed through the `extract-memories.sh` script. It calls the Anthropic Claude API with a structured prompt that:

- Parses the message for entities, facts, opinions, preferences, vocabulary, and events
- Applies privacy detection (respecting per-user default visibility settings and override cues)
- Returns structured JSON stored in the database

### Stage 2: Embedding

**Scripts:** `scripts/embed-memories.py`, `scripts/embed-memories-cron.sh`

The embedding script reads from five source types:

| Source | Database Table / File | Description |
|---|---|---|
| `daily_log` | `~/clawd/memory/*.md` | Daily markdown logs |
| `memory_md` | `~/clawd/MEMORY.md` | Main memory file |
| `lesson` | `lessons` table | Learned lessons from corrections |
| `event` | `events` table | Calendar events |
| `sop` | `sops` table | Standard Operating Procedures |

Each source is chunked (1000 chars per chunk with 200 char overlap), embedded via OpenAI's `text-embedding-3-small` model, and stored in the `memory_embeddings` table with a `pgvector` vector column.

The cron wrapper (`embed-memories-cron.sh`) runs this daily to keep embeddings current.

### Stage 3: Recall

**Scripts:** `scripts/proactive-recall.py`, `scripts/semantic-search.py`

**Proactive Recall:** Before processing a user message, `proactive-recall.py` embeds the message query and performs a nearest-neighbor search against the `memory_embeddings` table. The top results are injected into the agent's context as "relevant memories."

**Semantic Search:** `semantic-search.py` is the ad-hoc CLI version — useful for manual queries and debugging.

Both use cosine distance (`<=>` operator in pgvector) for similarity ranking.

### Stage 4: Maintenance

**Scripts:** `scripts/recall-benchmark.py`, `scripts/decay-confidence.sh`

**Benchmarking:** `recall-benchmark.py` runs a set of known queries against `proactive-recall.py` and checks if expected keywords appear in the results. It tests:

- Entity lookups (direct fact retrieval)
- Library knowledge queries
- Lesson recall (from past corrections)
- Event date queries
- Cross-reference queries (architecture knowledge)
- Noise handling (irrelevant queries should return empty results)

The pipeline passes if hit rate ≥ 60%.

**Confidence Decay:** `decay-confidence.sh` runs daily via cron. It reduces confidence scores for lessons that haven't been referenced in 30+ days (multiply by 0.95, floor at 0.1). Lessons below 0.3 confidence are logged as candidates for review.

---

## Agent Chat Channel

The `agent-chat-channel/` directory contains a PostgreSQL-based messaging channel plugin for OpenClaw.

### Role in the Ecosystem

In the NOVA agent ecosystem, agents need to communicate with each other. The agent-chat-channel plugin provides this capability by treating the `agent_chat` database table as a message bus:

```
Agent A (e.g., scout)
    │
    │  INSERT INTO agent_chat (sender='scout', message='...', mentions=ARRAY['coder'])
    ▼
agent_chat table ──► PostgreSQL NOTIFY
    │
    ▼
gateway.agentChatPlugin ──► LISTEN agent_chat
    │
    ├──► Routes to Agent B's session (e.g., coder)
    │      runtime.handleInbound({...})
    │
    └──► Marks message as processed in agent_chat_processed
```

### Key Design Decisions

- **Database as message bus:** No separate message broker needed. PostgreSQL's LISTEN/NOTIFY provides real-time delivery.
- **Mention-based routing:** Agents only receive messages that mention them by name. This prevents message storms.
- **Deduplication at the DB level:** The `agent_chat_processed` table with a composite primary key `(chat_id, agent)` ensures each message is processed exactly once per agent.
- **1Password integration:** Database credentials can be stored in 1Password and resolved at runtime.

### Database Tables

| Table | Purpose |
|---|---|
| `agent_chat` | Message store (channel, sender, message, mentions, reply chain) |
| `agent_chat_processed` | Deduplication tracker |

### Plugin Architecture

The plugin follows OpenClaw's channel plugin architecture:

| Component | Purpose |
|---|---|
| `config.resolveAccount` | Resolves account configuration (single or multi-account) |
| `gateway.startAccount` | Core listening loop (LISTEN, fetch unprocessed, route to sessions) |
| `outbound.sendText` | Sends agent replies back to the `agent_chat` table |
| `status` | Health and runtime status reporting |

---

## Git Security

The `scripts/git-security/` directory provides pre-commit hooks that scan staged files for secrets before they reach the repository.

### Purpose

In an AI agent ecosystem where code is written autonomously (or semi-autonomously), the risk of accidentally committing API keys or credentials is higher than in human-only development. These hooks provide an automated safety net.

### How It Works

```
Developer stages files
    │
    ▼
git commit triggers pre-commit hook
    │
    ▼
Scans staged files for patterns:
  - API keys (OpenAI, Anthropic, AWS, GitHub)
  - Private keys (RSA, Ed25519, PEM)
  - Secrets and passwords in config-like patterns
  - Forbidden files (.env, credentials.json, id_*)
    │
    ├── No problems found ──► Commit proceeds
    │
    └── Secrets detected ──► Commit blocked
                              (can bypass with --no-verify)
```

### Installer

`install-hooks.sh` automates installation:
1. Copies `pre-commit-template` to the target repo's `.git/hooks/pre-commit`
2. Makes it executable
3. Updates `.gitignore` with common secret patterns

---

## Dependencies Summary

| Component | Dependencies |
|---|---|
| Memory Pipeline | PostgreSQL (pgvector), OpenAI API, Anthropic API, Python 3 (psycopg2, openai), bash (jq, curl, psql) |
| Agent Chat Plugin | Node.js, PostgreSQL (`pg` npm package) |
| Git Security | bash, grep |
| GDrive Sync | gogcli, jq |

---

## Related Repositories

- [OpenClaw](https://github.com/nova-ai/openclaw) — The gateway platform these scripts run on
- [nova-memory](https://github.com/nova-ai/nova-memory) — Database schemas and migrations
- [nova-cognition](https://github.com/nova-ai/nova-cognition) — Agent cognition and routing

---

*Architecture reviewed 2026-05-06*
