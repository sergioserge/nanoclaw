# Handover: Dev → Prod Credential Swap

Sergej keeps SSH access and continues development from any location. After the swap, the client's credentials are live on the VPS for the production group. The dev group (`whatsapp_physio_assistant`) stays on Sergej's calendar for testing.

**What requires physical presence:** Only Step 4 (WhatsApp QR scan). Every other step can be done remotely via SSH.

**Order:** Backup (Step 1) → Anthropic (Step 2) → Google (Step 3) → WhatsApp in person (Step 4) → Post-handover verification (Step 5) → Document Organizer Drive setup (Step 6, if feature is active).

---

## Group Folder Reference

| Group | Folder | Purpose |
|-------|--------|---------|
| Dev routing | `groups/whatsapp_physio_assistant/data/` | Sergej's calendar — stays as-is |
| Prd routing | `groups/whatsapp_physio_assistant_prd/data/` | Client's calendar — set up during handover |
| Document organizer | `groups/document_organizer/data/` | Shared, Drive scope on prd token |

Each group carries its own `credentials.json` and `token.json` independently — no credential file-swapping needed.

---

## Requirements — Collect Before Starting

- **Claude subscription** — client needs an active Claude.ai subscription. If the client cancels, Bob stops working immediately with no warning.
- **Claude Code CLI** — client installs from claude.ai/code, then runs `claude setup-token` on their machine and sends the output token to Sergej.
- **Google account** — `lange@mobile-physiotherapie.koeln` or a dedicated Gmail. Sergej needs the client available in real time to approve the 2FA prompt during OAuth (can be done via screen share — no physical presence needed).
- **WhatsApp** — physical access to the therapist's phone for the QR scan (one-time only). After this, Sergej uses the SQLite DB directly for dev testing — no need to re-link his phone.

## Questions to Ask Client Before Building Drive Feature

- **What file types do you receive?** (PDF invoices, DOCX letters, XLSX reports — list the common ones)
- **How is your Drive currently organized?** Any existing folder structure, or starting fresh?
- **Who sends you documents?** (insurance companies, patients, tax office — helps define initial folders)
- **Do you scan paper documents?** If yes, what app? Scanned PDFs (image-only) cannot be read without OCR.

---

## Step 1 — Dev Credentials Backup

Run from `/root/nanoclaw/`. Do this before anything else.

```bash
cd /root/nanoclaw
cp groups/whatsapp_physio_assistant/data/credentials.json \
   groups/whatsapp_physio_assistant/data/credentials.dev.json
cp groups/whatsapp_physio_assistant/data/token.json \
   groups/whatsapp_physio_assistant/data/token.dev.json
```

✓ **Gate:** `credentials.dev.json` and `token.dev.json` present in dev data dir.

---

## Step 2 — Anthropic (Claude Subscription)

Billed via Claude.ai subscription — not an API key. No usage in Anthropic console — this is normal.

- [ ] Client installs Claude Code CLI from claude.ai/code
- [ ] Client runs `claude setup-token` on their own machine → sends the token to Sergej
- [ ] Update token in OneCLI on the VPS:
  ```bash
  onecli secrets delete 51bbc7e2-e72a-4977-a598-8e342318c620
  onecli secrets create --name "Anthropic" --type anthropic --value <client-token>
  ```
- [ ] Verification deferred to Step 4 (first WhatsApp response confirms Anthropic token works)

---

## Step 3 — Google Cloud + Calendar (remote, via screen share or async)

- [ ] Client creates their own GCP project at console.cloud.google.com
- [ ] Enable Google Calendar API: APIs & Services → Library → "Google Calendar API" → Enable
- [ ] Enable Google Drive API: APIs & Services → Library → "Google Drive API" → Enable  
  *(needed now so both scopes are in the same OAuth flow — avoids a second re-auth later)*
- [ ] Create OAuth credentials: APIs & Services → Credentials → Create Credentials → OAuth client ID → type: **Desktop App** → download as `credentials.json`
- [ ] Add `lange@mobile-physiotherapie.koeln` as test user: APIs & Services → OAuth consent screen → Test users → Add users
- [ ] Upload credentials to VPS:
  ```bash
  # Run on your laptop:
  scp /path/to/credentials.json \
    root@<VPS_IP>:/root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/credentials.json
  ```
