# Handover: Dev → Prod

> **Status (2026-04-28):** Calendar OAuth and dev credential backup complete. Remaining work: `config.json` schema migration + `physio-routing/SKILL.md` update, claude.ai CLI re-auth, prd WhatsApp group setup. One short call needed for claude.ai re-auth (section 1.4) — everything else is async or local.

---

## Calendar Architecture (Locked 2026-04-28)

**OAuth identity:** `mobilephysiotherapie.pilot@gmail.com` — Bob authenticates as this account. Owner of its own primary calendar.

**Read/write split:**

| Role | Calendar | ID | Bob's permission |
|---|---|---|---|
| Write target | `mobilephysiotherapie.pilot@gmail.com` (pilot primary) | `mobilephysiotherapie.pilot@gmail.com` | owner |
| Read source #1 | (same as above — sees its own writes) | `mobilephysiotherapie.pilot@gmail.com` | owner |
| Read source #2 | `Therapeut Christian – Termine` | `f5203265db2b1b530d9d835a17cf1ec73a79f677c193a70b2d9d4faa9e17bd0e@group.calendar.google.com` | reader (shared) |

**Bob never writes to `Therapeut Christian – Termine`.** That calendar is human-only — Christian's source of truth.

**Cross-calendar visibility (handled outside Bob, not via Calendar API):**
- *Christian sees Bob's bookings:* he subscribes his own calendar UI to `mobilephysiotherapie.pilot@gmail.com` (overlay view in his client). Sergej coordinates this with Christian out of band.
- *Bob sees Christian's existing appointments and Verfügbar blocks:* via the existing read-only share of `Therapeut Christian – Termine` to pilot. Already in place.

