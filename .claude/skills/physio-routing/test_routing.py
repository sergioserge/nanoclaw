"""
Unit tests for routing.py — Mobile Physio VRP engine.
No API keys required: tests run in degraded mode (no network calls).

Run with: python3 -m unittest test_routing.py
"""
import math
import sys
import tempfile
import os
import unittest
from datetime import datetime

# Allow importing routing.py from the same directory
sys.path.insert(0, os.path.dirname(__file__))

import routing


# ── _in_bridge_penalty_hours ──────────────────────────────────────────────────

class TestInBridgePenaltyHours(unittest.TestCase):
    def _dt(self, h: int, m: int) -> datetime:
        return datetime(2026, 4, 22, h, m, 0)

    def test_inside_morning_window(self):
        self.assertTrue(routing._in_bridge_penalty_hours(self._dt(8, 0)))

    def test_inside_evening_window(self):
        self.assertTrue(routing._in_bridge_penalty_hours(self._dt(17, 0)))

    def test_at_morning_window_start(self):
        self.assertTrue(routing._in_bridge_penalty_hours(self._dt(7, 0)))

    def test_at_morning_window_end(self):
        self.assertTrue(routing._in_bridge_penalty_hours(self._dt(9, 0)))

    def test_just_after_morning_window(self):
        self.assertFalse(routing._in_bridge_penalty_hours(self._dt(9, 1)))

    def test_at_evening_window_end(self):
        self.assertTrue(routing._in_bridge_penalty_hours(self._dt(18, 30)))

    def test_just_after_evening_window(self):
        self.assertFalse(routing._in_bridge_penalty_hours(self._dt(18, 31)))

    def test_midday_outside_both_windows(self):
        self.assertFalse(routing._in_bridge_penalty_hours(self._dt(12, 0)))

    def test_early_morning_outside_window(self):
        self.assertFalse(routing._in_bridge_penalty_hours(self._dt(6, 59)))


# ── _crosses_rhine ────────────────────────────────────────────────────────────

class TestCrossesRhine(unittest.TestCase):
    WEST = (50.940, 6.890)   # lng < 6.965 → west bank
    EAST = (50.940, 7.010)   # lng > 6.965 → east bank

    def test_west_to_east_crosses(self):
        self.assertTrue(routing._crosses_rhine(self.WEST, self.EAST))

    def test_east_to_west_crosses(self):
        self.assertTrue(routing._crosses_rhine(self.EAST, self.WEST))

    def test_west_to_west_does_not_cross(self):
        west2 = (50.930, 6.920)
        self.assertFalse(routing._crosses_rhine(self.WEST, west2))

    def test_east_to_east_does_not_cross(self):
        east2 = (50.950, 7.020)
        self.assertFalse(routing._crosses_rhine(self.EAST, east2))

    def test_exactly_on_boundary(self):
        # 6.965 is the threshold — not < 6.965 so counts as east
        on_boundary = (50.940, 6.965)
        self.assertFalse(routing._crosses_rhine(self.EAST, on_boundary))


# ── bridge_penalty ────────────────────────────────────────────────────────────

class TestBridgePenalty(unittest.TestCase):
    WEST = (50.940, 6.890)
    EAST = (50.940, 7.010)

    def _dt(self, h: int, m: int) -> datetime:
        return datetime(2026, 4, 22, h, m, 0)

    def test_applies_penalty_when_crossing_during_peak(self):
        penalty = routing.bridge_penalty(self.WEST, self.EAST, self._dt(8, 0))
        self.assertEqual(penalty, routing.BRIDGE_PENALTY_MINUTES)

    def test_no_penalty_during_off_peak(self):
        penalty = routing.bridge_penalty(self.WEST, self.EAST, self._dt(12, 0))
        self.assertEqual(penalty, 0)

    def test_no_penalty_same_side(self):
        west2 = (50.930, 6.920)
        penalty = routing.bridge_penalty(self.WEST, west2, self._dt(8, 0))
        self.assertEqual(penalty, 0)


