# TODO

## From code review (2026-04-24)

- [x] `clear_stale_session.sh` — verify `sessions` table schema matches what script expects; rewrite SQL to use parameterised queries not shell interpolation (2026-04-24)
- [x] `organizer.py` — commit typo fix (`unssortiertFolderId` → `unsortiertFolderId`) and `prev_name` routing.py change (2026-04-24)
- [ ] `routing.py` — wrap `requests.get` in `try/except RequestException` for graceful degradation when Maps API is transient
- [ ] `routing.py` — move `import hashlib` / `import math` to top-level imports
- [x] `organizer.py` — replace bare `open(...)` with `with open(...) as f:` to avoid leaked file handles (2026-04-24)
- [ ] `container-runner.ts` — long-term: run nanoclaw service under uid 1000 instead of root to avoid chmod 0o777 on sessions/IPC dirs
- [ ] `identify_cluster` — document or fix first-match-wins behaviour (overlapping cluster radii, e.g. Mitte anchor is inside Süd radius)

## Document organizer bugs (2026-04-24)

- [x] `SKILL.md` — add explicit hard rule: never access `documents.db` directly; never call Google API directly; all operations must go through `organizer.py` (2026-04-24)
- [x] `organizer.py` `list_inbox` — add pagination (Google Drive returns max 100 per page; inbox with >100 files silently drops the rest) (2026-04-24)
- [ ] Run actual inbox sort — inbox was never processed by the proper workflow; both April 23 runs bypassed it
