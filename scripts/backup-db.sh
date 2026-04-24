#!/bin/bash
# Daily backup of nanoclaw SQLite databases. Keeps 7 days of backups.
set -euo pipefail

BACKUP_DIR="/root/nanoclaw/backups"
DATE=$(date +%Y-%m-%d)
DEST="$BACKUP_DIR/$DATE"

mkdir -p "$DEST"

sqlite3 /root/nanoclaw/store/messages.db ".backup '$DEST/messages.db'"
sqlite3 /root/nanoclaw/groups/document_organizer/data/documents.db ".backup '$DEST/documents.db'"
sqlite3 /root/nanoclaw/groups/physio-copilot/data/physio.db ".backup '$DEST/physio.db'"

# Remove backups older than 7 days
find "$BACKUP_DIR" -maxdepth 1 -type d -name "????-??-??" -mtime +7 -exec rm -rf {} +

echo "[$(date -Iseconds)] Backup complete → $DEST"
