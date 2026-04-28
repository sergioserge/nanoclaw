---
name: gdrive-document-organizer
description: Organizes documents in Google Drive for the physio practice. Activates when the co-pilot sends a document organization request. Reads files from an inbox folder, classifies them, extracts metadata for search, and moves them to the correct subfolder.
---

# Google Drive Document Organizer Skill

Operational skill for the `whatsapp_document_organizer` group.

## Credentials & Config

All files live at `/workspace/group/data/`:
- `credentials.json` — Google OAuth client credentials (same GCP project as Calendar)
- `token.json` — OAuth token with Drive scope
- `config.json` — `rootFolderId`, `inboxFolderId`, `unsortiertFolderId`, `timezone`, `maxFileSizeBytes`
- `documents.db` — SQLite document index (search metadata)

Required OAuth scope:
- `https://www.googleapis.com/auth/drive`

Google Maps API key is not used by this skill.

## Initial Setup (run once per installation)

Creates the "Document Organizer" root folder in Drive with default subfolders, and writes `config.json`:

```bash
python3 /workspace/project/.claude/skills/gdrive-document-organizer/organizer.py \
  '{"action": "setup_drive"}'
```

Default subfolders created: Inbox, Unsortiert, Eingangsrechnungen, Ausgangsrechnungen, Krankenkasse, Steuer, Verträge, Sonstiges.

The user can rename, add, or delete category folders in Drive at any time — Bob always reads the live folder list at sort time. Only `rootFolderId` and `inboxFolderId` are fixed after setup.

## Trigger

Activate when the co-pilot sends a document organization request.

Examples:
- "Sort the inbox"
- "Organisiere die neuen Dokumente"
- "Was liegt noch im Eingang?"
- "Find my 2025 tax documents"
- "Zeig mir alle AOK-Rechnungen"

## Supported File Types

| Type | Library | Notes |
|------|---------|-------|
| PDF (native) | PyMuPDF (`fitz`) | Text extractable directly |
| PDF (scanned) | — | Flag as unreadable, leave in inbox |
| DOCX | `python-docx` | Full text extraction |
| XLSX / CSV | `openpyxl` / `csv` | Read cell values |

Files over 20 MB: warn the co-pilot before downloading. Do not process silently.

## Folder Structure (Google Drive)

```
Document Organizer/        ← rootFolderId
├── Inbox/                 ← inboxFolderId — new files land here
├── Unsortiert/            ← unsortiertFolderId — unreadable/unclassifiable files
└── [category folders]/    ← whatever the user has created in Drive
```

Category folders are read live from Drive at sort time via `list_folders`. The user can rename, add, or delete category folders freely — Bob always works with what actually exists. Bob never creates new category folders; if a file doesn't fit any existing folder, it goes to Unsortiert with a note suggesting a new folder name.

## Hard Rules (Non-Negotiable)

**NEVER access `documents.db` directly.** Do not read from it, write to it, or query it with SQL. All database writes happen inside `organizer.py` as a side-effect of `move_file`. The DB is an implementation detail — it is not a source of truth for what is in the inbox.

**NEVER call the Google Drive API directly** (not in inline Python, not via subprocess calls to anything other than `organizer.py`). All Drive operations go through `organizer.py` actions. No exceptions.

**NEVER look at the Unsortiert folder** unless the co-pilot explicitly asks about it. The Unsortiert folder is a legacy migration area, not the inbox. Sorting the inbox does not touch Unsortiert.

## Workflow: Organize Inbox

All Drive operations go through `organizer.py`. Call it via subprocess only:

```bash
python3 /workspace/project/.claude/skills/gdrive-document-organizer/organizer.py '<json_input>'
```

### Step 1 — Ensure Unsortiert exists

```json
{"action": "ensure_unsortiert"}
```

Returns: `{"folder_id": "...", "created": false}`

If `created` is true, note it in the report. This step is mandatory — Unsortiert must exist before any processing begins.

### Step 2 — Get current category folders (live from Drive)

```json
{"action": "list_folders"}
```

Returns: `{"folders": [{"id": "...", "name": "Eingangsrechnungen"}, ...]}`

This is the complete list of valid move targets for this sort run. It reflects whatever folders the user currently has in Drive.

### Step 3 — List inbox (mandatory before processing any file)

```json
{"action": "list_inbox"}
```

Returns: `{"files": [...], "count": N}`

