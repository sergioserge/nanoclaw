---
name: physio-routing
description: Mobile Physio appointment management for Cologne. Three intents — Booking (address + time → ranked slots → create on "1"/"2"/"3" reply), List (date phrase → events for that range), Delete (patient name → confirm with full name → delete on "Ja" reply). Reads Google Calendar across all configured calendars; writes only to writeCalendarId.
---

# Physio Routing Skill

Operational skill for the Mobile Physio Optimization Agent in Cologne, Germany. Bob handles three intents: **Booking**, **List**, **Delete**.

## Credentials & Config

All files live at `/workspace/group/data/`:
- `credentials.json` — Google OAuth client credentials
- `token.json` — OAuth token (read/write calendar access)
- `config.json` — `writeCalendarId`, `readCalendarIds`, `homeCoords`, `timezone`
- `.env` — `GOOGLE_MAPS_API_KEY`
- `physio.db` — SQLite patient_mapping table (pseudonymization)

**Never** pass real patient names, addresses, or event descriptions to any LLM. Patient names and addresses may be written to Google Calendar (that is their intended store) but must never reach the Google Maps API or any other external service. Use `routing.py` for pseudonymization before any geocoding call.

Google Maps API key: read from `/workspace/group/data/.env` as `GOOGLE_MAPS_API_KEY`. If not set, routing.py skips distance calculation and returns slots based on calendar gaps only (degraded mode).

## Intent Classification

Determine the intent before executing any workflow:

| Signal in the message | Intent |
|---|---|
| Street address + time preference / day | Booking |
| "welche Termine", "Termine", "what appointments" + date phrase | List |
| "lösche", "entferne", "cancel", "absagen", "streichen" + patient name | Delete |
| Bare "1", "2", "3" after a slot suggestion in this session | Continue Booking confirmation |
| Bare "Ja", "Nein", or a number after a delete prompt in this session | Continue Delete confirmation |
| Bare "Ja", "Nein", "1", "2", "3" with **no** pending workflow in this session | Orphan confirmation — respond exactly: `Diese Antwort bezieht sich auf eine abgelaufene Anfrage — bitte erneut stellen.` and stop. Do NOT fall through to the general off-topic rejection. |

If both an address and list/delete keywords appear, prefer **Booking**. If a list message has no date phrase, ask back: `Für welchen Zeitraum?`

Examples per intent:
- Booking: "Neuer Patient, Bonner Str. 88, flexibel" / "Frau Müller, Aachener Str. 15, Donnerstag morgen"
- List: "Welche Termine habe ich morgen?" / "Termine nächste Woche" / "Was steht am 5. Mai an?"
- Delete: "Lösche Termin von Müller" / "Cancel Hans Schmidt" / "Bitte den Termin mit Frau Sachs absagen"

## Workflow: Booking Request

### 1. Parse
Extract address and time preference from the message. Default appointment duration: **60 min** — never ask for it, never prompt the co-pilot to confirm it.

**Start immediately.** As soon as an address is present, begin Steps 2–6 in parallel. If the patient name is missing, ask for it in a single short question while the calculation runs — do not wait for the answer before starting the geocoding and calendar fetch.

### 2. Load config
```python
import json
config = json.load(open('/workspace/group/data/config.json'))
write_calendar_id = config['writeCalendarId']
read_calendar_ids = config['readCalendarIds']
home_coords = config['homeCoords']
# Read Maps API key from .env
maps_api_key = ''
for line in open('/workspace/group/data/.env').read().splitlines():
    if line.startswith('GOOGLE_MAPS_API_KEY='):
        maps_api_key = line.split('=', 1)[1].strip()
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

def _fetch_day_events(cal_id):
    return service.events().list(
        calendarId=cal_id,
        timeMin=day_start_iso,   # e.g. "2026-04-22T00:00:00+02:00"
        timeMax=day_end_iso,
        singleEvents=True,
        orderBy='startTime'
    ).execute().get('items', [])

# Read events from each calendar in readCalendarIds and dedupe by event id.
# Bob's own bookings live on writeCalendarId; in prd, Christian's appointments and
# Verfügbar blocks come from the shared Therapeut Christian – Termine calendar (read-only).
events = []
seen_ids = set()
for cal_id in read_calendar_ids:
    for e in _fetch_day_events(cal_id):
        if e['id'] not in seen_ids:
            seen_ids.add(e['id'])
            events.append(e)
events.sort(key=lambda e: e['start'].get('dateTime', e['start'].get('date', '')))
```

