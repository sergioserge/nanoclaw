# Setup Notes — Lessons Learned

One line per lesson. Format: `YYYY-MM-DD | section | lesson`
This file feeds the `update-setup-template` skill. Do not delete old entries — they are the audit trail.

---

2026-04-23 | permissions | /tmp/onecli-proxy-ca.pem becomes root-owned if nanoclaw ever ran as root before the user migration — delete it so the system user can recreate it; containers will fail with EACCES otherwise
2026-04-23 | group-config | requires_trigger defaults to 1 in the schema — always set it explicitly to 0 for hub groups or Bob silently ignores all messages without the @prefix
2026-04-23 | group-config | WhatsApp group display name rename does not change the JID — only update docs/memory, no code or DB changes needed
2026-04-23 | global-ack | Global acknowledgement rule belongs in groups/global/CLAUDE.md, not in individual skills — putting it in a skill means it only fires for that skill, not all operations
2026-04-23 | health-check | Use nanoclaw's native scheduled task (script field in scheduled_tasks table) for the daily health check, not an external cron — the script runs bash before waking the agent, so Bob is only invoked when something is actually wrong
2026-04-23 | backup | Use sqlite3 .backup command for live DB backup — safe while DB is open, no lock conflicts, unlike cp
2026-04-23 | maps-api | Restrict Google Maps API key to VPS IP (both IPv4 and IPv6) + only the specific APIs used (Distance Matrix + Geocoding) — do this before the first real API call, not after
2026-04-23 | maps-api | If VPS IP changes (migration, provider switch), update the GCP IP restriction or Maps API returns 403 silently with no obvious error message
2026-04-23 | group-config | Never symlink group CLAUDE.md files — each group must have its own real file. A shared symlink means both groups get the same instructions and the wrong skill activates
2026-04-23 | group-config | The physio assistant group had document_organizer instructions via shared symlink — Bob improvised as a generic assistant instead of running routing. Root cause of all 7 quality issues in that session.
2026-04-23 | group-config | Never set is_main=1 for a worker group — it mounts the full project root, causing Claude Code to load groups/main/CLAUDE.md (generic assistant) alongside the group's own CLAUDE.md. Use is_main=0 + containerConfig.additionalMounts instead.
2026-04-23 | group-config | Worker groups that need skills from the project root: use containerConfig additionalMounts + mount-allowlist at ~/.config/nanoclaw/mount-allowlist.json. Mount skill dir to containerPath="skill-name" → accessible at /workspace/extra/skill-name inside the container.
2026-04-23 | dockerfile | Pre-install all skill Python dependencies in the Dockerfile — missing packages cause ~14-27s pip install on every run. Add requests + pytz for physio-routing; PyMuPDF + python-docx + openpyxl for document-organizer.
2026-04-23 | skill-config | Skill-specific credentials (e.g. Maps API key) belong in groups/<group>/data/.env — gitignored, mounted at /workspace/group/data/.env for is_main=0 containers. OneCLI only injects HTTP headers (not env vars), so .env in the group data dir is the right pattern for query-param API keys.
