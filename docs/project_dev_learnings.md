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