**Why split read/write:** Bob operates in a sandbox calendar. Mutations are visually distinguishable from human entries (different calendar source, different color in Christian's UI). Christian can revoke pilot's read share at any time without breaking his own data.

**Calendars deliberately excluded from `readCalendarIds`** (currently visible to pilot via existing shares, but ignored by Bob): `Fahrzeiten & Pausen`, `Urlaub & Abwesenheiten`, `Rückrufe & Anfragen`, `Intern / Verwaltung`, `lange@mobile-physiotherapie.koeln`. Sergej/Christian will revoke these shares from the practice side. Revocation is independent of Bob's behavior — Bob's `readCalendarIds` is the source of truth for what gets queried.

**Note on terminology:** Earlier drafts of this doc referenced an `info@mobile-physiotherapie.koeln` calendar. That calendar does not exist (or was never shared with pilot). The relevant calendar is `Therapeut Christian – Termine`.

---

## Current Status (2026-04-28)

**Done:**
- ✅ Dev credential backup — `credentials.dev.json`, `token.dev.json` in `groups/whatsapp_physio_assistant/data/` (Apr 27)
- ✅ Pilot OAuth complete — `token.json` authenticated as `mobilephysiotherapie.pilot@gmail.com` (verified Apr 28 via live `calendarList()` call returning 8 pilot calendars with primary/owner role)
- ✅ `Therapeut Christian – Termine` shared read-only to pilot
- ✅ Home address known: Senefelderstraße 44, Köln (`lat: 50.9532868, lng: 6.9156511`)
- ✅ Pilot account password received async via Signal (used for OAuth, not stored anywhere by Bob)
- ✅ GCP test user added (implicit — OAuth wouldn't have completed otherwise)

**Pending (rough order):**
- ⬜ Migrate `config.json` to `writeCalendarId` / `readCalendarIds` schema (dev + prd)
- ⬜ Update `physio-routing/SKILL.md` for new schema (3 edits)
- ⬜ Smoke-test routing in dev → smoke-test in prd
- ⬜ Christian subscribes his calendar UI to `pilot@` (out-of-band, Sergej coordinates)
- ⬜ Re-auth claude.ai CLI to client's account (section 1.4) — needs client live for password entry
- ⬜ Phase 2: create prd WhatsApp group + register JID in NanoClaw DB
- ⬜ Phase 3: document organizer activation (separate session)
- ⬜ (Later) Final WhatsApp account migration to client's number

---

## Group Folder Reference

| Group | Folder | Purpose |
|---|---|---|
| Dev routing | `groups/whatsapp_physio_assistant_dev/data/` | Sergej's own calendar — runs in parallel with prd, untouched during handover |
| Prd routing | `groups/whatsapp_physio_assistant/data/` | Pilot account — handover target |
| Document organizer | `groups/document_organizer/data/` | Activated separately in Phase 3 |

---

## Phase 1 — Calendar Hookup

### 1.1 ✅ Dev Backup (Done Apr 27)

For the record:
```bash
cp /root/nanoclaw/groups/whatsapp_physio_assistant/data/credentials.json \
   /root/nanoclaw/groups/whatsapp_physio_assistant/data/credentials.dev.json
cp /root/nanoclaw/groups/whatsapp_physio_assistant/data/token.json \
   /root/nanoclaw/groups/whatsapp_physio_assistant/data/token.dev.json
```

### 1.2 ✅ Pilot OAuth (Done Apr 27)

Verified by listing calendars on `token.json` — returns 8 pilot calendars with `mobilephysiotherapie.pilot@gmail.com` as PRIMARY/owner.

If ever needed to re-run (e.g. token revoked):
```bash
# On Sergej's laptop — open SSH tunnel
ssh -L 8080:localhost:8080 root@178.105.3.245 -N

# On VPS — second terminal
python3 /root/nanoclaw/groups/whatsapp_physio_assistant/data/oauth_flow.py
```
Copy the printed URL **as a single line** (it must end with `&state=XXXX` — line-wrap truncation breaks the scope) and open it in Sergej's own browser (only Sergej's tunnel resolves `localhost:8080`). Sign in as `mobilephysiotherapie.pilot@gmail.com` using the password received via Signal. Click Allow. Blank page = success. Verify:
```bash
ls -la /root/nanoclaw/groups/whatsapp_physio_assistant/data/token.json
```

### 1.3 ⬜ Migrate `config.json` and `SKILL.md` to Split Read/Write Schema

**Why:** Current schema has a single `calendarId` for both reading and writing. New architecture needs `writeCalendarId` (string) + `readCalendarIds` (array). The skill code currently reads from `calendarId` plus `'primary'` (a hidden assumption that worked in dev but is wrong for prd). The new schema makes both sources explicit.

**`/root/nanoclaw/groups/whatsapp_physio_assistant/data/config.json` (prd):**
```json
{
  "writeCalendarId": "mobilephysiotherapie.pilot@gmail.com",
  "readCalendarIds": [
    "mobilephysiotherapie.pilot@gmail.com",
    "f5203265db2b1b530d9d835a17cf1ec73a79f677c193a70b2d9d4faa9e17bd0e@group.calendar.google.com"
  ],
  "homeCoords": { "lat": 50.9532868, "lng": 6.9156511 },
  "timezone": "Europe/Berlin"
}
```

**`/root/nanoclaw/groups/whatsapp_physio_assistant_dev/data/config.json` (dev — keeps using Sergej's calendar):**
```json
{
  "writeCalendarId": "travelnomad1234@gmail.com",
  "readCalendarIds": [ "travelnomad1234@gmail.com" ],
  "homeCoords": { "lat": 50.9333, "lng": 6.9500 },
  "timezone": "Europe/Berlin"
}
```

**`/root/nanoclaw/.claude/skills/physio-routing/SKILL.md` — 3 edits:**

| Step | Current | Becomes |
|---|---|---|
| Step 2 (Load config, ~line 44) | `calendar_id = config['calendarId']` | `write_calendar_id = config['writeCalendarId']`<br>`read_calendar_ids = config['readCalendarIds']` |
| Step 3 (Fetch Calendar, ~lines 79–89) | Hardcoded dual read of `calendar_id` + `'primary'` with dedup; comment about dev/prd assumptions | Loop over `read_calendar_ids`, dedup by event id; obsolete comment removed |
| Step 7 (Insert event, ~line 199) | `calendarId=config['calendarId']` | `calendarId=config['writeCalendarId']` |

**Order of execution:**
1. Edit dev `config.json` (schema-only change — still routes to `travelnomad1234@gmail.com`)
2. Edit `SKILL.md` (3 spots)
3. Smoke-test dev: send a fake booking request in Physio Assistant Dev → verify slot proposal still works
4. Edit prd `config.json` with the new pilot values
5. Smoke-test prd (after Phase 2 group registration): send a real booking request → verify (a) slots reflect Christian's existing appointments from `Therapeut Christian – Termine`, (b) confirmed event lands on `mobilephysiotherapie.pilot@gmail.com`
6. Commit all changes in `nanoclaw-physio` private repo with descriptive message; update `TODO.md`

### 1.4 ⬜ Re-auth Claude Code CLI to Client's Account

The Claude Code CLI on the VPS currently runs under Sergej's claude.ai account. Switch it to the client's. Bob's inference (and any future `claude` CLI use on this VPS) runs under whichever account is active.

**Prerequisite:** Client has Pro or Max subscription on claude.ai. (No Anthropic API key — OneCLI uses the subscription session.)

This is the only step that needs the client live — they enter their own claude.ai password. Schedule a short call or screen share.

```bash
# On VPS — log out current session
claude auth logout

# Start re-auth (no SSH tunnel needed — opens in any browser)
claude
# → prints a URL. Send to client.

# Verify
claude auth status
# → shows client's email + subscriptionType
```

Session persists indefinitely — no expiry unless explicitly logged out.

✅ **Phase 1 gate — verify before Phase 2:**
- `cat` of both prd and dev `config.json` shows new schema (no `calendarId`, no `note` field)
- Live API call with prd `token.json` returns events from both `readCalendarIds` (dedup works)
- A test event written via prd token shows up on `mobilephysiotherapie.pilot@gmail.com`
- `claude auth status` shows the client's email and `pro` or `max`

---

## Phase 2 — WhatsApp Prd Group

NanoClaw runs on Sergej's WhatsApp number. No QR scan by the client is needed; Sergej creates the group and adds the client and co-pilot.

### 2.1 Create the Prd WhatsApp Group

On Sergej's phone:
- [ ] WhatsApp → New Group
- [ ] Add the client (`lange@mobile-physiotherapie.koeln` phone) and the co-pilot
- [ ] Name the group **"Physio Assistant"** (can be renamed later)
- [ ] Ask the client to send any message in the group so it syncs into NanoClaw

### 2.2 Register the Prd Group in NanoClaw DB

```bash
# Find the group JID (newest @g.us chats)
sqlite3 /root/nanoclaw/store/messages.db \
  "SELECT jid, name FROM chats WHERE jid LIKE '%@g.us' ORDER BY last_message_time DESC LIMIT 5;"

# Register the prd group (replaces any existing row for the same folder)
sqlite3 /root/nanoclaw/store/messages.db \
  "INSERT OR REPLACE INTO registered_groups (jid, name, folder, trigger_pattern, added_at, container_config, requires_trigger, is_main)
   VALUES ('<NEW_JID>', 'Physio Assistant', 'whatsapp_physio_assistant', '@Bob', datetime('now'),
     '{\"additionalMounts\":[{\"hostPath\":\"/root/nanoclaw/.claude/skills/physio-routing\",\"containerPath\":\"physio-routing\",\"readonly\":true}]}',
     0, 0);"

# Remove any stale entry for the same folder under a different JID
sqlite3 /root/nanoclaw/store/messages.db \
  "DELETE FROM registered_groups WHERE folder='whatsapp_physio_assistant' AND jid != '<NEW_JID>';"

systemctl restart nanoclaw
```

### 2.3 Verify End-to-End

- [ ] Client or co-pilot sends a test booking request in the group
- [ ] Bob responds with a routing suggestion → confirms claude.ai subscription, Calendar connection, and skill code all wired correctly

✅ **Phase 2 gate:** Bob responds correctly to a booking request in the prd group, and confirmed slot creates an event on `mobilephysiotherapie.pilot@gmail.com`.

---

## Phase 3 — Document Organizer (Separate Session)

Done remotely. Requires Phase 1 and Phase 2 complete.

### 3.1 Register the Document Organizer WhatsApp Group

- [ ] Sergej creates a second WhatsApp group (or reuses existing) and adds the client
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

### 3.2 Copy Pilot Token to Document Organizer Group

The doc organizer reads Drive under the same pilot OAuth identity. Copy the existing token rather than re-running OAuth.

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
- [ ] Confirm "Document Organizer" folder and subfolders visible in client's Google Drive

✅ **Phase 3 gate:** `config.json` has `rootFolderId`. Folders visible in client's Drive. Test sort trigger in WhatsApp returns a response.

---

## Future Maintenance

- **Google token expired/revoked:** Re-run section 1.2 (Pilot OAuth) — `oauth_flow.py` from `groups/whatsapp_physio_assistant/data/` via SSH tunnel. Sergej does this alone in his own browser using the pilot password from Signal.
- **Claude Code session expired:** Re-run section 1.4 (claude.ai re-auth). Requires the client live to enter their password.
- **WhatsApp session expired:** Sergej re-scans the QR on his own phone — no client involvement needed.
- **Christian revokes the `Therapeut Christian – Termine` share:** Bob silently loses visibility into existing appointments and starts double-booking. Detect via periodic `calendarList()` check; if reader role on that ID disappears, halt routing and alert Sergej.

---

## Future: Final WhatsApp Account Migration

> ⚠ **Not part of this handover — to be done later, once the system is stable in production.**

The current setup runs on Sergej's WhatsApp number. For the system to be fully independent of Sergej, NanoClaw needs to be re-linked to the client's existing WhatsApp number (`lange@mobile-physiotherapie.koeln` phone).

Steps:
1. Clear the current WhatsApp session on the VPS
2. Restart NanoClaw to generate a new QR code
3. Client scans the QR with their phone: WhatsApp → three dots → Linked Devices → Link a Device
4. Re-create all registered groups (Sergej's groups disappear; new groups created from the client's account; JIDs updated in NanoClaw DB)

The QR scan requires the client's phone to be present — this is the one step that needs a short coordinated call (video or phone). Everything else can be done remotely by Sergej via SSH.
