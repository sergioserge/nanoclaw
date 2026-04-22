---
name: physio-routing
description: Mobile Physio booking optimization for Cologne. Activates when the co-pilot sends a new client address with a time preference. Reads the Google Calendar, calculates travel-efficient appointment slots, and returns ranked suggestions. Also handles creating calendar events when asked.
---

# Physio Routing Skill

Operational skill for the Mobile Physio Optimization Agent in Cologne, Germany.

## Credentials & Config

All files live at `/workspace/group/data/`:
- `credentials.json` — Google OAuth client credentials
- `token.json` — OAuth token (read/write calendar access)
- `config.json` — `calendarId`, `homeCoords`, `timezone`
- `physio.db` — SQLite patient_mapping table (pseudonymization)

**Never** pass real patient names, addresses, or event descriptions to any LLM. Patient names and addresses may be written to Google Calendar (that is their intended store) but must never reach the Google Maps API or any other external service. Use `routing.py` for pseudonymization before any geocoding call.

Google Maps API key: read from `.env` as `GOOGLE_MAPS_API_KEY`. If not set, skip distance calculation and return slots based on calendar gaps only (degraded mode).

## Trigger

Activate when a message contains a street address (in Cologne) plus a time preference or day of week.

Examples:
- "New client: Venloer Str. 42, Tuesday preferred"
- "Neuer Patient, Bonner Str. 88, flexibel"
- "Frau Müller, Aachener Str. 15, Donnerstag morgen"
- "Patient hinzufügen: Ehrenfelder Str. 10, nächste Woche"

## Workflow: Booking Request

### 1. Parse
Extract address and time preference from the message. Default appointment duration: **60 min** — never ask for it, never prompt the co-pilot to confirm it.

**Start immediately.** As soon as an address is present, begin Steps 2–6 in parallel. If the patient name is missing, ask for it in a single short question while the calculation runs — do not wait for the answer before starting the geocoding and calendar fetch.

### 2. Load config
```python
import json
config = json.load(open('/workspace/group/data/config.json'))
calendar_id = config['calendarId']
home_coords = config['homeCoords']
```

### 3. Fetch Calendar for target day
```python
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import json

token = json.load(open('/workspace/group/data/token.json'))
creds = Credentials(
    token=token['token'],
    refresh_token=token['refresh_token'],
    token_uri=token['token_uri'],
    client_id=token['client_id'],
    client_secret=token['client_secret'],
    scopes=token['scopes'],
)
service = build('calendar', 'v3', credentials=creds)

events = service.events().list(
    calendarId=calendar_id,
    timeMin=day_start_iso,   # e.g. "2026-04-22T00:00:00+02:00"
    timeMax=day_end_iso,
    singleEvents=True,
    orderBy='startTime'
).execute()['items']
```

### 4. Find Verfügbar block
```python
verfuegbar = [e for e in events if e.get('summary','').lower() == 'verfügbar']
if not verfuegbar:
    return "Kein verfügbarer Tag gefunden."
window_start = verfuegbar[0]['start']['dateTime']
window_end   = verfuegbar[0]['end']['dateTime']
```

### 5. Extract stops (NEVER read description field)
```python
stops = []
for e in events:
    if e.get('summary','').lower() == 'verfügbar':
        continue
    # Extract only what routing needs — never touch e['description']
    location = e.get('location', '')
    if location:
        stops.append({
            'location': location,
            'start': e['start']['dateTime'],
            'end':   e['end']['dateTime'],
        })
```

### 6. Calculate route delta
Run `routing.py` via subprocess or import directly:
```bash
python3 /workspace/project/.claude/skills/physio-routing/routing.py '<json_input>'
```

Input JSON:
```json
{
  "address": "<new client address>",
  "day_iso": "2026-04-22",
  "stops": [{"location": "...", "start": "HH:MM", "end": "HH:MM"}],
  "window_start": "HH:MM",
  "window_end": "HH:MM",
  "home_coords": {"lat": 50.9333, "lng": 6.9500},
  "maps_api_key": "<from env or empty string>",
  "db_path": "/workspace/group/data/physio.db"
}
```

### 7. Present slots and wait for confirmation

Use this exact format:
```
Slot 1: Dienstag 09:30 | +12 min Fahrzeit | Cluster: Köln-West ✓
Slot 2: Dienstag 14:00 | +28 min Fahrzeit | Kein Cluster-Match
Slot 3: Mittwoch 10:00 | +8 min Fahrzeit  | Cluster: Köln-West ✓

⚠ Hinweis: Montag 08:15 würde +71 min Fahrzeit bedeuten. Nicht empfohlen.

Welchen Slot möchtest du buchen? (1, 2 oder 3)
```

Rules:
- Show top 1–3 slots sorted by delta ascending. Aim for at least 2 whenever the calendar allows.
- Add ✓ if cluster_match is true
- Add ⚠ flag line if any slot exceeds 60 min delta
- **Always flag routing violations** (Rhine crossing penalty, cluster mismatch) — even if the co-pilot chooses that slot anyway. State the cost explicitly (e.g. "+25 min Brückenstrafe"). Never silently accept an override.
- If maps_api_key is missing, note "Routenberechnung ohne Verkehrsdaten (kein API-Key)"
- **NEVER create the calendar event here.** Stop and wait for the co-pilot to reply "1", "2", or "3".

## Workflow: Confirm and Create Event

Activate when the co-pilot replies with "1", "2", or "3" immediately after a slot suggestion in the same session.

### 1. Identify the chosen slot
Match the reply to the slot presented in the previous message (use session context).

### 2. Load credentials
```python
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

config = json.load(open('/workspace/group/data/config.json'))
token = json.load(open('/workspace/group/data/token.json'))
creds = Credentials(
    token=token['token'],
    refresh_token=token['refresh_token'],
    token_uri=token['token_uri'],
    client_id=token['client_id'],
    client_secret=token['client_secret'],
    scopes=token['scopes'],
)
service = build('calendar', 'v3', credentials=creds)
```

### 3. Create the event
End time = start time + 60 min (default duration — always, unless co-pilot explicitly stated otherwise).

```python
from datetime import datetime, timedelta

start_dt = datetime.fromisoformat(chosen_slot_start_iso)
end_dt = start_dt + timedelta(minutes=60)

service.events().insert(calendarId=config['calendarId'], body={
    'summary':  '<patient name>',
    'location': '<patient address>',
    'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Europe/Berlin'},
    'end':   {'dateTime': end_dt.isoformat(),   'timeZone': 'Europe/Berlin'},
}).execute()
```

### 4. Confirm back
```
✅ Termin eingetragen: <Name>, <Datum> <Uhrzeit>–<Endzeit>
```

## Installing Python dependencies

If google-api-python-client is not available in the container, install it:
```bash
pip install --quiet google-api-python-client google-auth requests
```

## GDPR Rules (non-negotiable)
- NEVER log, store, or forward real patient names or addresses outside the local DB
- `event['description']` is read locally only — never passed to any API or LLM
- patient_mapping in physio.db is the only persistent store for address data
- All geocoding uses the pseudonymized patient_id as the reference label in logs
- **Google Maps API receives coordinates only** — never raw addresses or patient names. `routing.py` handles the address→coordinates conversion locally before any Maps API call.