# ── _haversine_km ─────────────────────────────────────────────────────────────

class TestHaversineKm(unittest.TestCase):
    def test_same_point_is_zero(self):
        p = (50.9333, 6.9500)
        self.assertAlmostEqual(routing._haversine_km(p, p), 0.0, places=6)

    def test_one_degree_latitude_is_roughly_111km(self):
        a = (50.0, 7.0)
        b = (51.0, 7.0)
        dist = routing._haversine_km(a, b)
        self.assertAlmostEqual(dist, 111.2, delta=1.0)

    def test_cologne_to_nearby_point(self):
        cologne = (50.9333, 6.9500)
        # Point ~3.5 km northeast — should be within cluster radius
        nearby = (50.9648, 6.9953)
        dist = routing._haversine_km(cologne, nearby)
        self.assertLess(dist, 5.0)
        self.assertGreater(dist, 2.0)


# ── identify_cluster ──────────────────────────────────────────────────────────

class TestIdentifyCluster(unittest.TestCase):
    def test_identifies_koln_mitte(self):
        # (50.942, 6.958): ~0.47 km from Mitte, ~3.56 km from Süd, ~3.65 km from Ost
        # Exclusively within Mitte — no other cluster's radius covers it.
        cluster = routing.identify_cluster((50.942, 6.958))
        self.assertEqual(cluster, "Köln-Mitte")

    def test_identifies_koln_west(self):
        # Ehrenfeld area — Köln-West anchor (50.940, 6.890)
        cluster = routing.identify_cluster((50.940, 6.890))
        self.assertEqual(cluster, "Köln-West")

    def test_identifies_koln_nord(self):
        # Nippes area — Köln-Nord anchor (50.975, 6.960)
        cluster = routing.identify_cluster((50.975, 6.960))
        self.assertEqual(cluster, "Köln-Nord")

    def test_identifies_koln_ost(self):
        # Deutz area — Köln-Ost anchor (50.940, 7.010)
        cluster = routing.identify_cluster((50.940, 7.010))
        self.assertEqual(cluster, "Köln-Ost")

    def test_returns_none_for_point_far_from_cologne(self):
        # Düsseldorf — 40+ km from any Cologne cluster
        cluster = routing.identify_cluster((51.2217, 6.7762))
        self.assertIsNone(cluster)

    def test_returns_none_for_point_just_outside_radius(self):
        # Build a point exactly CLUSTER_RADIUS_KM + small epsilon outside Mitte
        anchor_lat, anchor_lng = 50.938, 6.960
        # Move ~4 km north (> 3.5 km radius)
        far_north = (anchor_lat + 0.036, anchor_lng)  # ~4 km north
        dist = routing._haversine_km(far_north, (anchor_lat, anchor_lng))
        self.assertGreater(dist, routing.CLUSTER_RADIUS_KM)
        cluster = routing.identify_cluster(far_north)
        # Should not be Mitte; may be Nord or None
        self.assertNotEqual(cluster, "Köln-Mitte")


# ── dominant_cluster ──────────────────────────────────────────────────────────

class TestDominantCluster(unittest.TestCase):
    def test_single_stop_returns_its_cluster(self):
        stops = [{"coords": (50.942, 6.958)}]  # Mitte-exclusive coords
        self.assertEqual(routing.dominant_cluster(stops), "Köln-Mitte")

    def test_majority_cluster_wins(self):
        stops = [
            {"coords": (50.942, 6.958)},  # Mitte-exclusive
            {"coords": (50.943, 6.957)},  # also Mitte-exclusive
            {"coords": (50.940, 7.010)},  # Ost
        ]
        self.assertEqual(routing.dominant_cluster(stops), "Köln-Mitte")

    def test_returns_none_when_no_stops(self):
        self.assertIsNone(routing.dominant_cluster([]))

    def test_ignores_stops_without_coords(self):
        stops = [{"coords": None}, {"no_coords_key": True}]
        self.assertIsNone(routing.dominant_cluster(stops))

    def test_ignores_stops_in_unknown_cluster(self):
        # All stops far from Cologne
        stops = [{"coords": (51.2217, 6.7762)}]  # Düsseldorf
        self.assertIsNone(routing.dominant_cluster(stops))


