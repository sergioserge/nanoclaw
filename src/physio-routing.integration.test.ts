/**
 * Integration tests for the physio routing CLI (routing.py).
 * Spawns Python as a subprocess — no API key, degraded mode only.
 * Validates JSON output structure, slot ordering, and pseudonymization stability.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { execFileSync } from 'child_process';
import { mkdtempSync, rmSync } from 'fs';
import { tmpdir } from 'os';
import { join, resolve } from 'path';

const ROUTING_PY = resolve(
  __dirname,
  '../.claude/skills/physio-routing/routing.py',
);

const HOME = { lat: 50.9333, lng: 6.95 };
const DAY = '2026-04-22';

function runRouting(payload: object): { slots: any[]; degraded: boolean } {
  const out = execFileSync('python3', [ROUTING_PY, JSON.stringify(payload)], {
    encoding: 'utf-8',
    timeout: 15_000,
  });
  return JSON.parse(out);
}

let tmpDir: string;

beforeEach(() => {
  tmpDir = mkdtempSync(join(tmpdir(), 'physio-int-'));
});

afterEach(() => {
  rmSync(tmpDir, { recursive: true, force: true });
});

// ── Basic output structure ────────────────────────────────────────────────────

describe('physio routing CLI — degraded mode (no API key)', () => {
  it('reports degraded=true when no maps_api_key provided', () => {
    const result = runRouting({
      address: 'Venloer Str. 42, Köln',
      day_iso: DAY,
      stops: [],
      window_start: '08:00',
      window_end: '18:00',
      home_coords: HOME,
      maps_api_key: '',
      db_path: join(tmpDir, 'physio.db'),
    });
    expect(result.degraded).toBe(true);
  });

  it('returns a non-empty slots array for a wide open day', () => {
    const result = runRouting({
      address: 'Venloer Str. 42, Köln',
      day_iso: DAY,
      stops: [],
      window_start: '08:00',
      window_end: '18:00',
      home_coords: HOME,
      maps_api_key: '',
      db_path: join(tmpDir, 'physio.db'),
    });
    expect(result.slots.length).toBeGreaterThan(0);
  });

  it('each slot has the required output fields', () => {
    const result = runRouting({
      address: 'Venloer Str. 42, Köln',
      day_iso: DAY,
      stops: [],
      window_start: '08:00',
      window_end: '18:00',
      home_coords: HOME,
      maps_api_key: '',
      db_path: join(tmpDir, 'physio.db'),
    });
    for (const slot of result.slots) {
      expect(slot).toHaveProperty('slot_start');
      expect(slot).toHaveProperty('slot_end');
      expect(slot).toHaveProperty('delta_minutes');
      expect(slot).toHaveProperty('cluster');
      expect(slot).toHaveProperty('cluster_match');
      expect(slot).toHaveProperty('flag');
      expect(typeof slot.delta_minutes).toBe('number');
      expect(typeof slot.flag).toBe('boolean');
      expect(typeof slot.cluster_match).toBe('boolean');
      // Times are HH:MM strings
      expect(slot.slot_start).toMatch(/^\d{2}:\d{2}$/);
      expect(slot.slot_end).toMatch(/^\d{2}:\d{2}$/);
    }
  });

  it('returns at most 3 slots', () => {
    const result = runRouting({
      address: 'Venloer Str. 42, Köln',
      day_iso: DAY,
      stops: [
        {
          location: 'Aachener Str. 1, Köln',
          start: '09:00',
          end: '10:00',
          name: 'P1',
        },
        {
          location: 'Ehrenfelder Str. 5, Köln',
          start: '11:00',
          end: '12:00',
          name: 'P2',
        },
        {
          location: 'Neusser Str. 10, Köln',
          start: '13:00',
          end: '14:00',
          name: 'P3',
        },
      ],
      window_start: '08:00',
      window_end: '18:00',
      home_coords: HOME,
      maps_api_key: '',
      db_path: join(tmpDir, 'physio.db'),
    });
    expect(result.slots.length).toBeLessThanOrEqual(3);
  });

  it('slots are sorted by delta_minutes ascending', () => {
    const result = runRouting({
      address: 'Venloer Str. 42, Köln',
      day_iso: DAY,
      stops: [
        {
          location: 'Aachener Str. 1, Köln',
          start: '10:00',
          end: '11:00',
          name: 'P1',
        },
      ],
      window_start: '08:00',
      window_end: '18:00',
      home_coords: HOME,
      maps_api_key: '',
      db_path: join(tmpDir, 'physio.db'),
    });
    const deltas = result.slots.map((s: any) => s.delta_minutes);
    expect(deltas).toEqual([...deltas].sort((a, b) => a - b));
  });

  it('returns no slots when booking window is too narrow to fit appointment', () => {
    // 30 min window: cannot fit 60 min appointment + travel (20+20) + buffer (15)
    const result = runRouting({
      address: 'Venloer Str. 42, Köln',
      day_iso: DAY,
      stops: [],
      window_start: '08:00',
      window_end: '08:30',
      home_coords: HOME,
      maps_api_key: '',
      db_path: join(tmpDir, 'physio.db'),
    });
    expect(result.slots).toHaveLength(0);
  });
});

// ── Pseudonymization stability ────────────────────────────────────────────────

describe('pseudonymization across calls', () => {
  it('same address on a second run reuses the same patient entry', () => {
    const payload = {
      address: 'Venloer Str. 42, Köln',
      day_iso: DAY,
      stops: [],
      window_start: '08:00',
      window_end: '18:00',
      home_coords: HOME,
      maps_api_key: '',
      db_path: join(tmpDir, 'physio.db'), // same db both calls
    };
    const first = runRouting(payload);
    const second = runRouting(payload);
    // Slot structure should be identical — same patient, same degraded coords
    expect(first.slots).toEqual(second.slots);
  });
});
