# Handover: Dev → Prod Credential Swap

Sergej keeps SSH access and continues development from any location. This is a credential swap only — no infrastructure changes. After the swap, prod credentials are live on the VPS. Sergej switches to dev credentials locally for testing when needed.

**Order:** Backup first (Step 1). Anthropic (Step 2). Google in one go (Step 3). WhatsApp last (Step 4). Create prod backup (Step 5).

---

## Requirements — Collect Before Starting

- **Claude subscription** — client needs an active Claude.ai subscription (same plan as dev). If the client cancels, Bob stops working immediately with no warning.
- **Claude Code CLI** — client installs from claude.ai/code, then runs `claude setup-token` and sends the output token to Sergej.
- **Google account** — clean Gmail for the client, or Google Workspace (recommended: professional email like `christian@mobile-physiotherapie.koeln` + passkey login). Sergej needs either the password + 2FA access, or the client must be available in real time to provide the 2FA code during OAuth setup.
- **WhatsApp** — physical access to the therapist's phone for the QR scan (one-time). After swap, Sergej accesses WhatsApp data via the SQLite DB directly for dev testing — no need to relink his phone.

## Questions to Ask Client Before Building Drive Feature

- **What file types do you receive?** (PDF invoices, DOCX letters, XLSX reports, CSV exports — list the common ones so we build the right parsers)
- **How is your Drive currently organized?** Any existing folder structure, or starting fresh?
- **Who sends you documents?** (insurance companies, patients, tax office — helps define categories)
- **Do you scan paper documents?** If yes, what app? Scanned PDFs (image-only) cannot be read without OCR — important to know upfront.

---

## Step 1 — Dev Credentials Backup

Run from `/root/nanoclaw/`. Do this before anything else.

```bash
cd /root/nanoclaw
cp groups/physio-copilot/data/credentials.json groups/physio-copilot/data/credentials.dev.json
cp groups/physio-copilot/data/token.json groups/physio-copilot/data/token.dev.json
rm -rf store/auth.dev && cp -r store/auth store/auth.dev
```

---

## Step 2 — Anthropic (Claude Subscription)

Billed via Claude.ai subscription — not an API key. No usage appears in Anthropic console, this is normal.

- [ ] Client installs Claude Code CLI from claude.ai/code
- [ ] Client runs `claude setup-token` on their own machine → sends the token to Sergej
- [ ] Update token in OneCLI on the VPS:
  ```bash
  onecli secrets delete 51bbc7e2-e72a-4977-a598-8e342318c620
  onecli secrets create --name "Anthropic" --type anthropic --value <client-token>
  ```
- [ ] Verification deferred to Step 4

---

## Step 3 — Google Cloud + Calendar

- [ ] Client creates their own GCP project at console.cloud.google.com (Sergej may need to guide this)
- [ ] Enable Google Calendar API: APIs & Services → Library → search "Google Calendar API" → Enable
- [ ] Create OAuth 2.0 credentials: APIs & Services → Credentials → Create Credentials → OAuth client ID → type: **Desktop App** → download as `credentials.json`
- [ ] Place on VPS:
  ```bash
  # Upload from your laptop:
  scp /path/to/credentials.json root@<VPS_IP>:/root/nanoclaw/groups/physio-copilot/data/credentials.json
  ```
- [ ] Add `lange@mobile-physiotherapie.koeln` as test user: APIs & Services → OAuth consent screen → Test users → Add users
- [ ] Clear existing token:
  ```bash
  rm /root/nanoclaw/groups/physio-copilot/data/token.json
  ```
- [ ] Open SSH tunnel from your laptop (keep open until blank page appears in browser):
  ```bash
  ssh -L 8080:localhost:8080 root@<VPS_IP> -N
  ```
- [ ] In a second terminal, run the OAuth script on the VPS:
  ```bash
  cd /root/nanoclaw
  python3 groups/physio-copilot/data/oauth_flow.py
  ```
- [ ] Copy the printed URL → open in your browser → log in as `lange@mobile-physiotherapie.koeln` → click Allow → blank page = success
- [ ] Verify token was written:
  ```bash
  ls -la /root/nanoclaw/groups/physio-copilot/data/token.json
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
creds = Credentials.from_authorized_user_file('/root/nanoclaw/groups/physio-copilot/data/token.json')
service = build('calendar', 'v3', credentials=creds)
for c in service.calendarList().list().execute()['items']:
    print(c['id'], '|', c['summary'])
"
  ```
