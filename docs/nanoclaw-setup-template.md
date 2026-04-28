# NanoClaw Bot — Complete Setup Template

**Last synced: 2026-04-23**

**Use this document every time you deploy a new NanoClaw bot on a VPS.**
It captures all the steps, security hardening, and small operational details that are easy to miss. Fill in the project-specific placeholders (marked `[PLACEHOLDER]`) before starting.

Fork: `[your-github-username/nanoclaw]` · VPS: `[provider + region]` · v1.0

---

## Project-Specific Placeholders (Fill In Before Starting)

| Key | Value |
|-----|-------|
| Fork URL | `https://github.com/[username]/nanoclaw` |
| VPS IPv4 | `[x.x.x.x]` (run `curl -s ifconfig.me -4` on VPS) |
| VPS IPv6 | `[x:x:x:x::x]` (run `curl -s ifconfig.me` on VPS) |
| Assistant name | `[Bob / Andy / ...]` |
| Main WhatsApp group JID | `[found in messages.db after first WhatsApp connect]` |
| Google Cloud project | `[project name in GCP console]` |
| Google Maps APIs used | `[Distance Matrix API, Geocoding API, ...]` |
| Primary Google account | `[account that owns calendar/drive]` |
| System user name | `[nanoclaw / botname]` |

---

## 1. VPS Prerequisites

### 1.1 Install Runtime Dependencies

```bash
# Node.js 20+
node --version   # must be 20+

# Docker
docker ps        # must return without error

# SQLite3 CLI (for DB inspection and backup script)
which sqlite3 || apt install -y sqlite3

# Python 3 + pip (for skill scripts)
python3 --version
pip3 --version
```

⚠ Never assume these are present or at the right version. Always verify before proceeding.

### 1.2 SSH Hardening

```bash
# Disable password auth — key-only from this point
cat > /etc/ssh/sshd_config.d/hardening.conf << 'EOF'
PasswordAuthentication no
PermitRootLogin prohibit-password
EOF
systemctl reload ssh
```

Verify you can still connect with your key before closing the current session.

### 1.3 Firewall (UFW)

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw enable
ufw status
```

Add additional ports only when needed (e.g. 443 for webhooks). Principle: deny by default, open explicitly.

---

## 2. Clone & Initial NanoClaw Setup

### 2.1 Clone the Fork

```bash
git clone https://github.com/[username]/nanoclaw.git /root/nanoclaw
cd /root/nanoclaw
git remote -v   # confirm origin points to your fork
ls -la          # confirm src/, CLAUDE.md, package.json are present
```

✓ **Gate:** `/root/nanoclaw/` exists. `git remote -v` shows your fork as origin.

### 2.2 Run /setup

From inside `/root/nanoclaw/`, run the NanoClaw setup skill:

```
/setup
```

This installs npm dependencies, builds the Docker agent container, configures systemd, and creates the `groups/` directory structure.

✓ **Gate:** `/setup` completes with no errors. Docker container builds successfully.

---

## 3. Run NanoClaw as a Dedicated System User (Not Root)

**This is mandatory.** Running as root means any container escape or skill bug has full system access.

```bash
# Create system user (no home dir, no login shell)
useradd --system --no-create-home --shell /usr/sbin/nologin [nanoclaw]

# Add to docker group so it can manage containers
usermod -aG docker [nanoclaw]

# Transfer ownership of the nanoclaw directory
chown -R [nanoclaw]:[nanoclaw] /root/nanoclaw

# Update the systemd service to run as the new user
# Edit /etc/systemd/system/nanoclaw.service — add under [Service]:
#   User=[nanoclaw]
#   Group=[nanoclaw]
systemctl daemon-reload
systemctl restart nanoclaw
systemctl status nanoclaw   # confirm Active: running
```

⚠ **Known trap:** If nanoclaw was ever started as root before this step, it will have created `/tmp/onecli-proxy-ca.pem` owned by root. The new system user cannot overwrite it and containers will fail with `EACCES`. Fix:

```bash
rm /tmp/onecli-proxy-ca.pem   # nanoclaw user recreates it on next container start
```

Check the error log if containers fail silently after the user switch:

```bash
tail -40 /root/nanoclaw/logs/nanoclaw.error.log | grep "message\|EACCES\|Error"
```

✓ **Gate:** `systemctl status nanoclaw` shows the process running as `[nanoclaw]` user.

---

## 4. Add WhatsApp Channel

WhatsApp is a separate skill — not bundled in NanoClaw core:

```
/add-whatsapp
```

**MANUAL STEP — operator required:** Open WhatsApp on the target phone → three-dot menu → Linked Devices → Link a Device → scan the QR code. Session persists permanently — one-time action.

✓ **Gate:** WhatsApp session active. Test message received.

---

## 5. Configure the Main WhatsApp Group

After the first WhatsApp connection, NanoClaw syncs available groups into `messages.db`. Register the primary hub group:

```bash
# Find the group JID
sqlite3 /root/nanoclaw/store/messages.db "
  SELECT jid, name FROM chats
  WHERE jid LIKE '%@g.us'
  ORDER BY last_message_time DESC LIMIT 10;"
