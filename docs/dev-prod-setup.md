# Dev / Prod Setup

## Why This Approach

Switching credentials via file swapping and NanoClaw restarts is fragile and takes prod offline during development. Instead, we register two NanoClaw groups simultaneously — dev and prod run in parallel, each reading from their own credential folder. No swapping, no restarts, no downtime.

---

## Before Setup (Historical Context)

Originally the setup split data and runtime across two folders, with data inaccessible inside the container:

```
groups/
├── whatsapp_physio_assistant/   ← active NanoClaw group (CLAUDE.md + logs only)
│   └── CLAUDE.md
│
└── physio-copilot/              ← data folder (not mounted in container — credentials unreachable)
    └── data/
        ├── credentials.json
        ├── token.json
        ├── config.json
        └── physio.db
```

Steps 1 and 2 below resolved this. `physio-copilot/data/` still exists as a reference copy but is no longer the active source.

---

## Target Structure (Dev + Prod)

Prod keeps its existing folder name (`whatsapp_physio_assistant`). Dev gets a new parallel group. Data lives inside each group folder so it's accessible inside the container at `/workspace/group/data/`.

```
groups/
├── whatsapp_physio_assistant/       ← prod group (existing, unchanged)
│   ├── CLAUDE.md                    ← symlink → ../shared/CLAUDE.md
│   └── data/
│       ├── credentials.json         ← client's GCP OAuth app
│       ├── token.json               ← client's Google OAuth token
│       ├── config.json              ← client's calendarId, homeCoords, timezone
│       └── physio.db
│
├── whatsapp_physio_assistant_dev/   ← dev group (new)
│   ├── CLAUDE.md                    ← symlink → ../shared/CLAUDE.md
│   └── data/
│       ├── credentials.json         ← Sergej's GCP OAuth app (or shared with prod)
│       ├── token.json               ← Sergej's Google OAuth token
│       ├── config.json              ← Sergej's calendarId, homeCoords, timezone
│       └── physio.db
│
└── shared/
    └── CLAUDE.md                    ← single source of truth for Bob's instructions
```

**What differs between dev and prod:** `token.json`, `config.json` (calendarId + homeCoords), `physio.db`

**What is shared:** routing skill — `SKILL.md` + `routing.py` live at `.claude/skills/physio-routing/`, one copy mounted into every container. Routing constants are hard-coded in `routing.py`, not in `config.json`. `CLAUDE.md` shared via symlink to `groups/shared/CLAUDE.md`.

Inside the container, credentials are accessible at `/workspace/group/data/`.

---

## How Dev Triggering Works

Create a WhatsApp group with Sergej and Bob's number (the linked phone) and link it to `whatsapp_physio_assistant_dev`. The same WhatsApp session (one phone linked) serves both groups — NanoClaw routes messages based on which chat group they come from.

- Message `whatsapp_physio_assistant_dev` group → Bob reads `whatsapp_physio_assistant_dev/data/` → Sergej's calendar
- Message `whatsapp_physio_assistant` group → Bob reads `whatsapp_physio_assistant/data/` → client's calendar

---

## Setup Steps

Run from `/root/nanoclaw/`.

**1. Create the shared CLAUDE.md:** ✅ done on this VPS
```bash
mkdir -p groups/shared
cp groups/whatsapp_physio_assistant/CLAUDE.md groups/shared/CLAUDE.md
# Replace prod CLAUDE.md with symlink:
ln -sf ../shared/CLAUDE.md groups/whatsapp_physio_assistant/CLAUDE.md
```

**2. Move prod data into the group folder:** ✅ done on this VPS
```bash
mkdir -p groups/whatsapp_physio_assistant/data
cp groups/physio-copilot/data/* groups/whatsapp_physio_assistant/data/
```

**3. Create the dev group folder:**
```bash
mkdir -p groups/whatsapp_physio_assistant_dev/data
ln -s ../shared/CLAUDE.md groups/whatsapp_physio_assistant_dev/CLAUDE.md
```

