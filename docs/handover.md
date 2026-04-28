# Handover: Dev → Prod

Fully remote. One short call (or screen share) needed for section 1.5 — everything else is async.

---

## Overview

**OAuth account:** `mobilephysiotherapie.pilot@gmail.com` — Bob authenticates here, full read/write Calendar access. GCP project is pre-existing (not under this email — pilot account just needs to be added as a test user).
**info@ sync:** `info@mobile-physiotherapie.koeln` calendar must be shared (read-only) with `mobilephysiotherapie.pilot@gmail.com` by whoever owns `info@`. One-time manual step in Google Calendar settings — no code change needed, Google handles live propagation.

**Inference model:** The bot's Claude inference runs under the client's **claude.ai subscription** (Pro or Max), not under an Anthropic API key. OneCLI injects the subscription session into containers. There is no Anthropic API key to create, copy, or rotate.

> The table below is grouped by dependency, not chronological order. Execute steps in the order given by Phase 1 → Phase 2 → Phase 3.

| # | Task | Who | Why | After |
|---|------|-----|-----|-------|
| 1 | Back up dev credentials on VPS | Sergej | Protects auth tokens in `whatsapp_physio_assistant/data/` — these files will be overwritten by OAuth. Only safe to proceed if dev state is recoverable. | — |
| 2 | Client gets claude.ai Pro/Max subscription | Client | The bot's inference and the Claude Code CLI both run under the client's claude.ai subscription post-handover. | — |
| 3 | Client logs into claude.ai on VPS browser flow (re-auth Claude Code CLI) | Sergej + Client | Client is the primary Claude Code user on this system — the active session must be theirs. Only step requiring the client live, since they must enter their own claude.ai password. One-time — session persists indefinitely. | 2 |
| 4 | Share `info@mobile-physiotherapie.koeln` calendar with `mobilephysiotherapie.pilot@gmail.com` (read-only) | Whoever owns `info@` | Bob reads the info@ calendar via the single pilot OAuth token — no second auth flow needed. Google propagates events live. | — |
| 5 | Add `mobilephysiotherapie.pilot@gmail.com` as test user in GCP; create "Physio Bot" calendar on pilot account | Client | Authorizes the pilot account for OAuth. The dedicated bot calendar is a safety guardrail — Bob writes only here, never to the primary calendar. | — |
| 6 | Client sends home address + pilot account password to Sergej via Signal | Client | Home address → `homeCoords` in config.json. Pilot password → Sergej uses it to log into the pilot account in his own browser during OAuth. | — |
| 7 | Run OAuth in Sergej's browser | Sergej | Generates token.json under the pilot account so Bob can read and write the client's calendar. SSH tunnel terminates on Sergej's laptop, so the redirect must complete in his browser. | 5, 6 |
| 8 | Configure config.json — calendarId, homeCoords | Sergej | Two values wrong by default; routing and calendar writes are broken until both are correct. | 6, 7 |
| 9 | Create WhatsApp group, add client and co-pilot | Sergej | Creates the production channel. Prd group is separate from dev so both can run in parallel during transition. | 1, 8 |
| 10 | Register prd group JID in NanoClaw DB | Sergej | NanoClaw ignores messages from unregistered groups. Client must send at least one message first so the JID appears in the DB. | 9 (client must have sent a message) |
| 11 | End-to-end test — co-pilot sends booking, Bob responds | Both | Verifies subscription, Calendar connection, and routing all work together. First real signal that prd is healthy. | 10 |
| 12 | Document organizer activation | Sergej | Separate feature — kept out of main handover to avoid scope creep on launch day. | 11, separate session |
| 13 | Final WhatsApp migration — re-link NanoClaw to client's number, client scans QR | Both | Makes the system fully independent of Sergej's phone. Deferred until stable — premature migration removes the safety net. | 12, once stable in prod |

---

## Group Folder Reference

| Group | Folder | Purpose |
|-------|--------|---------|
| Dev routing | `groups/whatsapp_physio_assistant_dev/data/` | Sergej's calendar — untouched during handover |
| Prd routing | `groups/whatsapp_physio_assistant/data/` | Client's calendar — token.json and config.json updated during handover |
| Document organizer | `groups/document_organizer/data/` | Activated separately in Phase 3 |

---

## Phase 1 — Async Prep

Sections 1.1–1.2 are client async tasks. Sections 1.3–1.4 are Sergej's tasks. Section 1.5 is the only step that needs the client live (claude.ai re-auth — they enter their own password).