**If `count == 0`:** Reply "Posteingang ist leer — keine neuen Dokumente." and STOP. Do not look at any other folder. Do not inspect `documents.db`. Do not do anything else.

**If `count > 0`:** Proceed with the exact list returned. This is the complete work queue — do not add files from any other source.

### Step 4 — For each file: extract text

```json
{"action": "extract_text", "file_id": "...", "mime_type": "application/pdf", "size_bytes": 102400}
```

Returns one of:
- `{"status": "ok", "text": "..."}` → proceed to Step 5
- `{"status": "scanned_pdf"}` → call `move_unsortiert` with `reason: "scanned_pdf"`
- `{"status": "too_large"}` → call `move_unsortiert` with `reason: "too_large"`
- `{"status": "unsupported"}` → call `move_unsortiert` with `reason: "unsupported"`

`text` is truncated to 4000 characters — use this for classification. The complete document text is written directly to a local staging table by `organizer.py` and is never sent to Bob.

### Step 5 — Classify (Bob's job — no organizer.py action)

Pick the best matching folder from the Step 2 list by name. Determine:
- `folder_id` and `folder_name`: from the Step 2 list
- `summary`: 1–2 sentence description
- `key_fields`: structured metadata (e.g. `{"amount": "€240", "date": "2025-03-15", "sender": "AOK Bayern"}`)
- `tags`: 3–5 keywords for future search

The goal is LLM-retrievable metadata: a future query like "find 2025 tax documents" must resolve without re-reading the files.

If no existing folder fits, call `move_unsortiert` and mention the suggested new folder name in the report. Never leave a file in the inbox because classification was uncertain.

### Step 6 — Move file and index it

```json
{
  "action": "move_file",
  "file_id": "...",
  "file_name": "AOK_Rechnung_März.pdf",
  "folder_id": "<id from list_folders>",
  "folder_name": "Eingangsrechnungen",
  "summary": "AOK invoice for March 2025, €240",
  "key_fields": {"amount": "€240", "date": "2025-03-15", "sender": "AOK Bayern"},
  "tags": ["AOK", "2025", "Rechnung", "März"]
}
```

Returns: `{"status": "ok", "moved_to": "Eingangsrechnungen"}`

For files going to Unsortiert:

```json
{"action": "move_unsortiert", "file_id": "...", "reason": "scanned_pdf"}
```

Repeat Steps 4–6 for every file in the Step 3 list.

### Step 7 — Verify inbox is empty

```json
{"action": "list_inbox"}
```

- If `count == 0`: success, proceed to Step 8.
- If `count > 0`: something was missed. Report remaining file names with a warning.

### Step 8 — Report back

```
📁 3 Dokumente sortiert:

• AOK_Rechnung_März.pdf → Eingangsrechnungen (€240, 15.03.2025)
• Steuervorauszahlung_Q1.pdf → Steuer (€1.200, Q1 2025)
• Vertrag_Musterstraße.docx → Verträge

⚠ 1 Dokument nach Unsortiert verschoben: Scan_unlesbar.pdf (gescanntes PDF)

💡 Vorschlag neuer Ordner: "Fortbildung" (1 Dokument passt nirgends)
```

## Workflow: Search Documents

Activate when the co-pilot asks to find a document (e.g. "Find my 2025 AOK invoices").

```bash
python3 /workspace/project/.claude/skills/gdrive-document-organizer/organizer.py '{"action": "search", "query": "AOK 2025"}'
```

Returns matching documents from the local index. Do not re-download or re-classify — the index is the source of truth for search.

## Failure Modes

| Situation | Handling |
|-----------|----------|
| Token missing Drive scope | Catch `HttpError 403`, tell co-pilot to re-run OAuth with Drive scope |
| Target folder deleted | Re-create it under `rootFolderId`, then move the file |
| File > 20 MB | Warn co-pilot, skip — do not download |
| Scanned PDF | Flag in report, leave in inbox |
| Unsupported MIME type | Log name, leave in inbox, mention in report |

## Installing Python Dependencies

```bash
pip install --quiet google-api-python-client google-auth PyMuPDF python-docx openpyxl
```

## Data Rules

- Document text is processed locally and by Bob (LLM) for classification — this is internal business data, not patient PII
- `documents.db` is the persistent index — never delete it without backing up
- Bob only ever sees the first 4000 characters of each document; the complete text is written to a local staging table by `organizer.py` and transferred to `documents.db` during `move_file` — it never passes through Bob
- Raw file content is not stored on the VPS beyond the extraction step