**4. Copy dev credentials (Sergej's) into dev folder:**
```bash
# Pre-handover: source is physio-copilot/data/ (still has Sergej's credentials)
cp groups/physio-copilot/data/credentials.json groups/whatsapp_physio_assistant_dev/data/
cp groups/physio-copilot/data/token.json groups/whatsapp_physio_assistant_dev/data/
cp groups/physio-copilot/data/config.json groups/whatsapp_physio_assistant_dev/data/

# Post-handover: source is the dev backups from handover.md (Step 1)
# cp groups/physio-copilot/data/credentials.dev.json groups/whatsapp_physio_assistant_dev/data/credentials.json
# cp groups/physio-copilot/data/token.dev.json groups/whatsapp_physio_assistant_dev/data/token.json

# Verify calendarId is Sergej's:
cat groups/whatsapp_physio_assistant_dev/data/config.json
```

**5. Register the dev group in NanoClaw:**
```bash
# Create a WhatsApp group and add Bob's number (the linked phone) to it.
# Pre-handover: Sergej's phone is linked, so use a second phone or WhatsApp account to create the group.
# Post-handover: Sergej can create the group from his own phone since the client's phone is linked.
# Then find the new group's JID:
sqlite3 store/messages.db "SELECT jid, name FROM chats ORDER BY last_message_time DESC LIMIT 10;"

# Register it:
sqlite3 store/messages.db "
INSERT INTO registered_groups (jid, name, folder, trigger_pattern, added_at, container_config, requires_trigger, is_main)
VALUES ('<DEV_GROUP_JID>', 'Physio Dev', 'whatsapp_physio_assistant_dev', '@Bob', datetime('now'), NULL, 1, 0);
"
```

**6. Restart NanoClaw:**
```bash
systemctl --user restart nanoclaw
```

**7. Verify both groups respond independently:**
- Send `@Bob test` to each group and confirm Bob responds
- Full routing verification (calendar reads, slot suggestions) requires the physio-routing skill to be built first (Step 6 of the main setup)

---

## Syncing Dev and Prod

### The Challenge

Not everything flows in the same direction. The classic assumption — dev changes flow to prod — breaks for data files where prod is the source of truth. Some files are environment-specific and must never be synced. Getting the direction wrong can overwrite real patient data or live credentials.

**When reviewing this section, check:**
- Is the direction correct for each file?
- Are any new files introduced by skill changes missing from this table?
- Is `physio.db` protected from accidental overwrite in the wrong direction?

### Sync Direction Table

| File | Direction | Reason |
|------|-----------|--------|
| `SKILL.md` + `routing.py` | dev → prod | code lives in dev, released to prod |
| `CLAUDE.md` | shared via symlink | single source of truth, no sync needed |
| `config.json` | **never** | all values are environment-specific (calendarId, homeCoords, timezone) |
| `physio.db` | **prod → dev** | real patient mappings and geocache built in prod — copy to dev for realistic testing |
| `token.json` | **never** | environment-specific Google OAuth |
| `credentials.json` | **never** | environment-specific GCP app |
| `store/auth/` | **never** | phone-specific WhatsApp session |
| `store/messages.db` | prod → dev on demand | copy as snapshot when reproducing a prod issue |

### Syncing Code (dev → prod)

**CLAUDE.md** — automatically in sync via symlink. Edit `groups/shared/CLAUDE.md` once.

**Routing skill** — automatically in sync. One file at `.claude/skills/physio-routing/`, mounted into all containers.

**config.json** — never synced. All values (calendarId, homeCoords, timezone) are environment-specific. Routing constants (bridge penalty, thresholds, cluster rules) are hard-coded in `routing.py` per spec — not in config.json.

### Syncing Data (prod → dev)

**physio.db** — copy from prod to dev when you need realistic patient data for testing:
```bash
cp /root/nanoclaw/groups/whatsapp_physio_assistant/data/physio.db \
   /root/nanoclaw/groups/whatsapp_physio_assistant_dev/data/physio.db
```
Never copy in the other direction — dev data is throwaway.

**store/messages.db** — both groups share the same messages.db. To investigate a prod issue, take a snapshot before switching to dev testing:
```bash
cp /root/nanoclaw/store/messages.db /root/nanoclaw/store/messages.db.snapshot-$(date +%Y%m%d)
```
