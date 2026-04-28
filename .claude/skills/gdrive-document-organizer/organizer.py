#!/usr/bin/env python3
"""
Drive document organizer. Called by Bob via subprocess with a JSON argument.
Returns JSON to stdout.

Actions:
  setup_drive       — create default folder structure and write config.json (run once)
  list_folders      — list current category folders from Drive (live, excludes Inbox/Unsortiert)
  ensure_unsortiert — verify Unsortiert exists; recreate under rootFolderId if deleted
  list_inbox        — list files in the inbox folder
  extract_text      — download a file and extract its text
  move_file         — move file to a category folder (by folder_id) and index it
  move_unsortiert   — move file to Unsortiert folder
  search            — query the document index

Usage:
  python3 organizer.py '<json_input>'
"""

import sys
import json
import io
import sqlite3
from pathlib import Path

DATA_DIR = '/workspace/group/data'

DEFAULT_CATEGORY_FOLDERS = [
    'Eingangsrechnungen',
    'Ausgangsrechnungen',
    'Krankenkasse',
    'Steuer',
    'Verträge',
    'Sonstiges',
]


# ── Config helpers ────────────────────────────────────────────────────────────

def _load_config(data_dir):
    with open(f'{data_dir}/config.json') as f:
        return json.load(f)


def _save_config(data_dir, config):
    with open(f'{data_dir}/config.json', 'w') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# ── Drive helpers ─────────────────────────────────────────────────────────────

def load_drive_service(data_dir):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    with open(f'{data_dir}/token.json') as f:
        token = json.load(f)
    creds = Credentials(
        token=token['token'],
        refresh_token=token['refresh_token'],
        token_uri=token['token_uri'],
        client_id=token['client_id'],
        client_secret=token['client_secret'],
        scopes=token['scopes'],
    )
    return build('drive', 'v3', credentials=creds)


def _create_folder(service, name, parent_id):
    """Create a Drive folder under parent_id. Returns the new folder ID."""
    metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id],
    }
    return service.files().create(body=metadata, fields='id').execute()['id']


def _folder_exists(service, folder_id):
    """Return True if the folder exists in Drive and is not trashed."""
    try:
        f = service.files().get(fileId=folder_id, fields='id,trashed').execute()
        return not f.get('trashed', False)
    except Exception:
        return False


def _get_root_id(service, config, data_dir):
    """
    Return rootFolderId. If absent from config, discover it by reading the
    parent of inboxFolderId and persist it to config.json (one-time migration).
    """
    root_id = config.get('rootFolderId')
    if root_id:
        return root_id
    f = service.files().get(fileId=config['inboxFolderId'], fields='parents').execute()
    root_id = f['parents'][0]
    config['rootFolderId'] = root_id
    _save_config(data_dir, config)
    return root_id


def _move_in_drive(service, file_id, from_folder_id, to_folder_id):
    service.files().update(
        fileId=file_id,
        addParents=to_folder_id,
        removeParents=from_folder_id,
        fields='id, parents',
    ).execute()


# ── Staging helpers (full text never sent to Bob — stored locally only) ───────

def _stage_full_text(file_id, full_text, db_path):
    conn = sqlite3.connect(db_path)
    conn.execute('''CREATE TABLE IF NOT EXISTS _staging (
        file_id TEXT PRIMARY KEY,
        full_text TEXT,
        created_at TEXT
    )''')
    conn.execute(
        "INSERT OR REPLACE INTO _staging VALUES (?, ?, datetime('now'))",
        (file_id, full_text)
    )
    conn.commit()
    conn.close()


def _retrieve_staged_text(file_id, db_path):
    if not Path(db_path).exists():
        return ''
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        'SELECT full_text FROM _staging WHERE file_id = ?', (file_id,)
    ).fetchone()
    conn.execute('DELETE FROM _staging WHERE file_id = ?', (file_id,))
    conn.commit()
    conn.close()
    return row[0] if row else ''


# ── Actions ───────────────────────────────────────────────────────────────────