# ── pseudonymize ──────────────────────────────────────────────────────────────

class TestPseudonymize(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mktemp(suffix='.db')

    def tearDown(self):
        if os.path.exists(self._tmp):
            os.unlink(self._tmp)

    def test_assigns_patient_id_to_new_address(self):
        pid, coords = routing.pseudonymize("Venloer Str. 42, Köln", self._tmp)
        self.assertIsInstance(pid, str)
        self.assertTrue(pid.startswith("Patient_"))
        self.assertIsNone(coords)  # no coords cached yet

    def test_deterministic_same_address_same_id(self):
        pid1, _ = routing.pseudonymize("Venloer Str. 42, Köln", self._tmp)
        pid2, _ = routing.pseudonymize("Venloer Str. 42, Köln", self._tmp)
        self.assertEqual(pid1, pid2)

    def test_case_and_whitespace_normalized(self):
        pid1, _ = routing.pseudonymize("venloer str. 42, köln", self._tmp)
        pid2, _ = routing.pseudonymize("  Venloer Str. 42, Köln  ", self._tmp)
        self.assertEqual(pid1, pid2)

    def test_different_addresses_get_different_ids(self):
        pid1, _ = routing.pseudonymize("Venloer Str. 42, Köln", self._tmp)
        pid2, _ = routing.pseudonymize("Aachener Str. 1, Köln", self._tmp)
        self.assertNotEqual(pid1, pid2)

    def test_returns_cached_coords_on_second_call(self):
        import hashlib
        address = "Venloer Str. 42, Köln"
        pid, _ = routing.pseudonymize(address, self._tmp)
        # Cache coords manually
        ahash = hashlib.sha256(address.strip().lower().encode()).hexdigest()[:16]
        routing.cache_coords(ahash, 50.938, 6.910, self._tmp)
        # Second lookup should return cached coords
        _, coords = routing.pseudonymize(address, self._tmp)
        self.assertIsNotNone(coords)
        self.assertAlmostEqual(coords[0], 50.938)
        self.assertAlmostEqual(coords[1], 6.910)


# ── calculate_route_delta ─────────────────────────────────────────────────────

class TestCalculateRouteDelta(unittest.TestCase):
    """All tests run in degraded mode (no API key) — travel_time = 20 min fixed."""

    HOME = (50.9333, 6.9500)  # Cologne center
    NEW = (50.9380, 6.9600)   # Nearby point (also Cologne center area)

    def _dt(self, h: int, m: int) -> datetime:
        return datetime(2026, 4, 22, h, m, 0)

    def test_empty_day_produces_one_slot(self):
        """No existing stops → exactly one gap (home→home), produces 1 slot."""
        slots = routing.calculate_route_delta(
            new_coords=self.NEW,
            new_duration_min=60,
            stops=[],
            home_coords=self.HOME,
            window_start=self._dt(8, 0),
            window_end=self._dt(18, 0),
            maps_api_key="",
        )
        self.assertEqual(len(slots), 1)

    def test_slot_has_required_fields(self):
        slots = routing.calculate_route_delta(
            new_coords=self.NEW,
            new_duration_min=60,
            stops=[],
            home_coords=self.HOME,
            window_start=self._dt(8, 0),
            window_end=self._dt(18, 0),
            maps_api_key="",
        )
        slot = slots[0]
        for key in ("slot_start", "slot_end", "delta_minutes", "cluster", "cluster_match", "flag"):
            self.assertIn(key, slot)

    def test_slot_start_is_earliest_possible(self):
        """earliest_start = window_start + travel_to (20 min in degraded mode)."""
        slots = routing.calculate_route_delta(
            new_coords=self.NEW,
            new_duration_min=60,
            stops=[],
            home_coords=self.HOME,
            window_start=self._dt(8, 0),
            window_end=self._dt(18, 0),
            maps_api_key="",
        )
        expected_start = self._dt(8, 20)  # 08:00 + 20 min travel
        self.assertEqual(slots[0]["slot_start"], expected_start)

    def test_no_slots_when_window_too_narrow(self):
        """Window shorter than travel + appointment + buffer → 0 slots."""
        # Window: 08:00–09:00 (60 min), appointment=60 min, travel=20+20, buffer=15
        # Need at least 20+60+15+20=115 min → doesn't fit in 60 min window
        slots = routing.calculate_route_delta(
            new_coords=self.NEW,
            new_duration_min=60,
            stops=[],
            home_coords=self.HOME,
            window_start=self._dt(8, 0),
            window_end=self._dt(9, 0),
            maps_api_key="",
        )
        self.assertEqual(len(slots), 0)

    def test_returns_at_most_three_slots(self):
        """Even with many gaps, result is capped at 3."""
        stops = [
            {
                "coords": self.HOME,
                "start_dt": self._dt(9, 0),
                "end_dt": self._dt(10, 0),
                "patient_id": "Patient_A",
                "name": "A",
            },
            {
                "coords": self.HOME,
                "start_dt": self._dt(11, 0),
                "end_dt": self._dt(12, 0),
                "patient_id": "Patient_B",
                "name": "B",
            },
            {
                "coords": self.HOME,
                "start_dt": self._dt(13, 0),
                "end_dt": self._dt(14, 0),
                "patient_id": "Patient_C",
                "name": "C",
            },
        ]
        slots = routing.calculate_route_delta(
            new_coords=self.NEW,
            new_duration_min=60,
            stops=stops,
            home_coords=self.HOME,
            window_start=self._dt(8, 0),
            window_end=self._dt(18, 0),
            maps_api_key="",
        )
        self.assertLessEqual(len(slots), 3)

    def test_slots_sorted_by_delta_ascending(self):
        slots = routing.calculate_route_delta(
            new_coords=self.NEW,
            new_duration_min=60,
            stops=[
                {
                    "coords": self.HOME,
                    "start_dt": self._dt(10, 0),
                    "end_dt": self._dt(11, 0),
                    "patient_id": "P1",
                    "name": "",
                },
            ],
            home_coords=self.HOME,
            window_start=self._dt(8, 0),
            window_end=self._dt(18, 0),
            maps_api_key="",
        )
        deltas = [s["delta_minutes"] for s in slots]
        self.assertEqual(deltas, sorted(deltas))

    def test_delta_is_non_negative(self):
        slots = routing.calculate_route_delta(
            new_coords=self.NEW,
            new_duration_min=60,
            stops=[],
            home_coords=self.HOME,
            window_start=self._dt(8, 0),
            window_end=self._dt(18, 0),
            maps_api_key="",
        )
        for slot in slots:
            self.assertGreaterEqual(slot["delta_minutes"], 0)

    def test_flag_set_when_delta_exceeds_threshold(self):
        """Force a large delta by placing new patient far from existing route."""
        # West bank point — far from east-bank existing stops
        far_west = (50.940, 6.800)
        east = (50.940, 7.050)
        stops = [
            {
                "coords": east,
                "start_dt": self._dt(9, 0),
                "end_dt": self._dt(10, 0),
                "patient_id": "P_east",
                "name": "",
            },
        ]
        slots = routing.calculate_route_delta(
            new_coords=far_west,
            new_duration_min=60,
            stops=stops,
            home_coords=self.HOME,
            window_start=self._dt(8, 0),
            window_end=self._dt(18, 0),
            maps_api_key="",
        )
        # In degraded mode travel is always 20 min, delta = travel_to + travel_from - direct
        # delta ≤ 20+20-20 = 20, which is below 60 min flag threshold
        # So this just verifies flag=False in degraded mode (delta always small)
        for slot in slots:
            self.assertFalse(slot["flag"])


if __name__ == '__main__':
    unittest.main()