- [ ] Update `calendarId` in config.json with the ID of `Therapeut Christian - Termine`:
  ```bash
  # Open in editor:
  nano /root/nanoclaw/groups/physio-copilot/data/config.json
  ```
- [ ] Verify Calendar API:
  ```bash
  python3 -c "
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import json
config = json.load(open('/root/nanoclaw/groups/physio-copilot/data/config.json'))
creds = Credentials.from_authorized_user_file('/root/nanoclaw/groups/physio-copilot/data/token.json')
service = build('calendar', 'v3', credentials=creds)
result = service.calendarList().get(calendarId=config['calendarId']).execute()
print('OK:', result['summary'])
"
  ```

### Adding Google Drive Scope (document organizer feature)

When the `whatsapp_document_organizer` feature is ready to activate, the token must be regenerated with Drive scope added. A token cannot be upgraded in place — delete it and re-run the OAuth flow.

- [ ] Enable Google Drive API in GCP: APIs & Services → Library → search "Google Drive API" → Enable
- [ ] Delete the existing token to force re-auth:
  ```bash
  rm /root/nanoclaw/groups/physio-copilot/data/token.json
  ```
- [ ] Re-run the OAuth flow (same SSH tunnel process as above) — the consent screen will now request both Calendar and Drive permissions
- [ ] Verify Drive access:
  ```bash
  python3 -c "
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
creds = Credentials.from_authorized_user_file('/root/nanoclaw/groups/physio-copilot/data/token.json')
service = build('drive', 'v3', credentials=creds)
results = service.files().list(pageSize=5, fields='files(id,name)').execute()
for f in results.get('files', []): print(f['id'], '|', f['name'])
"
  ```
- [ ] Copy the updated token to the document organizer data folder:
  ```bash
  cp /root/nanoclaw/groups/physio-copilot/data/token.json \
     /root/nanoclaw/groups/whatsapp_document_organizer/data/token.json
  cp /root/nanoclaw/groups/physio-copilot/data/credentials.json \
     /root/nanoclaw/groups/whatsapp_document_organizer/data/credentials.json
  ```

---

## Step 4 — WhatsApp

- [ ] Clear existing WhatsApp auth state and restart NanoClaw:
  ```bash
  rm -rf /root/nanoclaw/store/auth/*
  systemctl --user restart nanoclaw
  ```
- [ ] Watch logs for QR code:
  ```bash
  journalctl --user -u nanoclaw -f
  ```
- [ ] Scan QR with client's phone: WhatsApp → three dots → Linked Devices → Link a Device
- [ ] Send a test message to Bob and confirm response — this also verifies the Anthropic token from Step 2

---

## Step 5 — Prod Credentials Backup

Now that prod credentials are live, back them up so you can restore them after dev testing.

```bash
cd /root/nanoclaw
cp groups/physio-copilot/data/credentials.json groups/physio-copilot/data/credentials.prod.json
cp groups/physio-copilot/data/token.json groups/physio-copilot/data/token.prod.json
rm -rf store/auth.prod && cp -r store/auth store/auth.prod
```

---

## Switching Between Dev and Prod

All commands run from `/root/nanoclaw/`. NanoClaw must be restarted after any switch.
Switching WhatsApp auth disconnects whichever phone was linked — Sergej uses the SQLite DB directly for dev testing, no phone needed.

**Switch to dev:**
```bash
cd /root/nanoclaw
cp groups/physio-copilot/data/credentials.dev.json groups/physio-copilot/data/credentials.json
cp groups/physio-copilot/data/token.dev.json groups/physio-copilot/data/token.json
rm -rf store/auth && cp -r store/auth.dev store/auth
systemctl --user restart nanoclaw
```

**Switch back to prod:**
```bash
cd /root/nanoclaw
cp groups/physio-copilot/data/credentials.prod.json groups/physio-copilot/data/credentials.json
cp groups/physio-copilot/data/token.prod.json groups/physio-copilot/data/token.json
rm -rf store/auth && cp -r store/auth.prod store/auth
systemctl --user restart nanoclaw
```