def setup_drive(inp, data_dir):
    """
    Create the complete folder structure in Drive and write a fresh config.json.
    Run once per new installation. Safe to re-run — creates new folders each time,
    so only call it when setting up from scratch.
    """
    service = load_drive_service(data_dir)
    root_name = inp.get('root_name', 'Document Organizer')
    timezone = inp.get('timezone', 'Europe/Berlin')

    root_id = _create_folder(service, root_name, 'root')
    inbox_id = _create_folder(service, 'Inbox', root_id)
    unsortiert_id = _create_folder(service, 'Unsortiert', root_id)

    for name in DEFAULT_CATEGORY_FOLDERS:
        _create_folder(service, name, root_id)

    config = {
        'rootFolderId': root_id,
        'inboxFolderId': inbox_id,
        'unsortiertFolderId': unsortiert_id,
        'timezone': timezone,
        'maxFileSizeBytes': 20 * 1024 * 1024,
    }
    _save_config(data_dir, config)
    return {'status': 'ok', 'root_name': root_name, 'config': config}


def list_folders(inp, data_dir):
    """
    List current category folders under rootFolderId.
    Excludes Inbox and Unsortiert. Always reads live from Drive.
    """
    service = load_drive_service(data_dir)
    config = _load_config(data_dir)
    root_id = _get_root_id(service, config, data_dir)

    excluded = {config['inboxFolderId'], config.get('unsortiertFolderId', '')}

    resp = service.files().list(
        q=(
            f"'{root_id}' in parents"
            " and mimeType='application/vnd.google-apps.folder'"
            " and trashed=false"
        ),
        fields='files(id, name)',
        orderBy='name',
    ).execute()

    folders = [
        {'id': f['id'], 'name': f['name']}
        for f in resp.get('files', [])
        if f['id'] not in excluded
    ]
    return {'folders': folders}


def ensure_unsortiert(inp, data_dir):
    """
    Verify the Unsortiert folder still exists in Drive.
    If it was deleted, recreate it under rootFolderId and update config.json.
    """
    service = load_drive_service(data_dir)
    config = _load_config(data_dir)
    unsortiert_id = config.get('unsortiertFolderId')

    if unsortiert_id and _folder_exists(service, unsortiert_id):
        return {'folder_id': unsortiert_id, 'created': False}

    root_id = _get_root_id(service, config, data_dir)
    new_id = _create_folder(service, 'Unsortiert', root_id)
    config['unsortiertFolderId'] = new_id
    _save_config(data_dir, config)
    return {'folder_id': new_id, 'created': True}


def list_inbox(inp, data_dir):
    with open(f'{data_dir}/config.json') as f:
        config = json.load(f)
    service = load_drive_service(data_dir)

    files = []
    page_token = None
    while True:
        kwargs = dict(
            q=f"'{config['inboxFolderId']}' in parents and trashed=false",
            fields='nextPageToken, files(id, name, mimeType, size)',
            orderBy='createdTime',
            pageSize=100,
        )
        if page_token:
            kwargs['pageToken'] = page_token
        resp = service.files().list(**kwargs).execute()
        files.extend(resp.get('files', []))
        page_token = resp.get('nextPageToken')
        if not page_token:
            break

    return {'files': files, 'count': len(files)}


def extract_text(inp, data_dir):
    with open(f'{data_dir}/config.json') as f:
        config = json.load(f)
    service = load_drive_service(data_dir)

    file_id = inp['file_id']
    mime_type = inp['mime_type']
    size_bytes = int(inp.get('size_bytes', 0))
    max_size = config.get('maxFileSizeBytes', 20 * 1024 * 1024)

    if size_bytes > max_size:
        return {'status': 'too_large', 'size_mb': round(size_bytes / 1024 / 1024, 1)}

    content = service.files().get_media(fileId=file_id).execute()

    db_path = f'{data_dir}/documents.db'
    file_id = inp['file_id']

    if mime_type == 'application/pdf':
        try:
            import fitz
            doc = fitz.open(stream=io.BytesIO(content), filetype='pdf')
            text = '\n'.join(page.get_text() for page in doc)
            if not text.strip():
                return {'status': 'scanned_pdf', 'text': None}
            _stage_full_text(file_id, text, db_path)
            return {'status': 'ok', 'text': text[:4000]}
        except Exception as e:
            return {'status': 'error', 'error': str(e)}

    if mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        try:
            import docx
            doc = docx.Document(io.BytesIO(content))
            text = '\n'.join(p.text for p in doc.paragraphs if p.text.strip())
            _stage_full_text(file_id, text, db_path)
            return {'status': 'ok', 'text': text[:4000]}
        except Exception as e:
            return {'status': 'error', 'error': str(e)}

    if mime_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            rows = []
            for sheet in wb.worksheets:
                for row in sheet.iter_rows(values_only=True):
                    row_str = '\t'.join(str(c) if c is not None else '' for c in row)
                    if row_str.strip():
                        rows.append(row_str)
            text = '\n'.join(rows)
            _stage_full_text(file_id, text, db_path)
            return {'status': 'ok', 'text': text[:4000]}
        except Exception as e:
            return {'status': 'error', 'error': str(e)}

    if mime_type == 'text/csv':
        try:
            text = content.decode('utf-8', errors='replace')
            _stage_full_text(file_id, text, db_path)
            return {'status': 'ok', 'text': text[:4000]}
        except Exception as e:
            return {'status': 'error', 'error': str(e)}

    return {'status': 'unsupported', 'mime_type': mime_type}


