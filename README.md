# nova-scripts ✨

Utility scripts and tools by **NOVA** — an AI assistant ecosystem running on [OpenClaw](https://github.com/nova-ai/openclaw).

This repository contains the operational scripts that power NOVA's memory pipeline, inter-agent communication, Google Drive sync, and pre-commit security hooks. These are small utilities written to solve everyday problems — open source in case they're useful to others.

---

## Table of Contents

- [Memory Pipeline](#memory-pipeline)
  - [extract-memories.sh](#extract-memoriessh)
  - [embed-memories.py](#embed-memoriespy)
  - [embed-memories-cron.sh](#embed-memories-cronsh)
  - [proactive-recall.py](#proactive-recallpy)
  - [semantic-search.py](#semantic-searchpy)
  - [recall-benchmark.py](#recall-benchmarkpy)
  - [decay-confidence.sh](#decay-confidencesh)
- [Utilities](#utilities)
  - [gdrive-sync.sh](#gdrive-syncsh)
  - [agent-install.sh](#agent-installsh)
- [Security](#security)
  - [git-security (install-hooks.sh + pre-commit-template)](#git-security)
- [Plugin](#plugin)
  - [agent-chat-channel](#agent-chat-channel)
- [Architecture](#architecture)
- [License](#license)

---

## Memory Pipeline

The memory pipeline is the core of NOVA's persistent memory system. Data flows through four stages:

1. **Extract** → Parse chat messages and extract structured memory (facts, entities, lessons)
2. **Embed** → Convert extracted content into vector embeddings using OpenAI + pgvector
3. **Recall** → On new messages, retrieve semantically relevant memories for context injection
4. **Maintain** → Decay stale memories and benchmark retrieval accuracy

### extract-memories.sh

Extracts structured memory data (entities, facts, opinions, preferences, vocabulary, events) from chat messages using the Anthropic Claude API. Designed to be called from a message processing hook.

```bash
# Pipe a message directly
echo "I love working on the Nova project" | ./scripts/extract-memories.sh

# Or pass as argument
./scripts/extract-memories.sh "My birthday is May 27th, 1978"

# Environment variables for sender attribution
SENDER_NAME="I)ruid" SENDER_ID="+15551234567" ./scripts/extract-memories.sh "Just between us, I'm thinking of quitting"
```

**Requirements:** Anthropic API key (`ANTHROPIC_API_KEY`), `jq`, `curl`, `psql` (for privacy preference lookup)

**Output:** JSON with extracted entities, facts, opinions, preferences, vocabulary, and events.

**Privacy-aware:** Respects per-user default visibility settings (public/private) stored in the database. Detects override cues like "feel free to share" or "don't tell anyone."

### embed-memories.py

Takes memory content from various sources (daily logs, MEMORY.md, database lessons, events, SOPs) and creates vector embeddings using OpenAI's `text-embedding-3-small` model. Stores embeddings in PostgreSQL using the `pgvector` extension.

```bash
# Embed all sources
python3 ./scripts/embed-memories.py

# Embed only daily logs
python3 ./scripts/embed-memories.py --source daily_log

# Drop and recreate all embeddings
python3 ./scripts/embed-memories.py --reindex
```

**Requirements:** OpenAI API key (`OPENAI_API_KEY`), PostgreSQL (`nova_memory` database), `pgvector` extension

**Sources:**
- `daily_log` — Markdown files from `~/clawd/memory/`
- `memory_md` — `MEMORY.md` file
- `lesson` — Database `lessons` table
- `event` — Database `events` table
- `sop` — Database `sops` table (Standard Operating Procedures)

**Chunking:** Splits text into overlapping chunks (1000 chars with 200 char overlap) for granular retrieval.

### embed-memories-cron.sh

Cron wrapper script that runs `embed-memories.py` daily. Sources a Python virtual environment and logs output to `~/clawd/logs/embed-memories.log`.

```bash
# Run manually
./scripts/embed-memories-cron.sh

# Typical crontab entry (runs daily at 3 AM)
0 3 * * * /home/nova/clawd/scripts/embed-memories-cron.sh
```

**Requirements:** Python virtual environment at `~/clawd/scripts/tts-venv/`

### proactive-recall.py

Pre-message semantic recall system. Given a user's message, retrieves the most semantically relevant memories from the embedding store. Designed for context injection — it can produce formatted output ready to insert into an LLM prompt.

```bash
# Standalone search
python3 ./scripts/proactive-recall.py "What projects does NOVA include?"

# Formatted for prompt injection
python3 ./scripts/proactive-recall.py "Tell me about the Silmarillion" --inject

# Custom limit and threshold
python3 ./scripts/proactive-recall.py "How does the recall system work?" --limit 5
```

**Requirements:** OpenAI API key, PostgreSQL (`nova_memory` database with `memory_embeddings` table), `pgvector`

**Output:** JSON with ranked results including source, content excerpt, and similarity score. Use `--inject` for a preformatted markdown block.

### semantic-search.py

CLI tool for ad-hoc semantic search across the embedded memory store. Provides flexible querying with configurable similarity threshold and result limits.

```bash
# Basic search
python3 ./scripts/semantic-search.py "what did we discuss about the app?"

# More results with lower threshold
python3 ./scripts/semantic-search.py "I)ruid's health" --limit 10 --threshold 0.3

# JSON output for programmatic use
python3 ./scripts/semantic-search.py "architecture" --json
```

**Requirements:** OpenAI API key, PostgreSQL, `pgvector`

### recall-benchmark.py

Self-diagnostic benchmarking tool that tests the semantic recall pipeline (`proactive-recall.py`) against known ground-truth facts. Measures retrieval accuracy across multiple query patterns including entity lookups, library retrieval, lesson recall, event queries, cross-references, and noise handling.

```bash
# Run with verbose output
python3 ./scripts/recall-benchmark.py --verbose

# JSON output for analysis
python3 ./scripts/recall-benchmark.py --json
```

**Pass/fail:** Exit code 0 if hit rate ≥ 60%, exit code 1 otherwise. Reports per-category breakdown.

**Test categories:**
- `entity_lookup` — Direct fact retrieval (names, birthdays, relationships)
- `library` — Library/knowbase retrieval (books, subjects)
- `lesson` — Lesson recall from past corrections
- `event` — Event date retrieval
- `cross_reference` — Architecture and ecosystem knowledge
- `noise` — Handles irrelevant queries without false positives

### decay-confidence.sh

Cron-compatible script that gradually decays confidence scores for lessons not referenced recently. Prevents stale or outdated information from persisting indefinitely.

```bash
# Run manually
./scripts/decay-confidence.sh

# Typical crontab entry (runs daily at 4 AM)
0 4 * * * /home/nova/clawd/scripts/decay-confidence.sh
```

**Behavior:**
- Lessons not referenced in 30+ days: confidence multiplied by 0.95
- Minimum confidence floor: 0.1 (never fully forgets)
- Logs lessons that drop below 0.3 confidence for review

**Requirements:** PostgreSQL access to `nova_memory` database

---

## Utilities

### gdrive-sync.sh

Simple Google Drive folder sync using [gogcli](https://gogcli.sh). Supports pull, push, and status operations for a single Google Drive folder.

```bash
# Set required config (or edit script defaults)
export GDRIVE_FOLDER_ID="your-folder-id"
export LOCAL_DIR="$HOME/my-sync-folder"
export GOG_ACCOUNT="you@gmail.com"  # optional

# Download from GDrive to local
./scripts/gdrive-sync.sh pull

# Upload from local to GDrive
./scripts/gdrive-sync.sh push

# Show files in both locations
./scripts/gdrive-sync.sh status
```

**Requirements:**
- [gogcli](https://gogcli.sh) (`brew install steipete/tap/gogcli`)
- `jq` for JSON parsing
- Authenticated gog account (`gog auth add you@gmail.com`)

**Configuration:** Set via environment variables (`GDRIVE_FOLDER_ID`, `LOCAL_DIR`, `GOG_ACCOUNT`) or edit the defaults at the top of the script.

### agent-install.sh

Stub installer for NOVA-INSTALL.sh compatibility. This repository has no installation requirements.

```bash
./agent-install.sh
# Output: No installation steps for nova-scripts
```

---

## Security

### git-security

Pre-commit hooks for scanning staged files for potential secrets before they reach the repository. Prevents accidental commits of API keys, credentials, and private keys.

**Contents:**
- `install-hooks.sh` — Installer script that copies the hook template to any git repository
- `pre-commit-template` — The actual pre-commit hook template

```bash
# Install hooks in a repository
./scripts/git-security/install-hooks.sh /path/to/your/repo
```

**What it detects (via the pre-commit template):**

| Pattern | Example |
|---|---|
| Anthropic API keys | `sk-ant-api...` |
| Anthropic Admin keys | `sk-ant-admin...` |
| OpenAI API keys | `sk-...` |
| AWS Access Keys | `AKIA...` |
| AWS Secret Keys | Base64-encoded 40-char strings in quotes |
| Private Keys | `-----BEGIN * PRIVATE KEY-----` |
| GitHub Tokens | `ghp_...`, `ghs_...`, etc. |
| Generic secrets/passwords | `"secret": "..."`, `"password": "..."` |
| Generic API keys | `"api_key": "..."` |
| Forbidden files | `.env`, `.pem`, `.key`, `credentials.json`, `id_rsa`, etc. |

**Installation also updates `.gitignore`** with common secret patterns if they're missing.

**Bypass:** `git commit --no-verify` (document why in the commit message).

---

## Plugin

### agent-chat-channel

A PostgreSQL-based messaging channel plugin for OpenClaw that allows agents to communicate via the `agent_chat` database table. Uses PostgreSQL `LISTEN`/`NOTIFY` for real-time message delivery.

**Location:** `agent-chat-channel/` (has its own README.md and SETUP.md)

**Key features:**
- Real-time notifications via PostgreSQL `NOTIFY`
- Mention-based routing — only processes messages where the agent is mentioned
- Deduplication via `agent_chat_processed` table
- Two-way messaging — routes incoming messages to agent sessions and sends replies back to the database
- Multiple account support — one gateway can serve multiple agents
- 1Password integration for database credentials

**How it works:**
1. Plugin connects to PostgreSQL and executes `LISTEN agent_chat`
2. On startup, checks for any unprocessed messages where agent name is in the `mentions` array
3. When a `NOTIFY` is received, queries for new messages targeting this agent
4. Routes each message to the agent's session via `runtime.handleInbound`
5. Marks message as processed in `agent_chat_processed`
6. Agent replies are inserted back into `agent_chat` with the agent as sender

**Database schema:**

```sql
-- Main chat messages table
CREATE TABLE agent_chat (
    id SERIAL PRIMARY KEY,
    channel TEXT NOT NULL DEFAULT 'default',
    sender TEXT NOT NULL,
    message TEXT NOT NULL,
    mentions TEXT[] DEFAULT '{}',
    reply_to INTEGER REFERENCES agent_chat(id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Track processed messages
CREATE TABLE agent_chat_processed (
    chat_id INTEGER REFERENCES agent_chat(id) ON DELETE CASCADE,
    agent TEXT NOT NULL,
    processed_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (chat_id, agent)
);
```

**Configuration:** See `agent-chat-channel/README.md` and `agent-chat-channel/SETUP.md` for full details.

---

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the system overview showing how these components relate to each other and to the broader NOVA ecosystem.

---

## License

MIT — do whatever you want with these.

---

*Made with 💜 by NOVA (Neural Oracle, Velvet Attitude)*
