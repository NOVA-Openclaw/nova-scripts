# Agent Install Script

A minimal stub script that exists only for compatibility with the `NOVA-INSTALL.sh` convention.

## Purpose

Some NOVA‑related repositories include an `agent-install.sh` script that performs setup steps (installing dependencies, configuring databases, etc.). This repository has no installation requirements, so the script is a no‑op placeholder.

## Usage

```bash
./agent-install.sh
```

**Output:**
```
No installation steps for nova-scripts
```

## Why It Exists

- Ensures the repository can be processed by automation that expects an `agent-install.sh` file.
- Provides a clear message that no installation is needed.
- Can be extended later if the repository gains installation requirements.

## Extending

If you need to add installation steps (e.g., installing Python dependencies, setting up database tables), edit `agent-install.sh` and replace the stub with the appropriate commands.

Example:

```bash
#!/bin/bash
echo "Installing dependencies..."
pip install -r requirements.txt
psql -d nova_memory -f schema.sql
```

## Related Files

- `README.md` – overall repository documentation.
- `ARCHITECTURE.md` – high‑level architecture.

---

*Made with 💜 by NOVA*