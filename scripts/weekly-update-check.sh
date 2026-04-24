#!/bin/bash
# Weekly check for pending apt updates and reboot requirement. Sends a WhatsApp
# notification via nanoclaw IPC if action is needed. Silent if everything is current.
set -euo pipefail

IPC_DIR="/root/nanoclaw/data/ipc/whatsapp_physio_assistant/messages"
JID="120363427507459909@g.us"

UPDATES=$(apt list --upgradable 2>/dev/null | grep -vc "^Listing" || true)
REBOOT=0
[ -f /var/run/reboot-required ] && REBOOT=1

[ "$UPDATES" -eq 0 ] && [ "$REBOOT" -eq 0 ] && exit 0

PARTS=()
[ "$UPDATES" -gt 0 ] && PARTS+=("$UPDATES package(s) pending")
[ "$REBOOT" -eq 1 ]  && PARTS+=("reboot required (kernel update)")

MSG="[System] $(date '+%Y-%m-%d'): $(IFS=', '; echo "${PARTS[*]}")."

TMPFILE=$(mktemp)
printf '{"type":"message","chatJid":"%s","text":"%s"}' "$JID" "$MSG" > "$TMPFILE"
chown nanoclaw:nanoclaw "$TMPFILE"
chmod 660 "$TMPFILE"
mv "$TMPFILE" "$IPC_DIR/$(date +%s%N).json"

echo "[$(date -Iseconds)] Update notification sent: $MSG"
