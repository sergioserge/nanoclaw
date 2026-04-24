---
name: gdrive-document-organizer
description: Organizes documents in Google Drive for the physio practice. Activates when the co-pilot sends a document organization request. Reads files from an inbox folder, classifies them, extracts metadata for search, and moves them to the correct subfolder.
---

# Google Drive Document Organizer Skill

Operational skill for the `whatsapp_document_organizer` group.

## Credentials & Config

All files live at `/workspace/group/data/`:
- `credentials.json` — Google OAuth client credentials (same GCP project as Calendar)
- `token.json` — OAuth token with both Calendar and Drive scopes
- `config.json` — `inboxFolderId`, `rootFolderId`, `timezone`
- `documents.db` — SQLite document index (search metadata)

Required OAuth scopes (both must be present in token):
- `https://www.googleapis.com/auth/calendar`
- `https://www.googleapis.com/auth/drive`

Google Maps API key is not used by this skill.

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
Document Organizer/
├── Inbox/                 ← inboxFolderId — new files land here
├── Eingangsrechnungen/    ← bills received (you pay)
├── Ausgangsrechnungen/    ← invoices sent (clients/insurance pay)
├── Krankenkasse/          ← insurance correspondence
├── Steuer/                ← tax documents
├── Verträge/              ← contracts
└── Sonstiges/             ← unclassifiable
```

Category folder IDs are defined in `config.json` under `categories`. The AI must only pick from this list — it never creates new folders. If a file cannot be classified into any existing category, leave it in the inbox and flag it in the report with a suggested new category name. New folders are added manually by the operator.

## Hard Rules (Non-Negotiable)

**NEVER access `documents.db` directly.** Do not read from it, write to it, or query it with SQL. All database writes happen inside `organizer.py` as a side-effect of `move_file`. The DB is an implementation detail — it is not a source of truth for what is in the inbox.

**NEVER call the Google Drive API directly** (not in inline Python, not via subprocess calls to anything other than `organizer.py`). All Drive operations go through `organizer.py` actions. No exceptions.

**NEVER look at the Unsortiert folder** unless the co-pilot explicitly asks about it. The Unsortiert folder is a legacy migration area, not the inbox. Sorting the inbox does not touch Unsortiert.

## Workflow: Organize Inbox

All Drive operations go through `organizer.py`. Call it via subprocess only:

```bash
python3 /workspace/project/.claude/skills/gdrive-document-organizer/organizer.py '<json_input>'
```

### Step 1 — List inbox (mandatory first action)

```json
{"action": "list_inbox"}
```

Returns: `{"files": [...], "count": N}`

**If `count == 0`:** Reply "Posteingang ist leer — keine neuen Dokumente." and STOP. Do not look at any other folder. Do not inspect `documents.db`. Do not do anything else.

**If `count > 0`:** Proceed to Step 2 with the exact list of files returned. The returned list is the complete work queue — do not add files from any other source.

### Step 2 — For each file: extract text

```json
{"action": "extract_text", "file_id": "...", "mime_type": "application/pdf", "size_bytes": 102400}
```

Returns one of:
- `{"status": "ok", "text": "..."}` → proceed to Step 3
- `{"status": "scanned_pdf"}` → skip, add to skipped list
- `{"status": "too_large"}` → skip, warn co-pilot
- `{"status": "unsupported"}` → skip, add to skipped list

### Step 3 — Classify (Bob's job — no organizer.py action)

From the extracted text, determine:
- `category`: one of `Eingangsrechnungen`, `Ausgangsrechnungen`, `Krankenkasse`, `Steuer`, `Verträge`, `Sonstiges`
- `summary`: 1–2 sentence description
- `key_fields`: structured metadata (e.g. `{"amount": "€240", "date": "2025-03-15", "sender": "AOK Bayern"}`)
- `tags`: 3–5 keywords for future search

The goal is LLM-retrievable metadata: a future query like "find 2025 tax documents" must resolve without re-reading the files.

If a file cannot be classified, use `Sonstiges` — never leave a classifiable file in the inbox because classification was uncertain.

### Step 4 — Move file and index it

```json
{
  "action": "move_file",
  "file_id": "...",
  "file_name": "AOK_Rechnung_März.pdf",
  "category": "Eingangsrechnungen",
  "summary": "AOK invoice for March 2025, €240",
  "key_fields": {"amount": "€240", "date": "2025-03-15", "sender": "AOK Bayern"},
  "tags": ["AOK", "2025", "Rechnung", "März"]
}
```

Returns: `{"status": "ok", "moved_to": "Eingangsrechnungen"}`

Repeat Steps 2–4 for every file in the Step 1 list.

### Step 5 — Verify inbox is empty

After processing all files, call `list_inbox` again:

```json
{"action": "list_inbox"}
```

- If `count == 0`: success, proceed to Step 6.
- If `count > 0`: something was missed. Report the remaining files by name in the summary with a warning. Do not silently ignore them.

### Step 6 — Report back

```
📁 3 Dokumente sortiert:

• AOK_Rechnung_März.pdf → Eingangsrechnungen (€240, 15.03.2025)
• Steuervorauszahlung_Q1.pdf → Steuer (€1.200, Q1 2025)
• Vertrag_Musterstraße.docx → Verträge

⚠ 1 Dokument übersprungen: Scan_unlesbar.pdf (gescanntes PDF, kein Text erkennbar)
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
- Raw file content is never stored on the VPS beyond the classification step
