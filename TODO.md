# TODO

## Bugs & Improvements

- [ ] `routing.py` — read freebusy from both the "Physio Bot" calendar (calendarId) AND the therapist's primary calendar, so Bob sees real availability while writing only to the bot calendar (safety guardrail until bot is confirmed reliable)
- [ ] `container-runner.ts` — long-term: run nanoclaw service under uid 1000 instead of root to avoid chmod 0o777 on sessions/IPC dirs
- [x] `identify_cluster` — fixed first-match-wins: now returns nearest cluster within radius, not first match (2026-04-24)
- [ ] Run actual inbox sort — inbox was never processed by the proper workflow; both April 23 runs bypassed it
- [x] Create `groups/whatsapp_physio_assistant_prd/data/.env` with `GOOGLE_MAPS_API_KEY` — already present, correct key and permissions (2026-04-24)

## Features

### Document Organizer

- [ ] **Action items** — after sorting, extract tasks from documents and include in the WhatsApp report: bills → "pay by [due date]", letters → "reply by [date]", contracts → "sign/return by [date]"
- [ ] **Accounting export** — prepare a summary of income and expenses (Einnahmen/Ausgaben) from sorted Eingangsrechnungen and Ausgangsrechnungen suitable for handover to an accountant or entry into a GuV spreadsheet
- [ ] **Tax audit preparation** — identify and bundle documents required for a Finanzamt tax audit (Betriebsprüfung): invoices, contracts, insurance correspondence, tax filings; generate a checklist of what is present and what is missing

### Physio Routing

- [ ] **Subscription usage tracking** — NanoClaw uses a claude.ai subscription (not an API key), so quota cannot be queried via API headers. Options: (a) track tokens consumed locally per container run and store in SQLite, report remaining estimate against known plan limit; (b) surface a `/usage` command in WhatsApp that shows today's and this-week's token spend. No programmatic endpoint exists for remaining claude.ai quota — any limit must be hardcoded from the plan or tracked client-side.

---

## Done (2026-04-24)

- [x] `clear_stale_session.sh` — verify `sessions` table schema; rewrite SQL to use parameterised queries not shell interpolation
- [x] `organizer.py` — fix typo `unssortiertFolderId` → `unsortiertFolderId`
- [x] `routing.py` — wrap `requests.get` in `try/except RequestException`
- [x] `routing.py` — move `import hashlib` / `import math` to top-level imports
- [x] `organizer.py` — replace bare `open(...)` with `with open(...) as f:`
- [x] `SKILL.md` — hard rules: never access `documents.db` directly; never call Google API directly
- [x] `organizer.py` `list_inbox` — add pagination for inboxes >100 files