### 1.0 Sergej: Back Up Dev Credentials

Do this first. The OAuth run (section 1.3) overwrites `token.json` in `whatsapp_physio_assistant/data/` — back it up before proceeding.

```bash
cd /root/nanoclaw
cp groups/whatsapp_physio_assistant/data/credentials.json \
   groups/whatsapp_physio_assistant/data/credentials.dev.json
cp groups/whatsapp_physio_assistant/data/token.json \
   groups/whatsapp_physio_assistant/data/token.dev.json
```

### 1.1 Client: claude.ai Pro/Max Subscription

The bot's Claude inference and the Claude Code CLI both run under the client's claude.ai subscription. There is no Anthropic API key — OneCLI uses the subscription session.

- [ ] Go to claude.ai → log in or create account → upgrade to **Pro** (or **Max**)
- [ ] No credentials to send — the client logs in themselves during section 1.5

### 1.2 Client: GCP Test User + Bot Calendar + info@ Share + Address + Pilot Password

The GCP project already exists — no new project or credentials needed. All of this is async, no coordination required.

**Add pilot account as GCP test user** (whoever has GCP Console access):
- [ ] Open console.cloud.google.com → log in as the GCP project owner
- [ ] APIs & Services → OAuth consent screen → Test users → **Add users** → add `mobilephysiotherapie.pilot@gmail.com`

**Create the bot calendar on the pilot account (safety guardrail):**

Bob writes all new appointments to a dedicated "Physio Bot" calendar. The therapist sees both overlaid in Google Calendar. Bob never touches the primary calendar until confirmed reliable.

- [ ] Open calendar.google.com → logged in as `mobilephysiotherapie.pilot@gmail.com`
- [ ] Left sidebar → **Other calendars** → **+** → **Create new calendar**
- [ ] Name it **"Physio Bot"**, leave everything else default → **Create calendar**
- [ ] Settings → click "Physio Bot" → scroll to "Calendar ID" → send to Sergej

**Share `info@mobile-physiotherapie.koeln` calendar with pilot account** (done by whoever manages `info@`):
- [ ] Open calendar.google.com → logged in as `info@mobile-physiotherapie.koeln`
- [ ] Settings (gear icon) → click the calendar to share → **Share with specific people** → add `mobilephysiotherapie.pilot@gmail.com` → permission: **"See all event details"** → Send
- [ ] No code change needed — Bob reads it automatically via the pilot OAuth token once shared.

**Send to Sergej via Signal:**
- [ ] Home address (for `homeCoords` in config.json)
- [ ] Password for `mobilephysiotherapie.pilot@gmail.com` (Sergej uses it to log into the pilot account during OAuth)

### 1.3 Sergej: Run OAuth

Sergej runs this alone in his own browser. The OAuth redirect lands on `localhost:8080` via the SSH tunnel on Sergej's laptop, so the click must happen there. Sergej logs into the pilot account using the password from section 1.2.

`oauth_flow.py` and `credentials.json` are already in `groups/whatsapp_physio_assistant/data/`.

- [ ] Open SSH tunnel (keep open until OAuth completes):
  ```bash
  ssh -L 8080:localhost:8080 root@178.105.3.245 -N
  ```
- [ ] In a second terminal, run the OAuth script on the VPS:
  ```bash
  python3 /root/nanoclaw/groups/whatsapp_physio_assistant/data/oauth_flow.py
  ```
- [ ] Copy the printed URL **as a single line** (it must end with `&state=XXXX`, not `googleapis.com` — line-wrap truncation breaks the scope) → open in Sergej's browser → log in as `mobilephysiotherapie.pilot@gmail.com` → click Allow → blank page = success
- [ ] Verify token was written:
  ```bash
  ls -la /root/nanoclaw/groups/whatsapp_physio_assistant/data/token.json
  ```

### 1.4 Sergej: Configure Prd Group

- [ ] Find the Physio Bot calendarId (or use the value the client sent):
  ```bash
  python3 -c "
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
creds = Credentials.from_authorized_user_file(
    '/root/nanoclaw/groups/whatsapp_physio_assistant/data/token.json')
service = build('calendar', 'v3', credentials=creds)
for c in service.calendarList().list().execute()['items']:
    print(c['id'], '|', c['summary'])
"
  ```
