---
trigger: "update setup-template", "update the template", "sync setup template"
description: Syncs docs/nanoclaw-setup-template.md with lessons learned since the last sync date
---

# Skill: update-setup-template

## Purpose
Keep `docs/nanoclaw-setup-template.md` current by merging in new lessons from two sources:
- `docs/setup-notes.md` — structured lessons captured during sessions
- `git log` — code changes since last sync that may imply new patterns

## Step 1 — Read the last sync date

Read `docs/nanoclaw-setup-template.md`. Find the line:
```
**Last synced: YYYY-MM-DD**
```
Extract the date. Call it `SYNC_DATE`.

## Step 2 — Collect new lessons from setup-notes.md

Read `docs/setup-notes.md`. Filter for lines where the date field (`YYYY-MM-DD |`) is **on or after** `SYNC_DATE`. These are the candidate lessons to merge.

If no lines are on or after `SYNC_DATE`, report "No new notes since [SYNC_DATE]" and skip to Step 3.

## Step 3 — Collect relevant git changes

Run:
```bash
git -C /root/nanoclaw log --since="SYNC_DATE" --oneline
```

Scan the commit messages for anything that indicates a new operational pattern — e.g. permission fixes, new config files, new scripts, security changes. Add these as additional candidates if they are not already represented in the setup-notes.md entries.

## Step 4 — Check each candidate against the template

For each candidate lesson:

1. Identify which template section it belongs to (e.g. permissions → Section 3, group-config → Section 5, maps-api → Section 8).
2. Read that section of the template.
3. Search for keywords from the lesson (e.g. "onecli-proxy-ca", "requires_trigger", "ifconfig"). If a substantively equivalent point is already present, skip this candidate — do not duplicate.
4. If not covered: draft a concise addition. Match the existing tone and format of that section (bullet point, warning block, code block, or table row — whatever fits).

## Step 5 — Write additions to the template

For each addition that passed Step 4:
- Insert it in the correct section, in the right format
- If it belongs in the "Common Failure Modes" table (Section 16 Appendix), add a row there too
- Do not rewrite existing content — append or insert only

## Step 6 — Update the sync date

Replace the `**Last synced: YYYY-MM-DD**` line at the top of the template with today's date.

## Step 7 — Report

Tell the user:
- How many candidates were found
- How many were added (and where)
- How many were skipped (already covered)
- The new sync date

## Rules

- Never delete or rewrite existing template content — additions only
- Never add project-specific details (physio routing constants, specific JIDs, etc.) — template must stay generic
- If a lesson is project-specific, note it to the user but do not add it to the template
- Keep additions concise — one ⚠ warning block or 2-3 bullet points max per lesson
- After writing, verify the "Last synced" line was updated correctly