### 4. Find Verfügbar block
```python
verfuegbar = [e for e in events if e.get('summary','').lower() == 'verfügbar']
if not verfuegbar:
    return "Kein verfügbarer Tag gefunden."
# Calendar API returns full ISO datetimes; routing.py expects "HH:MM"
window_start = verfuegbar[0]['start']['dateTime'][11:16]  # e.g. "2026-04-22T08:00:00+02:00" → "08:00"
window_end   = verfuegbar[0]['end']['dateTime'][11:16]
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
            'name':     e.get('summary', ''),   # patient name — for display only
            'location': location,
            'start': e['start']['dateTime'][11:16],  # "HH:MM"
            'end':   e['end']['dateTime'][11:16],
        })
```

### 6. Calculate route delta
Run `routing.py` via subprocess or import directly:
```bash
python3 /workspace/extra/physio-routing/routing.py '<json_input>'
```

Input JSON:
```json
{
  "address": "<new client address>",
  "day_iso": "2026-04-22",
  "stops": [{"name": "...", "location": "...", "start": "HH:MM", "end": "HH:MM"}],
  "window_start": "HH:MM",
  "window_end": "HH:MM",
  "home_coords": {"lat": 50.9333, "lng": 6.9500},
  "maps_api_key": "<GOOGLE_MAPS_API_KEY from .env or empty string>",
  "db_path": "/workspace/group/data/physio.db"
}
```

### 7. Present slots and wait for confirmation

Use this exact format:
```
Slot 1: Do. 14.05. 15:10–16:10 | +2 min | Köln-Süd
  Nach Rolf Harbach (endet 14:55), danach frei bis 18:00

Slot 2: Do. 14.05. 12:27–13:27 | +3 min | Köln-Süd
  Nach Fabricius (endet 12:15), vor Rolf Harbach (ab 14:00)

Slot 3: Di. 12.05. 11:58–12:58 | +20 min | Köln-Süd
  Nach Bernd Fabricius (endet 11:45), vor Susanne Sachs (ab 13:30)

⚠ Hinweis: Montag 08:15 würde +71 min Fahrzeit bedeuten. Nicht empfohlen.

Wie heißt der Patient, und welchen Slot (1, 2 oder 3)?
```

Rules:
- **Time format:** `<Tag-Kurzform>. <DD.MM.> <HH:MM>–<HH:MM>` (e.g. `Do. 14.05. 15:10–16:10`). Always include day-of-week + date together, and the full time range — never just a start time.
- **Context sub-line** (indented two spaces under each slot, derived from the events list in Step 5):
  - `Nach <prev_name> (endet <HH:MM>), vor <next_name> (ab <HH:MM>)` — both surrounding appointments exist
  - `Nach <prev_name> (endet <HH:MM>), danach frei bis <HH:MM>` — no next appointment until Verfügbar window ends
  - `Vor <next_name> (ab <HH:MM>), davor frei ab <HH:MM>` — slot is the first appointment of the day
  - Omit the sub-line only if the day has zero other events.
- **Cluster label** appears bare (e.g. `Köln-Süd`) — no `Cluster:` prefix, no ✓ checkmark. If no cluster match, write `Kein Cluster-Match` instead.
- Show top 1–3 slots sorted by delta ascending. Aim for at least 2 whenever the calendar allows.
- Add ⚠ flag line above the closing question if any slot exceeds 60 min delta or includes a Rhine-crossing penalty.
- **Always flag routing violations** (Rhine crossing penalty, cluster mismatch) — even if the co-pilot chooses that slot anyway. Never silently accept an override.
- If maps_api_key is missing, note "Routenberechnung ohne Verkehrsdaten (kein API-Key)"
- **Closing question:** always exactly `Wie heißt der Patient, und welchen Slot (1, 2 oder 3)?` — asks for both at once.
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

