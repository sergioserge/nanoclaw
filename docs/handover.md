# Handover: Dev → Prod

All steps are fully remote. No physical meeting required.

---

## Overview

| # | Task | Who | Why | After |
|---|------|-----|-----|-------|
| 1 | Fix skill — read events from both Physio Bot and primary calendar | Sergej/Bob | In prd, appointments live in the primary calendar. Without this fix Bob sees only Physio Bot events and misses the Verfügbar block — every booking attempt fails. | — |
| 2 | Back up dev credentials on VPS | Sergej | Protects dev auth tokens if prd setup goes wrong — only safe to proceed if dev state is recoverable. | 1 |
| 3 | Client creates Anthropic API key, sends to Sergej via Signal | Client | Moves Anthropic billing to the client; Sergej's dev key must not go into production. | — |
| 4 | Client does GCP setup, creates "Physio Bot" calendar, sends credentials.json | Client | Gives Bob write access under the client's Google account. The dedicated bot calendar is a safety guardrail — Bob never touches the therapist's real calendar until proven reliable. | — |
| 5 | Client sends home address to Sergej | Client | Needed to set accurate homeCoords in prd config.json. Wrong coords silently skew every routing calculation. | — |
| 6 | Upload credentials.json to VPS, run OAuth, client clicks Allow | Sergej + Client | Generates token.json under the client's Google account so Bob can read and write their calendar. Requires a brief coordinated moment for the one-click OAuth. | 4 |
| 7 | Configure prd config.json — calendarId, homeCoords, Maps API key | Sergej | Three values wrong by default; routing and calendar writes are broken until all three are correct. | 5, 6 |
| 8 | Update Anthropic token in OneCLI on VPS | Sergej | Replaces Sergej's dev API key with the client's key so Anthropic costs go to the right account. | 3 |
| 9 | Create WhatsApp group, add client and co-pilot | Sergej | Creates the production channel. Prd group is separate from dev so both can run in parallel during transition. | 2, 7, 8 |
| 10 | Register prd group JID in NanoClaw DB | Sergej | NanoClaw ignores messages from unregistered groups. Client must send at least one message first so the JID appears in the DB. | 9 (client must have sent a message) |
| 11 | End-to-end test — co-pilot sends booking, Bob responds | Both | Verifies Anthropic token, Calendar connection, and routing all work together. First real signal that prd is healthy. | 10 |
| 12 | Document organizer activation | Sergej | Separate feature — kept out of main handover to avoid scope creep on launch day. | 11, separate session |
| 13 | Final WhatsApp migration — re-link NanoClaw to client's number, client scans QR | Both | Makes the system fully independent of Sergej's phone. Deferred until stable — premature migration removes the safety net. | 12, once stable in prod |

---

## Group Folder Reference

| Group | Folder | Purpose |
|-------|--------|---------|
| Dev routing | `groups/whatsapp_physio_assistant/data/` | Sergej's calendar — untouched during handover |
| Prd routing | `groups/whatsapp_physio_assistant_prd/data/` | Client's calendar — set up during handover |
| Document organizer | `groups/document_organizer/data/` | Activated separately in Phase 3 |

---

## Phase 1 — Async Prep

Do all of this before Phase 2. Steps 1.1 and 1.2 can be done by the client independently at any time. Step 1.3 requires a 10-minute screen share after 1.1 and 1.2 are both complete.

### 1.0 Sergej: Back Up Dev Credentials

Do this first.

```bash
cd /root/nanoclaw
cp groups/whatsapp_physio_assistant/data/credentials.json \
   groups/whatsapp_physio_assistant/data/credentials.dev.json
cp groups/whatsapp_physio_assistant/data/token.json \
   groups/whatsapp_physio_assistant/data/token.dev.json
```

### 1.1 Client: Anthropic API Key

The client does this in a browser — no installation required.

- [ ] Open console.anthropic.com → log in (create account if needed)
- [ ] Add a payment method if prompted (Settings → Billing)
- [ ] Go to API Keys → **Create new secret key** → name it "Physio Assistant" → copy it
- [ ] Send the key to Sergej via Signal or WhatsApp — **not email**

### 1.2 Client: Google Cloud Setup + Bot Calendar

The client does this independently, or guided via screen share. They need to be logged into GCP as `lange@mobile-physiotherapie.koeln`.

- [ ] Create a GCP project at console.cloud.google.com
- [ ] Enable **Google Calendar API**: APIs & Services → Library → search → Enable
- [ ] Enable **Google Drive API**: APIs & Services → Library → search → Enable
  *(both now — avoids a second OAuth re-auth when the document organizer goes live)*
- [ ] Create OAuth credentials: APIs & Services → Credentials → Create Credentials → OAuth client ID → type: **Desktop App** → download as `credentials.json`
- [ ] Add `lange@mobile-physiotherapie.koeln` as test user: APIs & Services → OAuth consent screen → Test users → Add users
- [ ] Send `credentials.json` to Sergej

**Create the bot calendar (safety guardrail):**

The bot must never write to the therapist's existing calendar until it is confirmed reliable. Bob writes all new appointments to a dedicated "Physio Bot" calendar. The client sees both overlaid in Google Calendar.

- [ ] Client opens calendar.google.com → logged in as `lange@mobile-physiotherapie.koeln`
- [ ] Left sidebar → **Other calendars** → **+** → **Create new calendar**
- [ ] Name it **"Physio Bot"**, leave everything else default → **Create calendar**
- [ ] Settings → click "Physio Bot" → scroll to "Calendar ID" → send to Sergej alongside `credentials.json`

