# TODO

## Bugs & Improvements

- [x] `SKILL.md` — read events from both the "Physio Bot" calendar (calendarId) AND the therapist's primary calendar; dedup by event id; already implemented in SKILL.md (2026-04-27)
- [ ] `container-runner.ts` — long-term: run nanoclaw service under uid 1000 instead of root to avoid chmod 0o777 on sessions/IPC dirs
- [x] `identify_cluster` — fixed first-match-wins: now returns nearest cluster within radius, not first match (2026-04-24)
- [ ] Run actual inbox sort — inbox was never processed by the proper workflow; both April 23 runs bypassed it
- [x] Delete `groups/whatsapp_physio_assistant_prd/` and `docs/dev-prod-setup.md` — artifacts of an abandoned rename plan; production is `whatsapp_physio_assistant`, dev is `whatsapp_physio_assistant_dev` (2026-04-27)

## Features

### Document Organizer

- [ ] **Action items** — during classification, Bob extracts actionable deadlines from documents (bills → "pay by [due date]", subscriptions → "cancel before [date]", letters → "reply by [date]", contracts → "sign/return by [date]"); stored in a `tasks` table in `documents.db`; surfaced in the WhatsApp sort report and optionally written to Google Calendar as reminders
- [ ] **Accounting export** — during classification, Bob extracts standardised invoice fields (IBAN, due date, tax amount, net/gross); stored in `key_fields`; new `export_accounting` action queries `documents.db` for a date range and writes CSV or Google Sheet for accountant handover (Einnahmen/Ausgaben / GuV)
- [ ] **Keyword search** — replace current `LIKE`-based search with SQLite FTS5 virtual table; indexes `summary + tags + key_fields + full_text` at `move_file` time; returns BM25-ranked results; no API calls, no embeddings, zero extra cost
- [ ] **Tax audit preparation** — identify and bundle documents required for a Finanzamt tax audit (Betriebsprüfung): invoices, contracts, insurance correspondence, tax filings; generate a checklist of what is present and what is missing
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
