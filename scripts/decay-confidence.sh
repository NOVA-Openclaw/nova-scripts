#!/bin/bash
# Decay confidence scores for lessons not referenced recently
# Run via cron: 0 4 * * * ~/clawd/scripts/decay-confidence.sh

set -e

LOG_FILE="/home/nova/clawd/logs/confidence-decay.log"
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date -Iseconds)] $1" >> "$LOG_FILE"
}

log "Starting confidence decay..."

# Decay lessons not referenced in 30+ days by 5%
# Minimum confidence floor of 0.1 (never fully forget)
DECAYED=$(psql -d nova_memory -t -c "
    UPDATE lessons 
    SET confidence = GREATEST(confidence * 0.95, 0.1)
    WHERE (last_referenced IS NULL OR last_referenced < NOW() - INTERVAL '30 days')
      AND confidence > 0.1
    RETURNING id;
" | grep -c '[0-9]' || echo "0")

log "Decayed $DECAYED lessons"

# Log any lessons that have dropped below 0.3 (candidates for review)
LOW_CONFIDENCE=$(psql -d nova_memory -t -A -c "
    SELECT id, ROUND(confidence::numeric, 2), LEFT(lesson, 50) 
    FROM lessons 
    WHERE confidence < 0.3 AND confidence > 0.1
    ORDER BY confidence ASC
    LIMIT 5;
")

if [ -n "$LOW_CONFIDENCE" ]; then
    log "Low confidence lessons (consider reviewing):"
    echo "$LOW_CONFIDENCE" | while read line; do
        log "  $line"
    done
fi

log "Confidence decay complete"
