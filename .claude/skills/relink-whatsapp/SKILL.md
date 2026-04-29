---
name: relink-whatsapp
description: Re-link the WhatsApp channel after a 401 disconnect (phone uninstall/reinstall, manual unlink, or expired session). Wipes stale Baileys auth and runs a fresh pairing-code flow. Group registrations are preserved.
---

# Re-link WhatsApp

Use when WhatsApp authentication has been severed and the bot can no longer connect. Group registrations in `registered_groups` survive — do **not** re-add groups.

## When to use

- `journalctl -u nanoclaw` shows tight restart loop (`Restart counter at N` climbing)
- `logs/nanoclaw.error.log` shows `WhatsApp authentication required. Run /setup in Claude Code.`
- `logs/nanoclaw.log` shows `Connection closed reason: 401 shouldReconnect: false`
- Operator uninstalled WhatsApp on the bot's phone, or unlinked the device manually
- `store/auth/creds.json` exists but no longer pairs

## Out of scope

- Fresh install (use `/setup` and `/add-whatsapp`)
- Re-registering groups (rows in `registered_groups` are stable across re-pair)
- Adding/removing channels, trigger phrase changes, container rebuild

## Inputs needed before starting

1. Operator's phone number — country code + number, **digits only, no `+` or spaces**. Example: `4915123456789`.
2. Operator's phone within reach, WhatsApp installed, ready to navigate to **Settings → Linked Devices → Link a Device → Link with phone number instead**. Pairing codes expire in ~60 seconds.

## Procedure

### Step 1 — Audit

```bash
cd /root/nanoclaw
systemctl status nanoclaw --no-pager | head -10
tail -20 logs/nanoclaw.error.log
ls -la store/auth/creds.json store/auth-status.txt store/pairing-code.txt 2>&1
```

Confirm the symptoms above. If the failure mode is different (e.g. Docker down, OneCLI proxy issue), do not proceed — diagnose first via `/debug`.

### Step 2 — Stop the flapping service

```bash
systemctl stop nanoclaw
systemctl is-active nanoclaw  # expect: inactive
```

### Step 3 — Move stale auth state aside (reversible)

A timestamp suffix preserves backups for ~24h in case rollback is needed. Do **not** delete here.

```bash
TS=$(date +%Y-%m-%d-%H%M)
mv store/auth store/auth.broken-$TS
mv store/auth-status.txt store/auth-status.txt.broken-$TS 2>/dev/null
mv store/pairing-code.txt store/pairing-code.txt.broken-$TS 2>/dev/null
ls store/*.broken-* | head
```

All three files lie about the auth state after a 401 (`auth-status.txt` keeps saying "authenticated"; `pairing-code.txt` keeps an old code). Move all three.

### Step 4 — Run pairing-code auth as the `nanoclaw` user

Running as root creates root-owned files the service cannot read. Always use `sudo -u nanoclaw`.

```bash
PHONE=<digits-only-phone-number>
rm -f /tmp/wa-auth.log /root/nanoclaw/store/pairing-code.txt
sudo -u nanoclaw bash -c "cd /root/nanoclaw && nohup npx tsx setup/index.ts --step whatsapp-auth -- --method pairing-code --phone $PHONE > /tmp/wa-auth.log 2>&1 &"
```

Poll for the code (typically appears in 2–5s):

```bash
for i in $(seq 1 30); do
  [ -f store/pairing-code.txt ] && cat store/pairing-code.txt && break
  sleep 1
done
```

**Display the code to the operator immediately.** Tell them to enter it on their phone within 60s via **Settings → Linked Devices → Link a Device → Link with phone number instead**.

Poll for completion:

```bash
for i in $(seq 1 90); do
  grep -q 'AUTH_STATUS: authenticated' /tmp/wa-auth.log && echo OK && break
  grep -q 'AUTH_STATUS: failed' /tmp/wa-auth.log && echo FAIL && break
  sleep 2
done
test -f store/auth/creds.json && echo "creds.json present"
```

### Step 5 — Restart service and verify

```bash
systemctl start nanoclaw
sleep 6
systemctl is-active nanoclaw                     # expect: active
systemctl show nanoclaw -p NRestarts             # expect: low single-digit
tail -30 logs/nanoclaw.log
```

In the log, confirm three things:
- `Connected to WhatsApp`
- `groupCount: 4` (or whatever count is registered — query `SELECT COUNT(*) FROM registered_groups;` in `store/messages.db`)
- No new `Connection closed reason: 401` lines

### Step 6 — Roundtrip test in DEV groups only

Ask the operator to send `@Bob ping` (or any test) in a **dev** group only — never in PRD groups, where real users would see the message. Confirm a container spin-up in the log:

```bash
tail -f logs/nanoclaw.log | grep -E 'Spawning container|Container completed'
```

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `Pairing failed` on phone | Phone already has 4 linked devices | WhatsApp app → Linked Devices → remove an old entry, retry Step 4 |
| `AUTH_STATUS: failed` with `qr_timeout` | Code wasn't entered in time | Re-run Step 4 (auth folder is already clean) |
| `AUTH_STATUS: failed` with `logged_out` | Number rejected by WhatsApp | Confirm phone number is correct, retry Step 4 |
| `AUTH_STATUS: failed` with `515` | Baileys handshake glitch | Re-run Step 4 — usually transient |
| Service starts but immediately 401 again | Auth files owned by root | `chown -R nanoclaw:nanoclaw store/auth` |
| Service active but no `Connected to WhatsApp` log within 10s | Network or OneCLI gateway issue | Check `docker ps` for OneCLI; investigate via `/debug` |

## Alternative: QR-terminal auth method

If pairing-code is unavailable (e.g. phone rejects code repeatedly), substitute Step 4 with:

```bash
sudo -u nanoclaw bash -c "cd /root/nanoclaw && nohup npx tsx setup/index.ts --step whatsapp-auth -- --method qr-terminal > /tmp/wa-auth.log 2>&1 &"
tail -f /tmp/wa-auth.log  # ASCII QR appears here
```

Operator scans with phone camera via **Linked Devices → Link a Device**. Less reliable over SSH if the terminal font shrinks the QR.

## Cleanup (after ~24h of stable uptime)

```bash
rm -rf store/auth.broken-* store/auth-status.txt.broken-* store/pairing-code.txt.broken-*
```

## What this skill does NOT touch

- `store/messages.db` `registered_groups` table — group rows persist across re-pair, JIDs are stable
- `groups/*/data/` — credentials, tokens, configs all preserved
- `.claude/skills/` — skill code untouched
- Container build cache — no rebuild required
- `.env` — secrets untouched
