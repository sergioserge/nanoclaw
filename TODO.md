# TODO

## Bugs & Improvements

- [ ] `container-runner.ts` — long-term: run nanoclaw service under uid 1000 instead of root to avoid chmod 0o777 on sessions/IPC dirs
- [ ] `identify_cluster` — document or fix first-match-wins behaviour (overlapping cluster radii, e.g. Mitte anchor is inside Süd radius)
- [ ] Run actual inbox sort — inbox was never processed by the proper workflow; both April 23 runs bypassed it
- [ ] Create `groups/whatsapp_physio_assistant_prd/data/.env` with `GOOGLE_MAPS_API_KEY` before handover (same key as dev, owned by nanoclaw, chmod 640)

## Features

### Document Organizer

- [ ] **Action items** — after sorting, extract tasks from documents and include in the WhatsApp report: bills → "pay by [due date]", letters → "reply by [date]", contracts → "sign/return by [date]"
- [ ] **Accounting export** — prepare a summary of income and expenses (Einnahmen/Ausgaben) from sorted Eingangsrechnungen and Ausgangsrechnungen suitable for handover to an accountant or entry into a GuV spreadsheet
- [ ] **Tax audit preparation** — identify and bundle documents required for a Finanzamt tax audit (Betriebsprüfung): invoices, contracts, insurance correspondence, tax filings; generate a checklist of what is present and what is missing

### Physio Routing

*(none yet)*

---

## Done (2026-04-24)

- [x] `clear_stale_session.sh` — verify `sessions` table schema; rewrite SQL to use parameterised queries not shell interpolation
- [x] `organizer.py` — fix typo `unssortiertFolderId` → `unsortiertFolderId`
- [x] `routing.py` — wrap `requests.get` in `try/except RequestException`
- [x] `routing.py` — move `import hashlib` / `import math` to top-level imports
- [x] `organizer.py` — replace bare `open(...)` with `with open(...) as f:`
- [x] `SKILL.md` — hard rules: never access `documents.db` directly; never call Google API directly
- [x] `organizer.py` `list_inbox` — add pagination for inboxes >100 files
