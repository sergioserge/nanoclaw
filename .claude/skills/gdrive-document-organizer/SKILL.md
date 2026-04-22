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

## Workflow: Organize Inbox

### 1–5. Run organizer.py

All Drive operations are handled by `organizer.py`. Call it via subprocess:

```bash
python3 /workspace/project/.claude/skills/gdrive-document-organizer/organizer.py '<json_input>'
```

**List inbox:**
```json
{"action": "list_inbox"}
```
Returns: `{"files": [...], "count": N}`

**Extract text from a file:**
```json
{"action": "extract_text", "file_id": "...", "mime_type": "application/pdf", "size_bytes": 102400}
```
Returns: `{"status": "ok", "text": "..."}` or `{"status": "scanned_pdf"}` / `{"status": "too_large"}` / `{"status": "unsupported"}`

**Classify (Bob's job — not organizer.py):**
After receiving the extracted text, Bob classifies the document and determines:
- `category`: one of `Eingangsrechnungen`, `Ausgangsrechnungen`, `Krankenkasse`, `Steuer`, `Verträge`, `Sonstiges`
- `summary`: 1–2 sentence description
- `key_fields`: structured data relevant to the document type (e.g. `{"amount": "€240", "date": "2025-03-15", "sender": "AOK Bayern"}`)
- `tags`: 3–5 keywords for future search (e.g. `["AOK", "2025", "Rechnung"]`)

The goal is LLM-retrievable metadata: a future query like "find 2025 tax documents" must resolve without re-reading the files.

**Move file and index it:**
```json
{
  "action": "move_file",
  "file_id": "...",
  "file_name": "AOK_Rechnung_März.pdf",
  "category": "Rechnungen",
  "summary": "AOK invoice for March 2025, €240",
  "key_fields": {"amount": "€240", "date": "2025-03-15", "sender": "AOK Bayern"},
  "tags": ["AOK", "2025", "Rechnung", "März"]
}
```
Returns: `{"status": "ok", "moved_to": "Rechnungen"}`

### 6. Report back

After processing all inbox files:

```
📁 3 Dokumente sortiert:

• AOK_Rechnung_März.pdf → Rechnungen (€240, 15.03.2025)
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