service.events().insert(calendarId=config['writeCalendarId'], body={
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

## Workflow: List Appointments

Activate when the user asks for appointments in a date range.

### 1. Resolve the date range deterministically

Use `dateparser` — never compute dates yourself. Anchor on Europe/Berlin "today".

```python
import dateparser
from datetime import datetime, timedelta
import pytz

berlin = pytz.timezone('Europe/Berlin')
now = datetime.now(berlin)

phrase = '<extracted_phrase>'  # exact quote from user, e.g. "morgen", "nächste Woche", "5. Mai"

parsed = dateparser.parse(phrase, languages=['de', 'en'], settings={
    'TIMEZONE': 'Europe/Berlin',
    'RETURN_AS_TIMEZONE_AWARE': True,
    'PREFER_DATES_FROM': 'future',
    'RELATIVE_BASE': now,
})
```

Range conventions:
- Single-day phrases ("morgen", "5. Mai") → start = 00:00, end = 23:59 of that day
- Week phrases ("diese Woche", "nächste Woche") → Mon 00:00 to Sun 23:59 of that ISO week
- Range phrases ("morgen bis Freitag", "5. Mai bis 12. Mai") → split on "bis"/"und", parse each side

dateparser returns a single point datetime. Derive the range deterministically:

```python
from datetime import datetime, time, timedelta

def day_bounds(d, tz):
    return tz.localize(datetime.combine(d, time.min)), tz.localize(datetime.combine(d, time.max))

# Single-day phrase
start_dt, end_dt = day_bounds(parsed.date(), berlin)

# Week phrase ("diese Woche", "nächste Woche") — dateparser gives ANY date inside the target week.
# Snap to Mon-Sun of that ISO week:
ref = parsed.date()
mon = ref - timedelta(days=ref.weekday())  # Monday of same ISO week
sun = mon + timedelta(days=6)
start_dt, _ = day_bounds(mon, berlin)
_, end_dt   = day_bounds(sun, berlin)

# Range phrase: parse each side separately, take start of the earlier and end of the later
```

If unparseable: respond `Konnte den Zeitraum '<phrase>' nicht verstehen. Bitte präziser.` and stop.
If no date phrase at all in the message: respond `Für welchen Zeitraum?` and stop.

### 2. Fetch events across all read calendars (dedup by event id)

```python
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

config = json.load(open('/workspace/group/data/config.json'))
token = json.load(open('/workspace/group/data/token.json'))
creds = Credentials(
    token=token['token'], refresh_token=token['refresh_token'],
    token_uri=token['token_uri'], client_id=token['client_id'],
    client_secret=token['client_secret'], scopes=token['scopes'],
)
service = build('calendar', 'v3', credentials=creds)

events = []
seen = set()
for cal_id in config['readCalendarIds']:
    items = service.events().list(
        calendarId=cal_id,
        timeMin=start_dt.isoformat(),
        timeMax=end_dt.isoformat(),
        singleEvents=True, orderBy='startTime',
    ).execute().get('items', [])
    for e in items:
        if e['id'] in seen:
            continue
        seen.add(e['id'])
        # Strip description IMMEDIATELY — never read, log, or pass it onward (P3 GDPR).
        events.append({
            'id': e['id'],
            'summary':  e.get('summary', ''),
            'location': e.get('location', ''),
            'start':    e['start'].get('dateTime', e['start'].get('date', '')),
            'end':      e['end'].get('dateTime',   e['end'].get('date', '')),
        })

events.sort(key=lambda e: e['start'])
events = [e for e in events if e['summary'].lower() != 'verfügbar']  # skip booking-window markers
```

### 3. Format the output

Cap at 20 events. Always echo the resolved date range in the header so misparsing is visible.

Single-day:
```
Termine am <Tag>, <DD.MM.YYYY>:

1. <Patient Name> — <HH:MM>–<HH:MM> — <Location>
2. <Patient Name> — <HH:MM>–<HH:MM> — <Location>
```

Range:
```
Termine vom <Tag>, <DD.MM.YYYY> bis <Tag>, <DD.MM.YYYY>:

1. <Patient Name> — <Tag>. <DD.MM.> <HH:MM>–<HH:MM> — <Location>
2. <Patient Name> — <Tag>. <DD.MM.> <HH:MM>–<HH:MM> — <Location>
```

If no events: `Keine Termine im Zeitraum vom <start> bis <end>.`
If more than 20: append `…und <X> weitere. Bitte präziser fragen.`

## Workflow: Delete Appointment

Activate when the user asks to delete a named appointment.

### 1. Extract the name fragment

The user supplies first, last, or both — partial match OK ("Müller", "Max", "Max Müller", "Frau Sachs"). Strip honorifics ("Frau", "Herr", "Dr.").

### 2. Search the writable calendar within ±30 days

Search ONLY `writeCalendarId` — Bob refuses to delete from read-only calendars (Christian's personal entries are off-limits).

```python
import json
from datetime import datetime, timedelta
import pytz
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

config = json.load(open('/workspace/group/data/config.json'))
token = json.load(open('/workspace/group/data/token.json'))
creds = Credentials(
    token=token['token'], refresh_token=token['refresh_token'],
    token_uri=token['token_uri'], client_id=token['client_id'],
    client_secret=token['client_secret'], scopes=token['scopes'],
)
service = build('calendar', 'v3', credentials=creds)

berlin = pytz.timezone('Europe/Berlin')
now = datetime.now(berlin)

name_query = '<extracted_name>'  # e.g. "Müller"

items = service.events().list(
    calendarId=config['writeCalendarId'],
    q=name_query,                                       # server-side full-text search
    timeMin=(now - timedelta(days=30)).isoformat(),
    timeMax=(now + timedelta(days=30)).isoformat(),
    singleEvents=True, orderBy='startTime',
).execute().get('items', [])

# `q` matches description too — re-filter on summary only.
matches = []
for e in items:
    if name_query.lower() not in e.get('summary', '').lower():
        continue
    matches.append({
        'id':       e['id'],
        'summary':  e.get('summary', ''),
        'location': e.get('location', ''),
        'start':    e['start'].get('dateTime', ''),
        'end':      e['end'].get('dateTime', ''),
    })
# Never store or forward e['description'] — discard immediately (P3 GDPR).
```

If the user mentioned a date hint ("im März", "letzte Woche"), parse that with `dateparser` first and override the ±30 day window with the resolved range.

### 3. Branch on match count

**0 matches:**
```
Keinen Termin für '<name>' gefunden im Zeitraum ±30 Tage. Falls weiter zurück oder voraus liegt, bitte mit Datum fragen ("lösche Termin von Müller im März").
```
Stop.

**1 match:** echo the full identity and ask for explicit confirmation:
```
Termin gefunden: <Full Name> am <Tag>, <DD.MM.YYYY> um <HH:MM>–<HH:MM> in <Location>. Löschen? Antworte 'Ja' oder 'Nein'.
```
Wait for the next message.

**2+ matches:** numbered list, ask for selection:
```
Mehrere Termine gefunden für '<name>':

1. <Full Name> — <Tag>, <DD.MM.> <HH:MM> — <Location>
2. <Full Name> — <Tag>, <DD.MM.> <HH:MM> — <Location>
...

Welcher? (1, 2, …)
```
On the user's reply with a number, treat as a single match and present the confirmation prompt as above. If more than 20 matches, cap and append `…und <X> weitere. Bitte präziser fragen.`

### 4. Apply confirmation

Wait for explicit `Ja` (case-insensitive, also `ja`, `yes`) in the next message of the same session. Anything else → abort:
```
Löschung abgebrochen. Sag mir Bescheid, wenn ich es löschen soll.
```

If the session has timed out (~10 min idle) and the user replies "Ja" later, the pending state is gone — Bob has no context to act on. Re-issue the delete command.

### 5. Delete

```python
service.events().delete(
    calendarId=config['writeCalendarId'],
    eventId=event_id_to_delete,
).execute()
```

Confirm: `Termin von <Full Name> gelöscht.`

If the API returns an error (event already deleted, network failure):
```
Löschen fehlgeschlagen: <error>. Bitte erneut versuchen.
```

## GDPR Rules (non-negotiable)
- Patient names (event summaries) may appear in the slot output shown to the co-pilot — this is intentional. They must NEVER be passed to Google Maps API or any other external service.
- `event['description']` is read locally only — never passed to any API or LLM
- patient_mapping in physio.db is the only persistent store for address data
- All geocoding uses the pseudonymized patient_id as the reference label in logs
- **Google Maps API receives coordinates only** — never raw addresses or patient names. `routing.py` handles the address→coordinates conversion locally before any Maps API call.