```

Register via the main group or directly in the DB. Key settings:

| Field | Value | Notes |
|-------|-------|-------|
| `requires_trigger` | `0` | All messages processed without @prefix |
| `is_main` | `0` or `1` | `1` = elevated privileges (group management, cross-group scheduling) |
| `trigger_pattern` | `@[AssistantName]` | Used by groups that DO require a trigger |

⚠ **Note:** Renaming a WhatsApp group changes only the display name — the JID stays the same. No code, DB, or config changes are needed when renaming. Only update docs and memory.

⚠ **Common mistake:** `requires_trigger` defaults to `1` in the schema. If you set a group as your main hub and don't explicitly set it to `0`, users must prefix every message with `@[AssistantName]` — the bot will silently ignore plain messages.

```bash
# Fix if needed
sqlite3 /root/nanoclaw/store/messages.db \
  "UPDATE registered_groups SET requires_trigger=0 WHERE jid='[group-jid]';"
systemctl restart nanoclaw
```

✓ **Gate:** A plain message (no trigger prefix) in the group gets a response.

---

## 6. Global Acknowledgement Rule

Add this to `groups/global/CLAUDE.md` so Bob acknowledges every request before starting work. Without this, users stare at silence while the container starts and tools run.

In the `## Communication` section, after the `mcp__nanoclaw__send_message` description, add:

```markdown
### Acknowledge before working

**Always** call `mcp__nanoclaw__send_message` with a short acknowledgement as the very first
thing you do when starting any task that involves tool use or takes more than a moment.

Keep it brief and natural. Examples (vary them):
- "ich bin dabei" / "on it" / "schon dran"
- "wird erledigt" / "einen Moment bitte" / "kurz"

Do this before any bash commands, file reads, API calls, or multi-step work.
For simple one-liner answers (no tools needed), skip the ack.
```

✓ **Gate:** Send a task to the group. Bob responds with an ack before the result arrives.

---

## 7. Google OAuth Setup

### 7.1 GCP Pre-Flight (Do on Your Laptop First)

1. GCP Console → APIs & Services → OAuth consent screen → Test users → add the Google account that owns the target calendar/drive
2. Enable the APIs your skill needs (Calendar API, Drive API, etc.)
3. Create OAuth credentials (Desktop app type) → download `credentials.json`
4. Open SSH tunnel for the OAuth callback:
   ```bash
   ssh -L 8080:localhost:8080 root@[VPS_IP] -N
   ```

### 7.2 Copy Credentials to VPS

```bash
# Run on your laptop:
scp /path/to/credentials.json root@[VPS_IP]:/root/nanoclaw/groups/[group-folder]/data/credentials.json
```

### 7.3 Run OAuth Flow

Claude Code runs the auth script, which prints an authorization URL. Open it in your browser, log in with the target Google account, click Allow. The browser will show a blank/empty page — this is success.

```bash
ls -la /root/nanoclaw/groups/[group-folder]/data/token.json   # must exist
```

⚠ `Access blocked: Error 403: access_denied` → you skipped step 7.1. Add the account as a test user first.

✓ **Gate:** `token.json` present. Test API call returns HTTP 200.

---

## 8. Google Maps API Key (if using Maps)

### 8.1 Get the VPS IP

```bash
curl -s ifconfig.me -4   # IPv4
curl -s ifconfig.me      # IPv6 (if shown)
```

### 8.2 Create and Restrict the Key (GCP Console — Manual)

