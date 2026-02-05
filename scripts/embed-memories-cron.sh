#!/bin/bash
# Daily memory embedding cron job

LOG_FILE="$HOME/clawd/logs/embed-memories.log"
VENV="$HOME/clawd/scripts/tts-venv/bin/activate"
SCRIPT="$HOME/clawd/scripts/embed-memories.py"

echo "=== $(date -Iseconds) ===" >> "$LOG_FILE"
source "$VENV"
python "$SCRIPT" --source all >> "$LOG_FILE" 2>&1
echo "Exit code: $?" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
