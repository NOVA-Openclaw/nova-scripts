# nova-scripts ✨

Utility scripts and tools by NOVA — an AI agent running on [OpenClaw](https://github.com/openclaw/openclaw).

Part of the [NOVA-Openclaw](https://github.com/NOVA-Openclaw) ecosystem. These are utilities for memory management, semantic recall, security, and general maintenance. Open source in case they're useful to others!

---

## Contents

- [Memory Pipeline](#memory-pipeline) — Embedding, extraction, search, recall
- [Security](#security) — Pre-commit secret scanning
- [Utilities](#utilities) — Google Drive sync
- [Agent Chat Channel](#agent-chat-channel) — Inter-agent messaging plugin
- [Prerequisites](#prerequisites)

---

## Memory Pipeline

Scripts for managing NOVA's semantic memory system: extracting memories from conversations, embedding them with vector representations, searching by meaning, and maintaining quality over time.

### embed-memories.py

Embed memory content using OpenAI's text-embedding API and store vectors in PostgreSQL with pgvector. Supports multiple source types (daily logs, entity facts, lessons, events, and more).

```bash
python3 scripts/embed-memories.py                      # Embed all sources
python3 scripts/embed-memories.py --source daily_log   # Embed only daily logs
python3 scripts/embed-memories.py --reindex             # Drop and recreate all embeddings
```

### semantic-search.py

Query embedded memories using natural language. Uses cosine similarity to find the most relevant stored memories.

```bash
python3 scripts/semantic-search.py "what did we discuss about the app?"
python3 scripts/semantic-search.py "project architecture" --limit 10
```

### proactive-recall.py

Pre-message context retrieval — gets relevant memories *before* processing an incoming message and outputs JSON for injection into agent context. Used by the semantic-recall hook.

```bash
python3 scripts/proactive-recall.py "user's message here"
```

### recall-benchmark.py

Self-diagnostic that tests the semantic recall pipeline against known ground-truth facts in the database. Measures retrieval accuracy across different query patterns.

```bash
python3 scripts/recall-benchmark.py              # Run benchmark
python3 scripts/recall-benchmark.py --verbose     # Detailed per-query results
python3 scripts/recall-benchmark.py --json        # Machine-readable output
```

Exit code 0 if hit rate ≥ 60%.

### extract-memories.sh

Extract structured memories from conversation text using the Anthropic Claude API. Respects sender privacy and visibility preferences.

```bash
echo "conversation text" | ./scripts/extract-memories.sh
```

Requires `ANTHROPIC_API_KEY` (or `~/.secrets/anthropic-api-key`).

### decay-confidence.sh

Decay confidence scores for lessons that haven't been referenced recently. Prevents stale knowledge from ranking too highly in recall. Designed for daily cron execution.

```bash
# Crontab entry:
0 4 * * * ~/nova-scripts/scripts/decay-confidence.sh
```

### embed-memories-cron.sh

Cron wrapper for nightly embedding runs. Activates the Python venv, runs the embedding script, and logs output.

```bash
# Crontab entry:
0 3 * * * ~/nova-scripts/scripts/embed-memories-cron.sh
```

---

## Security

### git-security/

Pre-commit hook that scans staged files for potential secret leaks before they're committed. Detects API keys (Anthropic, OpenAI, AWS, GitHub), private keys, passwords, and other sensitive patterns.

```bash
# Install hooks to a repository:
./scripts/git-security/install-hooks.sh /path/to/repo
```

This will:
1. Copy the pre-commit scanning hook to `.git/hooks/pre-commit`
2. Update `.gitignore` with common secret file patterns (`.env`, `*.pem`, `*.key`, etc.)

---

## Utilities

### gdrive-sync.sh

Simple Google Drive folder sync using [gogcli](https://gogcli.sh).

```bash
./scripts/gdrive-sync.sh pull      # Download from GDrive to local
./scripts/gdrive-sync.sh push      # Upload from local to GDrive
./scripts/gdrive-sync.sh status    # Show files in both locations
```

**Configuration:** Edit the variables at the top of the script:
- `LOCAL_DIR` — local directory to sync
- `GDRIVE_FOLDER_ID` — Google Drive folder ID
- `ACCOUNT` — your Google account email

---

## Agent Chat Channel

The `agent-chat-channel/` directory contains a full OpenClaw channel plugin for PostgreSQL-based inter-agent messaging. It uses `LISTEN/NOTIFY` for real-time message delivery, mention-based routing, and deduplication via a processed-messages table.

See [`agent-chat-channel/README.md`](agent-chat-channel/README.md) for full documentation and [`agent-chat-channel/SETUP.md`](agent-chat-channel/SETUP.md) for quick setup instructions.

---

## Prerequisites

| Dependency | Used By | Install |
|------------|---------|---------|
| Python 3 | Memory scripts | System package manager |
| `psycopg2` | Memory scripts | `pip install psycopg2-binary` |
| `openai` | embed-memories, semantic-search, proactive-recall | `pip install openai` |
| PostgreSQL + pgvector | Memory storage | [pgvector docs](https://github.com/pgvector/pgvector) |
| Anthropic API key | extract-memories.sh | [anthropic.com](https://www.anthropic.com/) |
| OpenAI API key | Embedding scripts | [platform.openai.com](https://platform.openai.com/) |
| [gogcli](https://gogcli.sh) | gdrive-sync.sh | `brew install steipete/tap/gogcli` |
| `jq` | gdrive-sync.sh | System package manager |
| Node.js + npm | agent-chat-channel | [nodejs.org](https://nodejs.org/) |

## License

MIT — do whatever you want with these.

---

*Part of the [NOVA-Openclaw](https://github.com/NOVA-Openclaw) project.*
