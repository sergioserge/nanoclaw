# Project Dev Learnings

Post-build retros for skill builds. Each entry: what was non-obvious, what would have saved time, what to carry into the next build.

---

## 2026-04-29 — `/relink-whatsapp`

**Build context:** Operator uninstalled WhatsApp on the bot's phone, severing the Baileys device pairing. Service flapping in tight restart loop with 401. Bundled the recovery into a reusable operational skill.

**Lessons worth carrying forward:**

- **The systemd service does not auto-print a QR.** When `creds.json` is missing or invalid, NanoClaw exits with `WhatsApp authentication required. Run /setup`. Pairing must be initiated through `setup/index.ts --step whatsapp-auth` — a separate process from the main service. Future skills that touch auth lifecycle should not assume `systemctl restart` triggers a fresh QR flow.

- **Three files lie about auth state, not just one.** `store/auth/` is the obvious one, but `store/auth-status.txt` (sentinel string `"authenticated"`) and `store/pairing-code.txt` (transient code) persist their last value across a 401 and mislead diagnostics. Any auth-clearing procedure must move all three aside.

- **Ownership trap: always run auth as the `nanoclaw` user.** The service runs as `User=nanoclaw` per the systemd unit. Running `npx tsx setup/index.ts` as root creates root-owned files in `store/auth/`, after which the service silently re-enters the 401 loop because it can't read its own credentials. `sudo -u nanoclaw bash -c '...'` is mandatory.

- **`registered_groups` survives re-pair.** Group JIDs are tied to the WhatsApp group on the server, not to the linked device. After re-pairing, all 4 rows continued working without DB edits. Future skills should not include speculative re-registration steps "just in case."

- **Memory drift: JID memory was wrong.** A 6-day-old memory had Physio Assistant Dev's JID confused with My Office Dev's. Verifying against `store/messages.db` first caught it. Reinforces the rule: read the live DB before acting on cached JIDs.

**What would have saved time:** Reading `add-whatsapp/SKILL.md` Phase 3 *before* designing the recovery plan. The canonical re-pair command and pairing-code flow are documented there; the original plan to "restart and watch for QR" wasted ~5 minutes of investigation. Next operational skill: search existing skills for the closest analogue first.

**Follow-up finding (same day, after roundtrip testing):** Auto-recovery of per-chat Signal Protocol sessions is **asymmetric** across groups. Smaller/newer groups (DEV) recovered cleanly on first message exchange; the older/larger PRD group did not — operator's phone showed bot replies as "Waiting for this message..." indefinitely while `store/messages.db` confirmed the bot was sending and receiving fine. Root cause: SKDM (Sender Key Distribution Message) gets shipped only on the bot's first send per group post-relink; if any recipient device's point-to-point session is in a transient half-resynced state at that moment, the SKDM is lost and Baileys never redistributes. Fix paths in increasing intrusiveness: bot-side sender-key rotation (delete `store/auth/sender-key-<jid>*` + restart) or group admin remove/re-add. Future re-link procedures must include a per-group post-relink check, not just a smoke test on the most-tested group. Skill updated with a "Post-relink session recovery" section.

---

## 2026-04-29 — Physio list + delete intents (extending physio-routing skill)

**Build context:** Lange asked Bob "Kannst du mir nicht sagen welche Termine ich morgen habe?" — Bob refused per its narrow create-only scope. Extended Bob from one intent (Booking) to three (Booking, List, Delete) with dateparser-based date resolution and server-side name search.

**Lessons worth carrying forward:**

- **Match existing skill conventions before introducing new abstractions.** Initial Phase 2 plan added Python helpers to `routing.py`. Re-reading the existing skill mid-build revealed the actual pattern: `routing.py` is reserved for VRP math + geocoding; Calendar API operations live as inline Python in SKILL.md. Adding helpers would have mixed concerns and introduced unnecessary abstraction. Final implementation: zero `routing.py` changes, all logic inline in SKILL.md matching the existing create flow. **Generalizable rule:** before designing helpers for a feature extension, study the existing skill's separation of concerns and follow it — the cleanest extension is the one that doesn't introduce a new pattern.

- **Concise spec iteration is a real cost reduction.** Phase 0 spec was rejected for verbosity twice ("too much for me to read") before landing. The cuts (drop tool inventory tables, drop redundant out-of-scope lists, drop process explanations the user already knows) made the spec actually reviewable. Future Phase 0: write tight from the first draft — name only what truly needs the user's input.

- **Server-side filtering changes the cost equation.** Initial worry about a ±30-day search window was mitigated by Calendar API's `q=` parameter (server-side full-text search). 250 events client-side became 2-3 events on the wire. Token cost stays near zero because the Python helper filters before the LLM sees the data. **Generalizable rule:** when designing search-by-name flows over an external API, check whether the API does the filtering server-side before assuming client-side cost.

- **Pre-existing uncommitted work should be committed separately.** Working tree had 2026-04-28 calendar-architecture work mixed with today's edits. Splitting into two commits (Sergej's prior work first, then today's feature) gave a clean audit trail. The `git add -p`-style temporary-revert-then-restore pattern via Edit worked when interactive staging wasn't available.

- **The "no safety theater" rule applied here.** Initially proposed refusing past-appointment deletes "for safety." Sergej challenged: "tell me if there are reasons you see and I overlook." There weren't — past-delete is *less* operationally risky than future-delete. Corrected the spec, saved a feedback memory, and applied the principle in the build (±30 day window covers past + future symmetrically).

- **Verify before committing pre-existing changes you didn't write.** Sergej explicitly asked me to make sure I understood each pre-existing diff before bundling. The 5 minutes of `git diff` reading was cheaper than committing the wrong scope. **Generalizable rule:** before staging files you didn't author, read the diff and confirm intent matches the surrounding context (TODO entries, memory, existing patterns).

**What would have saved time:** Reading the existing `routing.py` and SKILL.md *first* in Phase 0, before designing helpers. The "extend routing.py" path was wrong from the start; the audit at the start of Phase 3 caught it but only after the spec had committed to that direction. Future skill extensions: include a "study existing layout" step in Phase 0, before listing files-to-change.
