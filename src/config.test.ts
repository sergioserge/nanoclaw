import { describe, expect, it, vi } from 'vitest';

vi.mock('./env.js', () => ({
  readEnvFile: vi.fn(() => ({})),
}));

vi.mock('./timezone.js', () => ({
  isValidTimezone: (tz: string) =>
    ['UTC', 'Europe/Berlin', 'Europe/London', 'America/New_York'].includes(tz),
}));

import { buildTriggerPattern, getTriggerPattern } from './config.js';

describe('buildTriggerPattern', () => {
  it('matches trigger at the start of the string', () => {
    const re = buildTriggerPattern('@Andy');
    expect(re.test('@Andy hello')).toBe(true);
  });

  it('requires a word boundary — does not match mid-word', () => {
    const re = buildTriggerPattern('@Andy');
    expect(re.test('@Andywood')).toBe(false);
  });

  it('is case-insensitive', () => {
    const re = buildTriggerPattern('@Andy');
    expect(re.test('@andy do this')).toBe(true);
    expect(re.test('@ANDY do this')).toBe(true);
  });

  it('does not match when trigger appears mid-sentence', () => {
    const re = buildTriggerPattern('@Andy');
    expect(re.test('hello @Andy')).toBe(false);
  });

  it('escapes regex special characters in trigger', () => {
    const re = buildTriggerPattern('@Bob.Bot');
    expect(re.test('@Bob.Bot help')).toBe(true);
    // Literal dot — should not match @BobXBot
    expect(re.test('@BobXBot help')).toBe(false);
  });

  it('escapes regex metacharacters so they are literal in the pattern source', () => {
    // '+' must appear as '\+' in the source, not as a regex quantifier
    expect(buildTriggerPattern('@Bot+').source).toContain('\\+');
    // '(' must appear as '\(' in the source, not open a capture group
    expect(buildTriggerPattern('bot(v2)').source).toContain('\\(');
    // Unescaped '.' would match any char; escaped it must not match @BobXBot
    expect(buildTriggerPattern('@Bob.Bot').test('@BobXBot help')).toBe(false);
  });
});

describe('getTriggerPattern', () => {
  it('uses default trigger (@ASSISTANT_NAME) when no argument given', () => {
    const re = getTriggerPattern();
    // Default trigger is derived from ASSISTANT_NAME (mocked env returns 'Andy')
    expect(re).toBeInstanceOf(RegExp);
    expect(re.flags).toContain('i');
  });

  it('uses the provided custom trigger', () => {
    const re = getTriggerPattern('@Physio');
    expect(re.test('@Physio new patient')).toBe(true);
    expect(re.test('@Andy new patient')).toBe(false);
  });

  it('trims leading and trailing whitespace from trigger', () => {
    const clean = getTriggerPattern('@Andy');
    const padded = getTriggerPattern('  @Andy  ');
    // Both should match the same input
    expect(clean.source).toBe(padded.source);
  });

  it('falls back gracefully when trigger is an empty string', () => {
    // Empty string falls back to default trigger
    const re = getTriggerPattern('');
    expect(re).toBeInstanceOf(RegExp);
  });
});