- [ ] Clear any existing prd token:
  ```bash
  rm -f /root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/token.json
  ```
- [ ] Open SSH tunnel from your laptop (keep open until blank page appears in browser):
  ```bash
  ssh -L 8080:localhost:8080 root@<VPS_IP> -N
  ```
- [ ] In a second terminal, run the OAuth script on the VPS:
  ```bash
  python3 /root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/oauth_flow.py
  ```
- [ ] Copy the printed URL → open in browser → log in as `lange@mobile-physiotherapie.koeln` → click Allow → blank page = success
- [ ] Verify token was written:
  ```bash
  ls -la /root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/token.json
  ```
- [ ] Install Google API packages if not present:
  ```bash
  pip3 install --quiet google-auth google-api-python-client
  ```
- [ ] Find the calendarId:
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
- [ ] Update `calendarId` in the prd config (replace the placeholder, keep the rest):
  ```bash
  python3 -c "
import json
path = '/root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/config.json'
with open(path) as f: cfg = json.load(f)
cfg['calendarId'] = 'PASTE_CALENDAR_ID_HERE'
cfg.pop('note', None)
with open(path, 'w') as f: json.dump(cfg, f, indent=2)
print('Updated:', cfg['calendarId'])
"
  ```
- [ ] Verify Calendar API works with the new calendarId:
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

✓ **Gate:** Calendar API returns `OK: <calendar name>` with no errors.

---

## Step 4 — WhatsApp ⚠ Requires physical access to client's phone

This is the only step that cannot be done remotely. Schedule this in person or via video call where the client can scan a QR code shown on screen.

- [ ] Clear existing WhatsApp auth state and restart NanoClaw:
  ```bash
  rm -rf /root/nanoclaw/store/auth/*
  systemctl restart nanoclaw
  ```
- [ ] Watch logs for QR code:
  ```bash
  journalctl -u nanoclaw -f
  ```
- [ ] Client scans QR with their phone: WhatsApp → three dots → Linked Devices → Link a Device
- [ ] Register the prd group (if not already registered) via Bob from the client's WhatsApp group, or directly:
  ```bash
  sqlite3 /root/nanoclaw/store/messages.db \
    "SELECT jid, name, folder FROM registered_groups;"
  # Confirm whatsapp_physio_assistant_prd is registered and has the right JID
  ```
- [ ] Send a test message to Bob from the client's group and confirm response — this also verifies the Anthropic token from Step 2

✓ **Gate:** Bob responds to a test message from the client's WhatsApp group.

---

## Step 5 — Post-Handover Verification

```bash
# Prd config is clean (no "note" field, correct calendarId)
cat /root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/config.json

# Token present for prd
ls -la /root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/token.json

# Dev group still intact
cat /root/nanoclaw/groups/whatsapp_physio_assistant/data/config.json
```

✓ **Gate:** Prd config has no `note` field. Dev config still points to Sergej's calendar.

---

## Step 6 — Document Organizer: Prd Drive Setup (when feature goes live)

Run only after the token from Step 3 is in place (includes Drive scope). Creates the Drive folder structure and writes `config.json` for the prd document organizer group.

- [ ] Copy the prd token to the document organizer group:
  ```bash
  cp /root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/token.json \
     /root/nanoclaw/groups/document_organizer/data/token.json
  cp /root/nanoclaw/groups/whatsapp_physio_assistant_prd/data/credentials.json \
     /root/nanoclaw/groups/document_organizer/data/credentials.json
  ```
- [ ] Run `setup_drive` to create the folder structure in the client's Drive:
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
- [ ] Confirm config.json was written with rootFolderId:
  ```bash
  cat /root/nanoclaw/groups/document_organizer/data/config.json
  ```
- [ ] Confirm folders are visible in the client's Google Drive

⚠ Run `setup_drive` only once. Re-running creates a second "Document Organizer" tree in Drive.

✓ **Gate:** `config.json` has `rootFolderId`. Folders visible in client's Drive.

---

## Future Credential Refresh (Remote — No In-Person Needed)

If the Google OAuth token expires or is revoked, re-run Step 3 via SSH tunnel and screen share — no physical presence required.

If WhatsApp needs to be re-linked (session expired or client gets a new phone), Step 4 must be repeated — QR scan requires the phone. Schedule a short video call for this.
