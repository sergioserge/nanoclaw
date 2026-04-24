# Handover: Dev → Prod

Three phases. Only Phase 2 requires physical presence (WhatsApp QR scan). Phases 1 and 3 are fully remote.

---

## Group Folder Reference

| Group | Folder | Purpose |
|-------|--------|---------|
| Dev routing | `groups/whatsapp_physio_assistant/data/` | Sergej's calendar — untouched during handover |
| Prd routing | `groups/whatsapp_physio_assistant_prd/data/` | Client's calendar — set up during handover |
| Document organizer | `groups/document_organizer/data/` | Activated separately in Phase 3 |

---

## Phase 1 — Async Prep (Days Before the In-Person Session)

Do these before meeting the client. If anything here isn't done, the in-person session cannot proceed.

### 1.0 Sergej: Back Up Dev Credentials

Do this first, before anything else changes on the VPS.

```bash
cd /root/nanoclaw
cp groups/whatsapp_physio_assistant/data/credentials.json \
   groups/whatsapp_physio_assistant/data/credentials.dev.json
cp groups/whatsapp_physio_assistant/data/token.json \
   groups/whatsapp_physio_assistant/data/token.dev.json
```

### 1.1 Client: Claude Subscription + Token

- [ ] Client has an active Claude.ai subscription
- [ ] Client installs Claude Code CLI from claude.ai/code
- [ ] Client runs `claude setup-token` on their machine → sends the token to Sergej

### 1.2 Client: Google Cloud Setup

The client does this independently, or guided via screen share. They need to be logged into GCP as `lange@mobile-physiotherapie.koeln`.

- [ ] Client creates a GCP project at console.cloud.google.com
- [ ] Enable **Google Calendar API**: APIs & Services → Library → search → Enable
- [ ] Enable **Google Drive API**: APIs & Services → Library → search → Enable
  *(both now — avoids a second OAuth re-auth when the document organizer goes live)*
- [ ] Create OAuth credentials: APIs & Services → Credentials → Create Credentials → OAuth client ID → type: **Desktop App** → download as `credentials.json`
- [ ] Add `lange@mobile-physiotherapie.koeln` as test user: APIs & Services → OAuth consent screen → Test users → Add users
- [ ] Client sends `credentials.json` to Sergej

### 1.3 Sergej: Upload Credentials + Run OAuth

The client must be available to approve the Google login (2FA) — this can be done via screen share.

- [ ] Install Google API packages if not present (needed by oauth_flow.py):
  ```bash
  pip3 install --quiet google-auth google-api-python-client
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
- [ ] Copy the printed URL → open in browser → log in as `lange@mobile-physiotherapie.koeln` → Allow → blank page = success
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
cfg['calendarId'] = 'PASTE_CALENDAR_ID_HERE'
cfg['homeCoords'] = {'lat': PASTE_LAT, 'lng': PASTE_LNG}  # geocode the therapist's actual home address
cfg.pop('note', None)
with open(path, 'w') as f: json.dump(cfg, f, indent=2)
print('Updated:', cfg['calendarId'], cfg['homeCoords'])
"
  ```
  *(Get the lat/lng from maps.google.com or geocode the address. The current placeholder is Cologne city center — routing is wrong until this is set.)*
- [ ] Create the Maps API key file for the prd group (routing runs in degraded mode without this):
  ```bash
  echo "GOOGLE_MAPS_API_KEY=<key from .env>" \
    > /root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/.env
  chown nanoclaw:nanoclaw /root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/.env
  chmod 640 /root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/.env
  ```
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

✓ **Phase 1 gate — verify before the in-person session:**
- Dev backup files (`credentials.dev.json`, `token.dev.json`) present in dev data dir
- `token.json` present in prd data dir
- Calendar API returns `OK: <calendar name>`
- Prd `config.json` has no `note` field, correct `calendarId`, and real `homeCoords` (not `50.9333, 6.9500`)

---

## Phase 2 — In-Person Session (WhatsApp)

⚠ **This is the only part that requires physical presence.** The client's phone must be present. All of Phase 1 must be complete before starting this.

### 2.1 Link WhatsApp to Client's Phone

- [ ] Clear existing WhatsApp session and restart NanoClaw:
  ```bash
  rm -rf /root/nanoclaw/store/auth/*
  systemctl restart nanoclaw
  ```
- [ ] Watch logs for the QR code:
  ```bash
  journalctl -u nanoclaw -f
  ```
- [ ] Client scans QR: WhatsApp → three dots → Linked Devices → Link a Device
- [ ] Confirm connection — NanoClaw logs should stop printing the QR and show "WhatsApp connected"

### 2.2 Register the Prd Group

After linking, the client's groups sync into the DB. Have the client send any message in their practice group, then:

- [ ] Find the group JID:
  ```bash
  sqlite3 /root/nanoclaw/store/messages.db \
    "SELECT jid, name FROM chats WHERE jid LIKE '%@g.us' ORDER BY last_message_time DESC LIMIT 5;"
  ```
- [ ] Register the prd group with that JID:
  ```bash
  sqlite3 /root/nanoclaw/store/messages.db \
    "INSERT OR REPLACE INTO registered_groups (jid, name, folder, trigger_pattern, added_at, requires_trigger)
     VALUES ('<JID>', 'Physio Assistant', 'whatsapp_physio_assistant_prd', '@Bob', datetime('now'), 0);"
  ```
- [ ] Restart NanoClaw to pick up the new group:
  ```bash
  systemctl restart nanoclaw
  ```

### 2.3 Verify End-to-End

- [ ] Client sends a test booking request in the group
- [ ] Bob responds with a routing suggestion — this also confirms the Anthropic token (Step 1.4) and the Calendar connection (Step 1.3)

✓ **Phase 2 gate:** Bob responds correctly to a booking request from the client's WhatsApp group.

---

## Phase 3 — Document Organizer (Separate Session, When Feature Goes Live)

This is a separate activation, not part of the main handover. Can be done remotely. Requires Phase 1 and Phase 2 to be complete.

### 3.1 Register the Document Organizer WhatsApp Group

The document organizer uses a separate WhatsApp group (e.g. the client's "My Office" or equivalent). After the Phase 2 phone swap, the old JID in the DB belongs to Sergej's WhatsApp and is no longer valid. Re-register it with the correct JID from the client's phone.

- [ ] Have the client send a message in their document organizer group
- [ ] Find the JID:
  ```bash
  sqlite3 /root/nanoclaw/store/messages.db \
    "SELECT jid, name FROM chats WHERE jid LIKE '%@g.us' ORDER BY last_message_time DESC LIMIT 5;"
  ```
- [ ] Update the registered group:
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

### 3.2 Create Drive Folder Structure

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

**WhatsApp session expired or client gets a new phone:** Repeat Phase 2.1–2.2. The QR scan requires the phone — schedule a short call.
