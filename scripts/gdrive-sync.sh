#!/bin/bash
# gdrive-sync.sh - Sync a Google Drive folder with a local directory
# Uses gogcli (https://gogcli.sh) for Google Drive access
#
# Usage: ./gdrive-sync.sh [pull|push|status]
#
# Configuration: Set these variables or export them before running
#   LOCAL_DIR        - Local directory to sync (default: ~/gdrive-sync)
#   GDRIVE_FOLDER_ID - Google Drive folder ID (required)
#   GOG_ACCOUNT      - Google account email (or use gog's default)

set -e

# Configuration - customize these or set via environment
LOCAL_DIR="${LOCAL_DIR:-$HOME/gdrive-sync}"
GDRIVE_FOLDER_ID="${GDRIVE_FOLDER_ID:?Error: GDRIVE_FOLDER_ID must be set}"
ACCOUNT="${GOG_ACCOUNT:-}"

# Build account flag if specified
ACCOUNT_FLAG=""
[ -n "$ACCOUNT" ] && ACCOUNT_FLAG="--account $ACCOUNT"

mkdir -p "$LOCAL_DIR"

case "${1:-status}" in
  pull)
    echo "📥 Pulling from GDrive to $LOCAL_DIR..."
    gog drive ls --parent "$GDRIVE_FOLDER_ID" $ACCOUNT_FLAG --json | \
      jq -r '.files[] | "\(.id)\t\(.name)"' | \
      while IFS=$'\t' read -r id name; do
        echo "  Downloading: $name"
        gog drive download "$id" --out "$LOCAL_DIR/$name" $ACCOUNT_FLAG
      done
    echo "✅ Pull complete"
    ;;
    
  push)
    echo "📤 Pushing from $LOCAL_DIR to GDrive..."
    for file in "$LOCAL_DIR"/*; do
      [ -f "$file" ] || continue
      name=$(basename "$file")
      echo "  Uploading: $name"
      gog drive upload "$file" --parent "$GDRIVE_FOLDER_ID" $ACCOUNT_FLAG
    done
    echo "✅ Push complete"
    ;;
    
  status)
    echo "📊 GDrive Sync Status"
    echo ""
    echo "Remote files (GDrive):"
    gog drive ls --parent "$GDRIVE_FOLDER_ID" $ACCOUNT_FLAG
    echo ""
    echo "Local files ($LOCAL_DIR):"
    ls -la "$LOCAL_DIR" 2>/dev/null || echo "  (directory empty or doesn't exist)"
    ;;
    
  *)
    echo "Usage: $0 [pull|push|status]"
    echo ""
    echo "Environment variables:"
    echo "  GDRIVE_FOLDER_ID  - Google Drive folder ID (required)"
    echo "  LOCAL_DIR         - Local directory (default: ~/gdrive-sync)"
    echo "  GOG_ACCOUNT       - Google account email (optional)"
    exit 1
    ;;
esac