- [ ] Geocode the client's home address from section 1.2 (use one of):
  - Google Maps in browser: search the address → right-click the pin → click the coordinates to copy `lat, lng`
  - Or via Geocoding API:
    ```bash
    curl -s "https://maps.googleapis.com/maps/api/geocode/json?address=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' 'PASTE_ADDRESS_HERE')&key=$GOOGLE_MAPS_API_KEY" \
      | python3 -c "import json,sys; print(json.load(sys.stdin)['results'][0]['geometry']['location'])"
    ```
- [ ] Write the Physio Bot calendarId and homeCoords into config.json:
  ```bash
  python3 -c "
import json
path = '/root/nanoclaw/groups/whatsapp_physio_assistant/data/config.json'
with open(path) as f: cfg = json.load(f)
cfg['calendarId'] = 'PASTE_BOT_CALENDAR_ID_HERE'  # the 'Physio Bot' calendar, NOT the primary calendar
cfg['homeCoords'] = {'lat': 0.0, 'lng': 0.0}  # paste lat/lng from the geocoding step above
cfg.pop('note', None)
with open(path, 'w') as f: json.dump(cfg, f, indent=2)
print('Updated:', cfg['calendarId'], cfg['homeCoords'])
"
  ```
- [ ] Verify Calendar API:
  ```bash
  python3 -c "
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import json
path = '/root/nanoclaw/groups/whatsapp_physio_assistant/data/'
cfg = json.load(open(path + 'config.json'))
creds = Credentials.from_authorized_user_file(path + 'token.json')
service = build('calendar', 'v3', credentials=creds)
result = service.calendarList().get(calendarId=cfg['calendarId']).execute()
print('OK:', result['summary'])
"
  ```

### 1.5 Sergej + Client: Re-auth Claude Code CLI

The Claude Code CLI on the VPS currently runs under Sergej's claude.ai account. It must be switched to the client's account.

**Prerequisite:** Client has completed section 1.1 (claude.ai Pro/Max subscription).

This step requires the client live — they must enter their own claude.ai password in the browser. Schedule a short call or screen share.

- [ ] On VPS, log out the current session:
  ```bash
  claude auth logout
  ```
- [ ] Start re-auth — a browser URL will be printed (no SSH tunnel needed, opens on any device):
  ```bash
  claude
  ```
- [ ] Send the printed URL to the client → they open it in any browser → log in as their claude.ai account → complete the auth flow → terminal confirms login
- [ ] Verify the right account is active:
  ```bash
  claude auth status
  ```

✓ Session persists indefinitely — no expiry unless explicitly logged out.

✓ **Phase 1 gate — verify before Phase 2:**
- Dev backup files (`credentials.dev.json`, `token.dev.json`) present in `whatsapp_physio_assistant/data/`
- `token.json` in `whatsapp_physio_assistant/data/` is the new pilot account token (calendar list shows pilot account calendars, not `travelnomad1234@gmail.com`)
- Calendar API returns `OK: Physio Bot`
- `config.json` has no `note` field, correct `calendarId` (Physio Bot), and real `homeCoords`
- `claude auth status` shows the client's email and `subscriptionType` is `pro` or `max`

---

## Phase 2 — WhatsApp Setup (Fully Remote)

NanoClaw runs on Sergej's WhatsApp number. No QR scan by the client is needed. Sergej creates the group and adds the client and co-pilot.

### 2.1 Create the Prd WhatsApp Group

On Sergej's phone:

- [ ] Open WhatsApp → New Group
- [ ] Add the client (`lange@mobile-physiotherapie.koeln` phone) and the co-pilot
- [ ] Name the group e.g. **"Physio Assistant"** (can be renamed later)
- [ ] Ask the client to send any message in the group so it syncs into NanoClaw

### 2.2 Register the Prd Group in NanoClaw

- [ ] Find the group JID:
  ```bash
  sqlite3 /root/nanoclaw/store/messages.db \
    "SELECT jid, name FROM chats WHERE jid LIKE '%@g.us' ORDER BY last_message_time DESC LIMIT 5;"
  ```
- [ ] Register the prd group (replaces any existing entry for the same folder):
  ```bash
  sqlite3 /root/nanoclaw/store/messages.db \
    "INSERT OR REPLACE INTO registered_groups (jid, name, folder, trigger_pattern, added_at, container_config, requires_trigger, is_main)
     VALUES ('<NEW_JID>', 'Physio Assistant', 'whatsapp_physio_assistant', '@Bob', datetime('now'),
       '{\"additionalMounts\":[{\"hostPath\":\"/root/nanoclaw/.claude/skills/physio-routing\",\"containerPath\":\"physio-routing\",\"readonly\":true}]}',
       0, 0);"
  ```
