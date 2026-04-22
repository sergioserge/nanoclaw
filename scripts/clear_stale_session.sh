#!/bin/bash
# Clears Bob's session_id if no messages in the last 10 minutes.
# Run via cron every 10 minutes: */10 * * * * /root/nanoclaw/scripts/clear_stale_session.sh

DB="/root/nanoclaw/store/messages.db"
GROUP_FOLDER="whatsapp_physio_assistant"
CHAT_JID="120363427507459909@g.us"
TIMEOUT_MINUTES=10

recent=$(sqlite3 "$DB" "
  SELECT COUNT(*) FROM messages
  WHERE chat_jid = '$CHAT_JID'
  AND datetime(timestamp) > datetime('now', '-${TIMEOUT_MINUTES} minutes');
")

if [ "$recent" -eq 0 ]; then
  existing=$(sqlite3 "$DB" "
    SELECT session_id FROM sessions WHERE group_folder = '$GROUP_FOLDER';
  ")

  if [ -n "$existing" ]; then
    sqlite3 "$DB" "DELETE FROM sessions WHERE group_folder = '$GROUP_FOLDER';"
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) session cleared for $GROUP_FOLDER (idle >${TIMEOUT_MINUTES}min)"
  fi
fi