def move_file(inp, data_dir):
    """
    Move a file from Inbox to a category folder and index it in documents.db.
    folder_id and folder_name come from the list_folders response — not from
    a hardcoded config list.
    """
    with open(f'{data_dir}/config.json') as f:
        config = json.load(f)
    service = load_drive_service(data_dir)

    file_id = inp['file_id']
    file_name = inp['file_name']
    folder_id = inp['folder_id']
    folder_name = inp['folder_name']
    summary = inp.get('summary', '')
    key_fields = inp.get('key_fields', {})
    tags = inp.get('tags', [])
    full_text = _retrieve_staged_text(file_id, f'{data_dir}/documents.db')

    _move_in_drive(service, file_id, config['inboxFolderId'], folder_id)

    db_path = f'{data_dir}/documents.db'
    conn = sqlite3.connect(db_path)
    conn.execute('''CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        name TEXT,
        category TEXT,
        summary TEXT,
        key_fields TEXT,
        tags TEXT,
        full_text TEXT,
        indexed_at TEXT
        -- future: vector BLOB for semantic search via sqlite-vec
    )''')
    # migration: add full_text column to existing DBs (idempotent)
    try:
        conn.execute('ALTER TABLE documents ADD COLUMN full_text TEXT')
    except Exception:
        pass
    conn.execute(
        "INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        (file_id, file_name, folder_name, summary,
         json.dumps(key_fields, ensure_ascii=False),
         json.dumps(tags, ensure_ascii=False),
         full_text)
    )
    conn.commit()
    conn.close()

    return {'status': 'ok', 'file_id': file_id, 'moved_to': folder_name}


def move_unsortiert(inp, data_dir):
    with open(f'{data_dir}/config.json') as f:
        config = json.load(f)
    service = load_drive_service(data_dir)

    file_id = inp['file_id']
    reason = inp.get('reason', 'unknown')

    unsortiert_id = config.get('unsortiertFolderId')
    if not unsortiert_id:
        return {'status': 'error', 'error': 'unsortiertFolderId not set — run ensure_unsortiert first'}

    _move_in_drive(service, file_id, config['inboxFolderId'], unsortiert_id)
    return {'status': 'ok', 'file_id': file_id, 'moved_to': 'Unsortiert', 'reason': reason}


def search(inp, data_dir):
    query = inp.get('query', '').lower()
    db_path = f'{data_dir}/documents.db'

    if not Path(db_path).exists():
        return {'results': [], 'note': 'No documents indexed yet'}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    pattern = f'%{query}%'
    rows = conn.execute('''
        SELECT name, category, summary, key_fields, tags, indexed_at
        FROM documents
        WHERE lower(name) LIKE ?
           OR lower(summary) LIKE ?
           OR lower(tags) LIKE ?
           OR lower(key_fields) LIKE ?
           OR lower(coalesce(full_text, '')) LIKE ?
        ORDER BY indexed_at DESC
        LIMIT 20
    ''', (pattern, pattern, pattern, pattern, pattern)).fetchall()
    conn.close()

    return {'results': [dict(r) for r in rows], 'count': len(rows)}


def main():
    inp = json.loads(sys.argv[1])
    data_dir = inp.get('data_dir', DATA_DIR)
    action = inp.get('action')

    dispatch = {
        'setup_drive':       setup_drive,
        'list_folders':      list_folders,
        'ensure_unsortiert': ensure_unsortiert,
        'list_inbox':        list_inbox,
        'extract_text':      extract_text,
        'move_file':         move_file,
        'move_unsortiert':   move_unsortiert,
        'search':            search,
    }

    if action not in dispatch:
        print(json.dumps({'error': f'Unknown action: {action}. Valid: {list(dispatch)}'}))
        sys.exit(1)

    result = dispatch[action](inp, data_dir)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