1. GCP Console → APIs & Services → Credentials → Create Credentials → API Key
2. Click the new key → Edit
3. **Application restrictions** → IP addresses → add both IPv4 and IPv6 of the VPS
4. **API restrictions** → Restrict key → select only the APIs your skill uses:
   - `[Distance Matrix API]` (for routing)
   - `[Geocoding API]` (for address → coordinates)
   - Add others only if explicitly needed
5. Save → copy the key

### 8.3 Add to .env

```bash
echo "GOOGLE_MAPS_API_KEY=[your-key]" >> /root/nanoclaw/.env
```

Confirm `.env` is in `.gitignore` before any `git push`:

```bash
grep "^\.env" /root/nanoclaw/.gitignore   # must match
```

⚠ An unrestricted Maps API key is a billing liability. If the key leaks, anyone can use it. IP restriction + API restriction means a leaked key is useless to anyone outside your VPS. **Do this before the first real API call — not after.**

⚠ If the VPS IP ever changes (migration, provider change), update the restriction in GCP Console or the Maps API will return 403 silently.

✓ **Gate:** Test Maps API call from VPS returns 200. Test call from your laptop returns 403.

---

## 9. DB Backup (Daily)

Both `messages.db` (conversation history, registered groups, scheduled tasks) and any skill-specific databases exist only on the VPS — they are git-ignored and have no automatic backup.

```bash
mkdir -p /root/nanoclaw/scripts

cat > /root/nanoclaw/scripts/backup-db.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail
BACKUP_DIR="/root/nanoclaw/backups"
DATE=$(date +%Y-%m-%d)
DEST="$BACKUP_DIR/$DATE"
mkdir -p "$DEST"

sqlite3 /root/nanoclaw/store/messages.db ".backup '$DEST/messages.db'"
# Add additional skill DBs here:
# sqlite3 /root/nanoclaw/groups/[folder]/data/[skill].db ".backup '$DEST/[skill].db'"

find "$BACKUP_DIR" -maxdepth 1 -type d -name "????-??-??" -mtime +7 -exec rm -rf {} +
echo "[$(date -Iseconds)] Backup complete → $DEST"
SCRIPT

chmod +x /root/nanoclaw/scripts/backup-db.sh

# Cron: daily at 03:00
echo "0 3 * * * root /root/nanoclaw/scripts/backup-db.sh >> /root/nanoclaw/logs/backup.log 2>&1" \
  > /etc/cron.d/nanoclaw-backup

# Run immediately to verify
bash /root/nanoclaw/scripts/backup-db.sh
ls /root/nanoclaw/backups/$(date +%Y-%m-%d)/
```

Uses SQLite's `.backup` command — safe to run while the DB is live (no lock conflicts).

✓ **Gate:** First backup folder created with correct DB files. `wc -c` shows non-zero size.

---

## 10. Log Rotation

NanoClaw writes to `logs/nanoclaw.log` and `logs/nanoclaw.error.log` continuously with no size limit. Without rotation these grow forever.

```bash
cat > /etc/logrotate.d/nanoclaw << 'EOF'
/root/nanoclaw/logs/*.log {
    daily
    rotate 14
    compress
    missingok
    notifempty
    copytruncate
}
EOF

logrotate --debug /etc/logrotate.d/nanoclaw   # verify config valid
```

`copytruncate` lets the running nanoclaw process keep its file handle — no restart needed.

✓ **Gate:** `logrotate --debug` runs without errors.

---

## 11. Daily Health Check (via Nanoclaw Scheduled Task)

Set up a daily script that checks the things most likely to break silently. Bob stays silent on pass; sends a WhatsApp alert to the main group if something fails.

Insert directly into the DB (or have Bob schedule it from the main group):

