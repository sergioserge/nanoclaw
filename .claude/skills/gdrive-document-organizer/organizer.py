#!/usr/bin/env python3
"""
Drive document organizer. Called by Bob via subprocess with a JSON argument.
Returns JSON to stdout.

Actions:
  list_inbox     — list files in the inbox folder
  extract_text   — download a file and extract its text
  move_file      — move file to category subfolder and index it
  search         — query the document index

Usage:
  python3 organizer.py '<json_input>'
"""

import sys
import json
import io
import os
import sqlite3
from pathlib import Path

DATA_DIR = '/workspace/group/data'


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


def resolve_category_folder(config, category):
    categories = config.get('categories', {})
    if category not in categories:
        valid = list(categories.keys())
        raise ValueError(f"Unknown category '{category}'. Valid: {valid}")
    return categories[category]


def _move_in_drive(service, file_id, from_folder_id, to_folder_id):
    service.files().update(
        fileId=file_id,
        addParents=to_folder_id,
        removeParents=from_folder_id,
        fields='id, parents',
    ).execute()


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

    if mime_type == 'application/pdf':
        try:
            import fitz
            doc = fitz.open(stream=io.BytesIO(content), filetype='pdf')
            text = '\n'.join(page.get_text() for page in doc)
            if not text.strip():
                return {'status': 'scanned_pdf', 'text': None}
            return {'status': 'ok', 'text': text[:8000]}  # cap for LLM context
        except Exception as e:
            return {'status': 'error', 'error': str(e)}

    if mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        try:
            import docx
            doc = docx.Document(io.BytesIO(content))
            text = '\n'.join(p.text for p in doc.paragraphs if p.text.strip())
            return {'status': 'ok', 'text': text[:8000]}
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
            return {'status': 'ok', 'text': '\n'.join(rows)[:8000]}
        except Exception as e:
            return {'status': 'error', 'error': str(e)}

    if mime_type == 'text/csv':
        try:
            text = content.decode('utf-8', errors='replace')
            return {'status': 'ok', 'text': text[:8000]}
        except Exception as e:
            return {'status': 'error', 'error': str(e)}

    return {'status': 'unsupported', 'mime_type': mime_type}


def move_file(inp, data_dir):
    with open(f'{data_dir}/config.json') as f:
        config = json.load(f)
    service = load_drive_service(data_dir)

    file_id = inp['file_id']
    file_name = inp['file_name']
    category = inp['category']
    summary = inp.get('summary', '')
    key_fields = inp.get('key_fields', {})
    tags = inp.get('tags', [])

    target_folder_id = resolve_category_folder(config, category)
    _move_in_drive(service, file_id, config['inboxFolderId'], target_folder_id)

    db_path = f'{data_dir}/documents.db'
    conn = sqlite3.connect(db_path)
    conn.execute('''CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        name TEXT,
        category TEXT,
        summary TEXT,
        key_fields TEXT,
        tags TEXT,
        indexed_at TEXT
    )''')
    conn.execute(
        "INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
        (file_id, file_name, category, summary,
         json.dumps(key_fields, ensure_ascii=False),
         json.dumps(tags, ensure_ascii=False))
    )
    conn.commit()
    conn.close()

    return {'status': 'ok', 'file_id': file_id, 'moved_to': category}


def move_unsortiert(inp, data_dir):
    with open(f'{data_dir}/config.json') as f:
        config = json.load(f)
    service = load_drive_service(data_dir)

    file_id = inp['file_id']
    reason = inp.get('reason', 'unknown')

    unsortiert_id = config.get('unsortiertFolderId')
    if not unsortiert_id:
        return {'status': 'error', 'error': 'unsortiertFolderId not set in config.json'}

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
        ORDER BY indexed_at DESC
        LIMIT 20
    ''', (pattern, pattern, pattern, pattern)).fetchall()
    conn.close()

    return {'results': [dict(r) for r in rows], 'count': len(rows)}


def main():
    inp = json.loads(sys.argv[1])
    data_dir = inp.get('data_dir', DATA_DIR)
    action = inp.get('action')

    dispatch = {
        'list_inbox':       list_inbox,
        'extract_text':     extract_text,
        'move_file':        move_file,
        'move_unsortiert':  move_unsortiert,
        'search':           search,
    }

    if action not in dispatch:
        print(json.dumps({'error': f'Unknown action: {action}. Valid: {list(dispatch)}'}))
        sys.exit(1)

    result = dispatch[action](inp, data_dir)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