⚠ Before going live, the physio-routing skill must read events from both the primary calendar and "Physio Bot" so Bob sees the therapist's real appointments, while still writing only to "Physio Bot". This is Overview item 1 — complete before starting the handover.

### 1.3 Sergej: Upload Credentials + Run OAuth

The client must be reachable for the OAuth click (one browser action — can be guided via WhatsApp or screen share).

- [ ] Install Google API packages if not present:
  ```bash
  pip3 install --quiet google-auth google-api-python-client
  ```
- [ ] Copy oauth_flow.py from dev to prd:
  ```bash
  cp groups/whatsapp_physio_assistant/data/oauth_flow.py \
     groups/whatsapp_physio_assistant_prd/data/oauth_flow.py
  ```
- [ ] Upload client credentials to VPS:
  ```bash
  scp /path/to/credentials.json \
    root@<VPS_IP>:/root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/credentials.json
  ```
- [ ] Open SSH tunnel (keep open until OAuth completes):
  ```bash
  ssh -L 8080:localhost:8080 root@<VPS_IP> -N
  ```
- [ ] In a second terminal, run the OAuth script on the VPS:
  ```bash
  python3 /root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/oauth_flow.py
  ```
- [ ] Copy the printed URL → send to client → client opens it, logs in as `lange@mobile-physiotherapie.koeln`, clicks Allow → blank page = success
- [ ] Verify token was written:
  ```bash
  ls -la /root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/token.json
  ```
- [ ] Find the client's calendarId:
  ```bash
  python3 -c "
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
creds = Credentials.from_authorized_user_file(
    '/root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/token.json')
service = build('calendar', 'v3', credentials=creds)
for c in service.calendarList().list().execute()['items']:
    print(c['id'], '|', c['summary'])
"
  ```
- [ ] Write the calendarId and therapist's home address into prd config:
  ```bash
  python3 -c "
import json
path = '/root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/config.json'
with open(path) as f: cfg = json.load(f)
cfg['calendarId'] = 'PASTE_BOT_CALENDAR_ID_HERE'  # the 'Physio Bot' calendar, NOT the primary calendar
cfg['homeCoords'] = {'lat': PASTE_LAT, 'lng': PASTE_LNG}  # geocode the therapist's actual home address
cfg.pop('note', None)
with open(path, 'w') as f: json.dump(cfg, f, indent=2)
print('Updated:', cfg['calendarId'], cfg['homeCoords'])
"
  ```
  *(Use the **"Physio Bot" calendar ID** from step 1.2. Get lat/lng from maps.google.com. The current placeholder is Cologne city center — routing is wrong until this is set.)*
- [ ] Create the Maps API key file for the prd group:
  ```bash
  echo "GOOGLE_MAPS_API_KEY=<key from .env>" \
    > /root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/.env
  chown nanoclaw:nanoclaw /root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/.env
  chmod 640 /root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/.env
  ```
- [ ] Copy dev geocache database to prd:
  ```bash
  cp groups/whatsapp_physio_assistant/data/physio.db \
     groups/whatsapp_physio_assistant_prd/data/physio.db
  chown nanoclaw:nanoclaw groups/whatsapp_physio_assistant_prd/data/physio.db
  chmod 600 groups/whatsapp_physio_assistant_prd/data/physio.db
  ```
  *(One-time only. After handover, sync direction reverses: copy prd → dev for testing, never dev → prd.)*
- [ ] Verify Calendar API:
  ```bash
  python3 -c "
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import json
path = '/root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/'
cfg = json.load(open(path + 'config.json'))
creds = Credentials.from_authorized_user_file(path + 'token.json')
service = build('calendar', 'v3', credentials=creds)
result = service.calendarList().get(calendarId=cfg['calendarId']).execute()
print('OK:', result['summary'])
"
  ```

### 1.4 Sergej: Anthropic Token

- [ ] Update token in OneCLI on the VPS:
  ```bash
  onecli secrets delete 51bbc7e2-e72a-4977-a598-8e342318c620
  onecli secrets create --name "Anthropic" --type anthropic --value <client-token>
  ```

✓ **Phase 1 gate — verify before Phase 2:**
- Dev backup files (`credentials.dev.json`, `token.dev.json`) present in dev data dir
- `token.json` present in prd data dir
- Calendar API returns `OK: <calendar name>`
- Prd `config.json` has no `note` field, correct `calendarId` (Physio Bot), and real `homeCoords` (not `50.9333, 6.9500`)

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
- [ ] Register the prd group:
  ```bash
  sqlite3 /root/nanoclaw/store/messages.db \
    "INSERT OR REPLACE INTO registered_groups (jid, name, folder, trigger_pattern, added_at, container_config, requires_trigger, is_main)
     VALUES ('<JID>', 'Physio Assistant', 'whatsapp_physio_assistant_prd', '@Bob', datetime('now'),
       '{\"additionalMounts\":[{\"hostPath\":\"/root/nanoclaw/.claude/skills/physio-routing\",\"containerPath\":\"physio-routing\",\"readonly\":true}]}',
       0, 0);"
  ```
- [ ] Restart NanoClaw:
  ```bash
  systemctl restart nanoclaw
  ```

### 2.3 Verify End-to-End

- [ ] Client or co-pilot sends a test booking request in the group
- [ ] Bob responds with a routing suggestion — this also confirms the Anthropic token (Step 1.4) and the Calendar connection (Step 1.3)

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
cp /root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/token.json \
   /root/nanoclaw/groups/document_organizer/data/token.json
cp /root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/credentials.json \
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

**Google token expired/revoked:** Re-run Phase 1.3 via SSH tunnel — no physical presence needed.

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