```python
import sqlite3, json
from datetime import datetime, timezone

SCRIPT = r"""#!/bin/bash
failures=()

# Check 1: Google token.json present
if [ ! -f /workspace/group/data/token.json ]; then
  failures+=("Google token.json fehlt")
fi

# Check 2: Google [API] reachable — replace with your actual API check
# if [ -f /workspace/group/data/token.json ]; then
#   python3 -c "..." 2>/dev/null || failures+=("[API] nicht erreichbar")
# fi

# Check 3: OneCLI auth gateway reachable
# TCP-level check — agent containers have HTTP_PROXY pointed at OneCLI itself,
# so an HTTP/curl probe to OneCLI would self-proxy and fail spuriously.
# curl is also not in the agent image; use python socket.
python3 -c "import socket; socket.create_connection(('host.docker.internal', 10254), timeout=5).close()" 2>/dev/null \
  || failures+=("OneCLI-Gateway nicht erreichbar")

if [ ${#failures[@]} -eq 0 ]; then
  echo '{"wakeAgent":false}'
else
  python3 -c "
import json,sys
print(json.dumps({'wakeAgent':True,'data':{'failures':sys.argv[1:]}}))" "${failures[@]}"
fi"""

PROMPT = """Daily health check found problems. Send a WhatsApp message listing the issues
from data.failures. Keep it short — no further action, just inform."""

db = sqlite3.connect('/root/nanoclaw/store/messages.db')
db.execute("DELETE FROM scheduled_tasks WHERE id='healthcheck-daily'")
db.execute("""
  INSERT INTO scheduled_tasks
    (id, group_folder, chat_jid, prompt, schedule_type, schedule_value,
     next_run, status, created_at, context_mode, script)
  VALUES (?,?,?,?,?,?,?,?,?,?,?)
""", (
    'healthcheck-daily',
    '[group-folder]',           # e.g. 'document_organizer'
    '[main-group-jid]',         # e.g. '120363426377913092@g.us'
    PROMPT,
    'cron', '0 8 * * *',
    '[YYYY-MM-DD]T06:00:00.000Z',  # next 8am Berlin (UTC+2 in summer)
    'active',
    datetime.now(timezone.utc).isoformat(),
    'isolated',
    SCRIPT,
))
db.commit()
print("Health check task inserted")
```

What to check (only things that break silently):
- `token.json` present (Google OAuth — can be revoked without warning)
- API reachability (Drive, Calendar — catches expired/revoked tokens)
- OneCLI gateway up (auth proxy — if down, no containers can authenticate)

