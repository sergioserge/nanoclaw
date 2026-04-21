#!/usr/bin/env python3
"""
VRP math engine for Mobile Physio Optimization Agent — Cologne, Germany.
All constants are hard-coded per the deployment spec (non-configurable).
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from typing import Optional

import requests

# ── Constants (Cologne deployment — do not make configurable) ─────────────────

BRIDGE_PENALTY_MINUTES = 25
FLAG_THRESHOLD_MINUTES = 60
CLUSTER_MAX_DELTA_MINUTES = 15  # below this, cross-cluster slot is acceptable

# Rhine crossing segments (approximate bounding boxes) for bridge detection
# Bridges: Zoobrücke, Severinsbrücke — add more as needed
RHINE_CROSSINGS = [
    {"name": "Zoobrücke",      "lat_min": 50.940, "lat_max": 50.960, "lng_min": 6.960, "lng_max": 6.985},
    {"name": "Severinsbrücke", "lat_min": 50.915, "lat_max": 50.935, "lng_min": 6.960, "lng_max": 6.985},
]

BRIDGE_PENALTY_HOURS = [
    (7, 0,  9, 0),   # 07:00–09:00
    (16, 0, 18, 30), # 16:00–18:30
]

# Cologne neighborhood anchors for cluster detection
COLOGNE_CLUSTERS = {
    "Köln-West":   {"lat": 50.940, "lng": 6.890},  # Ehrenfeld / Braunsfeld
    "Köln-Nord":   {"lat": 50.975, "lng": 6.960},  # Nippes / Longerich
    "Köln-Süd":    {"lat": 50.910, "lng": 6.960},  # Südstadt / Bayenthal
    "Köln-Ost":    {"lat": 50.940, "lng": 7.010},  # Deutz / Kalk / Mülheim
    "Köln-Mitte":  {"lat": 50.938, "lng": 6.960},  # Innenstadt / Lindenthal
}
CLUSTER_RADIUS_KM = 3.5


# ── Pseudonymization ──────────────────────────────────────────────────────────

def get_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS patient_mapping (
            patient_id TEXT PRIMARY KEY,
            address_hash TEXT UNIQUE,
            lat REAL,
            lng REAL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def pseudonymize(address: str, db_path: str) -> tuple[str, Optional[tuple[float, float]]]:
    """Return (patient_id, cached_coords). Never logs real address."""
    import hashlib
    address_hash = hashlib.sha256(address.strip().lower().encode()).hexdigest()[:16]
    conn = get_db(db_path)
    row = conn.execute(
        "SELECT patient_id, lat, lng FROM patient_mapping WHERE address_hash = ?",
        (address_hash,)
    ).fetchone()
    if row:
        conn.close()
        pid, lat, lng = row
        coords = (lat, lng) if lat and lng else None
        return pid, coords

    # Assign next patient ID
    count = conn.execute("SELECT COUNT(*) FROM patient_mapping").fetchone()[0]
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    pid = f"Patient_{letters[count % 26]}{count // 26 if count >= 26 else ''}"
    conn.execute(
        "INSERT INTO patient_mapping (patient_id, address_hash) VALUES (?, ?)",
        (pid, address_hash)
    )
    conn.commit()
    conn.close()
    return pid, None


def cache_coords(address_hash_or_pid: str, lat: float, lng: float, db_path: str, by_pid: bool = False):
    conn = get_db(db_path)
    if by_pid:
        conn.execute("UPDATE patient_mapping SET lat=?, lng=? WHERE patient_id=?", (lat, lng, address_hash_or_pid))
    else:
        conn.execute("UPDATE patient_mapping SET lat=?, lng=? WHERE address_hash=?", (lat, lng, address_hash_or_pid))
    conn.commit()
    conn.close()


# ── Geocoding ─────────────────────────────────────────────────────────────────

def geocode(address: str, maps_api_key: str) -> Optional[tuple[float, float]]:
    """Geocode address. Returns (lat, lng) or None."""
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    r = requests.get(url, params={"address": address, "key": maps_api_key}, timeout=10)
    r.raise_for_status()
    data = r.json()
    if data.get("status") == "OK" and data.get("results"):
        loc = data["results"][0]["geometry"]["location"]
        return loc["lat"], loc["lng"]
    return None


# ── Distance Matrix ───────────────────────────────────────────────────────────

def travel_time_minutes(
    origin: tuple[float, float],
    destination: tuple[float, float],
    departure_time: datetime,
    maps_api_key: str,
) -> int:
    """Get driving duration in minutes via Distance Matrix API."""
    now = datetime.now()
    if (departure_time - now).total_seconds() < 7200:
        dep_param = "now"
    else:
        dep_param = int(departure_time.timestamp())

    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    r = requests.get(url, params={
        "origins": f"{origin[0]},{origin[1]}",
        "destinations": f"{destination[0]},{destination[1]}",
        "mode": "driving",
        "departure_time": dep_param,
        "key": maps_api_key,
    }, timeout=10)
    r.raise_for_status()
    data = r.json()
    try:
        element = data["rows"][0]["elements"][0]
        if element["status"] == "OK":
            # Use duration_in_traffic if available, else duration
            duration = element.get("duration_in_traffic", element["duration"])
            return duration["value"] // 60
    except (KeyError, IndexError):
        pass
    return 30  # fallback


# ── Bridge penalty ────────────────────────────────────────────────────────────

def _in_bridge_penalty_hours(dt: datetime) -> bool:
    for h_start, m_start, h_end, m_end in BRIDGE_PENALTY_HOURS:
        start = dt.replace(hour=h_start, minute=m_start, second=0, microsecond=0)
        end   = dt.replace(hour=h_end,   minute=m_end,   second=0, microsecond=0)
        if start <= dt <= end:
            return True
    return False


def _crosses_rhine(origin: tuple[float, float], destination: tuple[float, float]) -> bool:
    """Heuristic: one point west of Rhine (lng < 6.96), other east (lng > 6.97)."""
    west_of_rhine = lambda p: p[1] < 6.965
    return west_of_rhine(origin) != west_of_rhine(destination)


def bridge_penalty(origin: tuple[float, float], destination: tuple[float, float], dt: datetime) -> int:
    if _crosses_rhine(origin, destination) and _in_bridge_penalty_hours(dt):
        return BRIDGE_PENALTY_MINUTES
    return 0


# ── Clustering ────────────────────────────────────────────────────────────────

def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    import math
    R = 6371
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlng/2)**2
    return R * 2 * math.asin(math.sqrt(h))


def identify_cluster(coords: tuple[float, float]) -> Optional[str]:
    for name, anchor in COLOGNE_CLUSTERS.items():
        if _haversine_km(coords, (anchor["lat"], anchor["lng"])) <= CLUSTER_RADIUS_KM:
            return name
    return None


def dominant_cluster(stops: list[dict]) -> Optional[str]:
    counts: dict[str, int] = {}
    for stop in stops:
        if stop.get("coords"):
            c = identify_cluster(stop["coords"])
            if c:
                counts[c] = counts.get(c, 0) + 1
    return max(counts, key=counts.get) if counts else None


# ── Route delta calculation ───────────────────────────────────────────────────

def calculate_route_delta(
    new_coords: tuple[float, float],
    new_duration_min: int,
    stops: list[dict],
    home_coords: tuple[float, float],
    window_start: datetime,
    window_end: datetime,
    maps_api_key: str,
) -> list[dict]:
    """
    Test inserting new_coords into every gap in the day loop.
    Returns list of slot dicts sorted by delta_minutes ascending.

    stops: list of {coords, start_dt, end_dt, patient_id}
    """
    # Build ordered route: home → stops → home
    route = [{"coords": home_coords, "start_dt": window_start, "end_dt": window_start, "patient_id": "home"}]
    route += stops
    route.append({"coords": home_coords, "start_dt": window_end, "end_dt": window_end, "patient_id": "home"})

    slots = []

    for i in range(len(route) - 1):
        prev = route[i]
        next_ = route[i + 1]

        # Travel from prev to new appointment
        travel_to = travel_time_minutes(prev["coords"], new_coords, prev["end_dt"], maps_api_key)
        travel_to += bridge_penalty(prev["coords"], new_coords, prev["end_dt"])

        earliest_start = prev["end_dt"] + timedelta(minutes=travel_to)
        latest_start   = next_["start_dt"] - timedelta(minutes=new_duration_min) - timedelta(minutes=15)

        if earliest_start > latest_start:
            continue  # doesn't fit

        # Travel from new appointment to next
        appt_end = earliest_start + timedelta(minutes=new_duration_min)
        travel_from = travel_time_minutes(new_coords, next_["coords"], appt_end, maps_api_key)
        travel_from += bridge_penalty(new_coords, next_["coords"], appt_end)

        if appt_end + timedelta(minutes=travel_from) > next_["start_dt"]:
            continue  # overruns next appointment

        # Delta = added travel time vs. direct prev→next
        direct_travel = travel_time_minutes(prev["coords"], next_["coords"], prev["end_dt"], maps_api_key)
        delta = (travel_to + travel_from) - direct_travel

        cluster = identify_cluster(new_coords)
        day_cluster = dominant_cluster(stops)
        cluster_match = (cluster == day_cluster) if (cluster and day_cluster) else False

        slots.append({
            "slot_start": earliest_start,
            "slot_end": appt_end,
            "delta_minutes": max(0, delta),
            "cluster": cluster or "Köln (unbekannt)",
            "cluster_match": cluster_match,
            "flag": delta > FLAG_THRESHOLD_MINUTES,
            "position": i,
        })

    slots.sort(key=lambda s: s["delta_minutes"])
    return slots[:3]


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Usage: python3 routing.py <input_json>
    input_json: {
      "address": "Venloer Str. 42, Köln",
      "day_iso": "2026-04-22",
      "stops": [{"location": "...", "start": "HH:MM", "end": "HH:MM"}],
      "window_start": "08:00",
      "window_end": "18:00",
      "home_coords": {"lat": 50.9333, "lng": 6.9500},
      "maps_api_key": "...",
      "db_path": "physio.db"
    }
    """
    data = json.loads(sys.argv[1])
    maps_key = data["maps_api_key"]
    db_path  = data["db_path"]
    day      = datetime.fromisoformat(data["day_iso"])

    def to_dt(t: str) -> datetime:
        h, m = map(int, t.split(":"))
        return day.replace(hour=h, minute=m, second=0, microsecond=0)

    window_start = to_dt(data["window_start"])
    window_end   = to_dt(data["window_end"])
    home         = (data["home_coords"]["lat"], data["home_coords"]["lng"])

    # Pseudonymize + geocode new address
    pid, coords = pseudonymize(data["address"], db_path)
    if not coords:
        import hashlib
        ahash = hashlib.sha256(data["address"].strip().lower().encode()).hexdigest()[:16]
        coords = geocode(data["address"], maps_key)
        if coords:
            cache_coords(ahash, coords[0], coords[1], db_path)

    if not coords:
        print(json.dumps({"error": f"Could not geocode address (id={pid})"}))
        sys.exit(1)

    # Build stops list
    stops = []
    for s in data.get("stops", []):
        spid, scoords = pseudonymize(s["location"], db_path)
        if not scoords:
            import hashlib
            ahash = hashlib.sha256(s["location"].strip().lower().encode()).hexdigest()[:16]
            scoords = geocode(s["location"], maps_key)
            if scoords:
                cache_coords(ahash, scoords[0], scoords[1], db_path)
        if scoords:
            stops.append({
                "coords": scoords,
                "start_dt": to_dt(s["start"]),
                "end_dt":   to_dt(s["end"]),
                "patient_id": spid,
            })

    slots = calculate_route_delta(coords, 60, stops, home, window_start, window_end, maps_key)

    result = []
    for slot in slots:
        result.append({
            "slot_start":    slot["slot_start"].strftime("%H:%M"),
            "slot_end":      slot["slot_end"].strftime("%H:%M"),
            "delta_minutes": slot["delta_minutes"],
            "cluster":       slot["cluster"],
            "cluster_match": slot["cluster_match"],
            "flag":          slot["flag"],
        })

    print(json.dumps(result, ensure_ascii=False))
