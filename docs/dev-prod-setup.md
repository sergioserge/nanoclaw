# Dev / Prod Setup

## Overview

Dev and prod run as two parallel NanoClaw groups on the same VPS. No credential swapping, no restarts, no downtime when switching.

- **Dev** = Sergej's WhatsApp group → Sergej's calendar → `whatsapp_physio_assistant/`
- **Prod** = client co-pilot's WhatsApp group → client's calendar → `whatsapp_physio_assistant_prd/`

The current active setup (`whatsapp_physio_assistant`) is dev. Prod is created at handover.

---

## Current State (Dev — fully operational)

```
groups/
└── whatsapp_physio_assistant/       ← dev group (Sergej's WhatsApp)
    ├── CLAUDE.md
    └── data/
        ├── credentials.json         ← Sergej's GCP OAuth app
        ├── token.json               ← Sergej's Google OAuth token
        ├── config.json              ← Sergej's calendarId, homeCoords, timezone
        ├── physio.db
        └── .env                     ← GOOGLE_MAPS_API_KEY
```

---

## Target State (Dev + Prod)

```
groups/
├── whatsapp_physio_assistant/       ← dev group (unchanged)
│   ├── CLAUDE.md
│   └── data/
│       ├── credentials.json         ← Sergej's GCP OAuth app
│       ├── token.json               ← Sergej's Google OAuth token
│       ├── config.json              ← Sergej's calendarId, homeCoords, timezone
│       ├── physio.db
│       └── .env
│
└── whatsapp_physio_assistant_prd/   ← prod group (created at handover)
    ├── CLAUDE.md
    └── data/
        ├── credentials.json         ← client's GCP OAuth app
        ├── token.json               ← client's Google OAuth token
        ├── config.json              ← client's calendarId, homeCoords, timezone
        ├── physio.db
        └── .env                     ← same GOOGLE_MAPS_API_KEY (shared key, IP-restricted)
```

**What differs between dev and prod:** `credentials.json`, `token.json`, `config.json` (calendarId + homeCoords)

**What is shared:** routing skill — `SKILL.md` + `routing.py` at `.claude/skills/physio-routing/`, mounted into every container via `containerConfig.additionalMounts`.

---

## How It Works

The same WhatsApp session (one linked phone) serves both groups. NanoClaw routes messages based on which chat the message comes from.

- Message in Sergej's group → Bob reads `whatsapp_physio_assistant/data/` → Sergej's calendar
- Message in client co-pilot's group → Bob reads `whatsapp_physio_assistant_prd/data/` → client's calendar

---

## Prod Setup Steps (run at handover)

Run from `/root/nanoclaw/`.

**1. Create the prod group folder:**
```bash
mkdir -p groups/whatsapp_physio_assistant_prd/data
cp groups/whatsapp_physio_assistant/CLAUDE.md groups/whatsapp_physio_assistant_prd/CLAUDE.md
cp groups/whatsapp_physio_assistant/data/.env groups/whatsapp_physio_assistant_prd/data/.env
```

**2. Copy client credentials into prod folder:**
```bash
# After completing handover.md credential steps:
cp <client_credentials.json> groups/whatsapp_physio_assistant_prd/data/credentials.json
cp <client_token.json>       groups/whatsapp_physio_assistant_prd/data/token.json
```

**3. Create prod config.json:**
```bash
# calendarId = client's calendar ID (from handover.md)
# homeCoords = client's home address coords (same or updated)
cat > groups/whatsapp_physio_assistant_prd/data/config.json << 'EOF'
{
  "calendarId": "<client_calendar_id>",
  "homeCoords": { "lat": 50.9333, "lng": 6.9500 },
  "timezone": "Europe/Berlin"
}
EOF
```

**4. Copy physio.db from dev (geocache + patient mappings):**
```bash
cp groups/whatsapp_physio_assistant/data/physio.db \
   groups/whatsapp_physio_assistant_prd/data/physio.db
```

**5. Create a WhatsApp group for the client co-pilot and find its JID:**
```bash
sqlite3 store/messages.db "SELECT jid, name FROM chats ORDER BY last_message_time DESC LIMIT 10;"
```

**6. Register the prod group in NanoClaw:**
```bash
sqlite3 store/messages.db "
INSERT INTO registered_groups (jid, name, folder, trigger_pattern, added_at, container_config, requires_trigger, is_main)
VALUES ('<PROD_GROUP_JID>', 'Physio Assistant', 'whatsapp_physio_assistant_prd', '0', datetime('now'),
  '{\"additionalMounts\":[{\"hostPath\":\"/root/nanoclaw/.claude/skills/physio-routing\",\"containerPath\":\"physio-routing\",\"readonly\":true}]}',
  0, 0);
"
```

**7. Restart NanoClaw:**
```bash
systemctl restart nanoclaw
```

**8. Verify both groups respond independently:**
- Send a booking request to each group and confirm Bob reads the correct calendar

---

## Syncing Dev → Prod

| File | Direction | Notes |
|------|-----------|-------|
| `SKILL.md` + `routing.py` | automatic | one shared copy at `.claude/skills/physio-routing/` |
| `CLAUDE.md` | dev → prod (copy) | copy when Bob's instructions change |
| `config.json` | **never** | environment-specific (calendarId, homeCoords) |
| `physio.db` | prod → dev | copy prod → dev for realistic testing; never dev → prod |
| `token.json` | **never** | environment-specific OAuth token |
| `credentials.json` | **never** | environment-specific GCP app |
| `.env` | **never** | same key value, but each folder keeps its own copy |
| `store/messages.db` | prod → dev (snapshot) | only when reproducing a prod issue |

### Syncing CLAUDE.md after instruction changes:
```bash
cp groups/whatsapp_physio_assistant/CLAUDE.md groups/whatsapp_physio_assistant_prd/CLAUDE.md
```

### Copying prod physio.db to dev for realistic testing:
```bash
cp groups/whatsapp_physio_assistant_prd/data/physio.db \
   groups/whatsapp_physio_assistant/data/physio.db
```
Never copy in the other direction — dev data is throwaway.