What NOT to check (you'll notice without it):
- nanoclaw service status — if it's down, the task won't fire anyway
- node/docker versions — never change between restarts

✓ **Gate:** Verify task in DB: `sqlite3 store/messages.db "SELECT id, status, next_run FROM scheduled_tasks;"`

---

## 12. Build Your Skill

Skills live at `.claude/skills/[skill-name]/`. Each skill needs at minimum:

- `SKILL.md` — workflow instructions Claude reads when the skill is active
- Any supporting scripts (Python, bash) in the same directory

Skill guidelines:
- Operational skills are instruction-only (no code merge required)
- Never modify `src/` — all custom logic stays in `.claude/skills/` and `groups/`
- Supporting scripts receive JSON on stdin or as a positional argument, return JSON on stdout
- All file paths inside the container use `/workspace/project/` (project root) and `/workspace/group/` (group data)

Add the skill trigger to the group's `CLAUDE.md` so Bob knows when to activate it.

```bash
git add .claude/skills/[skill-name]/ groups/[group-folder]/
git commit -m 'feat: add [skill-name] skill'
git push origin main
```

✓ **Gate:** Test trigger message in WhatsApp returns expected skill output.

### 12.1 Google Drive Document Organizer — Initial Drive Setup

After OAuth is complete and the group is registered, run `setup_drive` once to create the folder structure in Drive and write `config.json`:

```bash
python3 /root/nanoclaw/.claude/skills/gdrive-document-organizer/organizer.py "$(cat <<'EOF'
{
  "action": "setup_drive",
  "data_dir": "/root/nanoclaw/groups/[group-folder]/data",
  "root_name": "Document Organizer",
  "timezone": "Europe/Berlin"
}
EOF
)"
```

This creates under "My Drive":
```
Document Organizer/
├── Inbox/
├── Unsortiert/
├── Eingangsrechnungen/
├── Ausgangsrechnungen/
├── Krankenkasse/
├── Steuer/
├── Verträge/
└── Sonstiges/
```

And writes `groups/[group-folder]/data/config.json` with `rootFolderId`, `inboxFolderId`, and `unsortiertFolderId`.

The user can rename, add, or delete category folders in Drive freely after this point — Bob always reads the live folder list at sort time. Only Inbox and Unsortiert are special and must not be deleted (Unsortiert is recreated automatically if deleted; Inbox is fixed).

⚠ **Run only once per installation.** Re-running creates a second "Document Organizer" tree.

✓ **Gate:** `config.json` present with `rootFolderId`. Folders visible in Google Drive.

---

## 13. Commit Discipline & .gitignore

Before every `git push`:

```bash
# Confirm nothing sensitive is staged
git status
grep "^\.env" .gitignore          # .env must be excluded
grep "^store/" .gitignore          # messages.db must be excluded
grep "token\.json" .gitignore      # OAuth tokens must be excluded
grep "credentials\.json" .gitignore
```

Never commit: `.env`, `credentials.json`, `token.json`, `*.db`, `logs/`, `store/`.

All custom code changes get a commit. Git history = audit log.

---

## 14. Environment Audit (Run at the Start of Every Dev Session)

```bash
cd /root/nanoclaw
pwd && git remote -v
node --version
ls node_modules/.bin/tsx 2>/dev/null && echo 'deps OK' || echo 'FAIL: npm install'
docker ps
systemctl status nanoclaw --no-pager | head -5
ls -la groups/[group-folder]/data/
cat groups/[group-folder]/data/config.json 2>/dev/null || echo 'MISSING'
ls -la .claude/skills/[skill-name]/SKILL.md 2>/dev/null && echo 'skill OK' || echo 'MISSING'
```

---

## 15. Keeping the Fork Current

```bash
# First time only
git remote add upstream https://github.com/qwibitai/nanoclaw.git

# Monthly: review upstream changes
git fetch upstream
git log upstream/main --oneline -15

# Merge on a branch — never directly to main
git checkout -b upstream-review
git merge upstream/main
# Review. If good:
git checkout main && git merge upstream-review
git push origin main
```

Custom skill files (`.claude/skills/[skill-name]/`, `groups/[group-folder]/`) live in paths upstream never touches — merges will not overwrite them.

---

## 16. Post-Setup Verification Checklist

Run through this after all steps complete:

- [ ] nanoclaw service running as `[system-user]`, not root (`systemctl status nanoclaw`)
- [ ] UFW active, only port 22 open (`ufw status`)
- [ ] SSH password auth disabled (`sshd -T | grep passwordauthentication`)
- [ ] `.env` in `.gitignore` (`grep "^\.env" .gitignore`)
- [ ] `token.json` and `credentials.json` in `.gitignore`
- [ ] Google Maps API key restricted to VPS IP + specific APIs only (GCP console)
- [ ] DB backup cron active (`cat /etc/cron.d/nanoclaw-backup`)
- [ ] Log rotation configured (`cat /etc/logrotate.d/nanoclaw`)
- [ ] Health check task in DB (`sqlite3 store/messages.db "SELECT id,status FROM scheduled_tasks;"`)
- [ ] Main WhatsApp group has `requires_trigger=0` if no prefix needed
- [ ] Global ack rule present in `groups/global/CLAUDE.md`
- [ ] `/tmp/onecli-proxy-ca.pem` owned by system user, not root (`ls -la /tmp/onecli-proxy-ca.pem`)
- [ ] Test trigger message in WhatsApp → Bob acks → skill responds correctly

---

## Appendix: Common Failure Modes

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Message received, bot silent, no container log | `requires_trigger=1` on a group that should process all messages | `UPDATE registered_groups SET requires_trigger=0 WHERE jid='...'`, restart |
| `EACCES: permission denied, open '/tmp/onecli-proxy-ca.pem'` | File created by a root run, nanoclaw user can't overwrite | `rm /tmp/onecli-proxy-ca.pem` |
| Container retries with backoff, no error detail | Check `nanoclaw.error.log` — usually credential or permission issue | `tail -40 logs/nanoclaw.error.log` |
| `Error 403: access_denied` during Google OAuth | Account not added as test user in GCP OAuth consent screen | Add account under Test Users, retry OAuth |
| Google Maps returns 403 | API key IP restriction doesn't include current VPS IP | Update restriction in GCP Console |
| Google Drive/Calendar returns 401 | OAuth token revoked or expired (refresh token invalidated) | Re-run OAuth flow, get new `token.json` |
| Health check task fires but Bob doesn't respond | Anthropic auth issue (OneCLI gateway has expired credentials) | Check OneCLI dashboard, re-authenticate |

---

*Template version: 1.0 — 2026-04-23*
*Update this file whenever a new recurring setup issue is discovered.*