- [ ] Remove the old dev-style Physio Assistant entry if still present:
  ```bash
  sqlite3 /root/nanoclaw/store/messages.db \
    "DELETE FROM registered_groups WHERE folder='whatsapp_physio_assistant' AND jid != '<NEW_JID>';"
  ```
- [ ] Restart NanoClaw:
  ```bash
  systemctl restart nanoclaw
  ```

### 2.3 Verify End-to-End

- [ ] Client or co-pilot sends a test booking request in the group
- [ ] Bob responds with a routing suggestion — this also confirms the claude.ai subscription (section 1.5) and the Calendar connection (section 1.3)

✓ **Phase 2 gate:** Bob responds correctly to a booking request in the new group.

---

## Phase 3 — Document Organizer (Separate Session, When Feature Goes Live)

Can be done remotely. Requires Phase 1 and Phase 2 to be complete.

### 3.1 Register the Document Organizer WhatsApp Group

- [ ] Sergej creates a second WhatsApp group (or uses an existing one) and adds the client
- [ ] Client sends any message in the group
- [ ] Find the JID:
  ```bash
  sqlite3 /root/nanoclaw/store/messages.db \
    "SELECT jid, name FROM chats WHERE jid LIKE '%@g.us' ORDER BY last_message_time DESC LIMIT 5;"
  ```
- [ ] Register the group:
  ```bash
  sqlite3 /root/nanoclaw/store/messages.db \
    "INSERT OR REPLACE INTO registered_groups (jid, name, folder, trigger_pattern, added_at, requires_trigger)
     VALUES ('<JID>', 'Document Organizer', 'document_organizer', '@Bob', datetime('now'), 0);"
  ```
- [ ] Restart NanoClaw:
  ```bash
  systemctl restart nanoclaw
  ```

### 3.2 Copy Token to Document Organizer Group

```bash
cp /root/nanoclaw/groups/whatsapp_physio_assistant/data/token.json \
   /root/nanoclaw/groups/document_organizer/data/token.json
cp /root/nanoclaw/groups/whatsapp_physio_assistant/data/credentials.json \
   /root/nanoclaw/groups/document_organizer/data/credentials.json
```

### 3.3 Create Drive Folder Structure

⚠ Run only once. Re-running creates a second "Document Organizer" tree.

```bash
python3 /root/nanoclaw/.claude/skills/gdrive-document-organizer/organizer.py "$(cat <<'EOF'
{
  "action": "setup_drive",
  "data_dir": "/root/nanoclaw/groups/document_organizer/data",
  "root_name": "Document Organizer",
  "timezone": "Europe/Berlin"
}
EOF
)"
```

- [ ] Confirm `config.json` was written with `rootFolderId`:
  ```bash
  cat /root/nanoclaw/groups/document_organizer/data/config.json
  ```
- [ ] Confirm the "Document Organizer" folder and its subfolders are visible in the client's Google Drive

✓ **Phase 3 gate:** `config.json` has `rootFolderId`. Folders visible in client's Drive. Test sort trigger in WhatsApp returns a response.

---

## Future Maintenance

**Google token expired/revoked:** Re-run section 1.3 (Run OAuth) — run `oauth_flow.py` from `groups/whatsapp_physio_assistant/data/` via SSH tunnel. Sergej does this alone in his own browser.

**Claude Code session expired:** Re-run section 1.5 (claude.ai re-auth). Requires the client live to enter their password.

**WhatsApp session expired:** Sergej re-scans the QR on his own phone — no client involvement needed.

---

## Future: Final WhatsApp Account Migration

> ⚠ **Not part of this handover — to be done later, once the system is stable in production.**

The current setup runs on Sergej's WhatsApp number. For the system to be fully independent of Sergej, NanoClaw needs to be re-linked to the client's existing WhatsApp number (`lange@mobile-physiotherapie.koeln` phone).

This involves:
1. Clearing the current WhatsApp session on the VPS
2. Restarting NanoClaw to generate a new QR code
3. Client scans the QR with their phone: WhatsApp → three dots → Linked Devices → Link a Device
4. Re-creating all registered groups (Sergej's groups disappear; new groups are created from the client's account and JIDs updated in the NanoClaw DB)

The QR scan requires the client's phone to be present — this is the one step that needs a short coordinated call (video or phone). Everything else can be done remotely by Sergej via SSH.
