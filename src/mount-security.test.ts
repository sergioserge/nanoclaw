import { beforeEach, describe, expect, it, vi } from 'vitest';
import fs from 'fs';

vi.mock('./config.js', () => ({
  MOUNT_ALLOWLIST_PATH: '/test/.config/nanoclaw/mount-allowlist.json',
}));

vi.mock('./logger.js', () => ({
  logger: { warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

vi.mock('fs', async () => {
  const actual = await vi.importActual<typeof import('fs')>('fs');
  return {
    ...actual,
    default: {
      ...actual,
      existsSync: vi.fn(),
      readFileSync: vi.fn(),
      realpathSync: vi.fn(),
    },
  };
});

import {
  _resetAllowlistCacheForTests,
  generateAllowlistTemplate,
  loadMountAllowlist,
  validateAdditionalMounts,
  validateMount,
} from './mount-security.js';

const ALLOWLIST = {
  allowedRoots: [
    {
      path: '/allowed/projects',
      allowReadWrite: true,
      description: 'Projects',
    },
    { path: '/allowed/docs', allowReadWrite: false, description: 'Docs' },
  ],
  blockedPatterns: ['mytoken'],
  nonMainReadOnly: true,
};

function setupAllowlist(override?: object) {
  const data = override ?? ALLOWLIST;
  vi.mocked(fs.existsSync).mockReturnValue(true);
  vi.mocked(fs.readFileSync).mockReturnValue(JSON.stringify(data) as any);
  // Make realpathSync return the path unchanged (pretend all paths exist)
  vi.mocked(fs.realpathSync).mockImplementation((p: any) => String(p));
}

beforeEach(() => {
  _resetAllowlistCacheForTests();
  vi.clearAllMocks();
});

// ── loadMountAllowlist ────────────────────────────────────────────────────────

describe('loadMountAllowlist', () => {
  it('returns null when allowlist file is absent', () => {
    vi.mocked(fs.existsSync).mockReturnValue(false);
    expect(loadMountAllowlist()).toBeNull();
  });

  it('returns null and caches error on invalid JSON', () => {
    vi.mocked(fs.existsSync).mockReturnValue(true);
    vi.mocked(fs.readFileSync).mockReturnValue('not-json' as any);

    expect(loadMountAllowlist()).toBeNull();
    // Second call must not read file again
    expect(loadMountAllowlist()).toBeNull();
    expect(fs.readFileSync).toHaveBeenCalledTimes(1);
  });

  it('returns null and caches error when allowedRoots is missing', () => {
    vi.mocked(fs.existsSync).mockReturnValue(true);
    vi.mocked(fs.readFileSync).mockReturnValue(
      JSON.stringify({ blockedPatterns: [], nonMainReadOnly: true }) as any,
    );
    expect(loadMountAllowlist()).toBeNull();
    expect(loadMountAllowlist()).toBeNull();
    expect(fs.readFileSync).toHaveBeenCalledTimes(1);
  });

  it('returns null and caches error when nonMainReadOnly is not boolean', () => {
    vi.mocked(fs.existsSync).mockReturnValue(true);
    vi.mocked(fs.readFileSync).mockReturnValue(
      JSON.stringify({
        allowedRoots: [],
        blockedPatterns: [],
        nonMainReadOnly: 'yes',
      }) as any,
    );
    expect(loadMountAllowlist()).toBeNull();
  });

  it('merges default blocked patterns with custom patterns', () => {
    setupAllowlist();
    const result = loadMountAllowlist()!;
    // Default patterns include '.ssh'; custom adds 'mytoken'
    expect(result.blockedPatterns).toContain('.ssh');
    expect(result.blockedPatterns).toContain('mytoken');
  });

  it('caches successful load — second call skips fs read', () => {
    setupAllowlist();
    const first = loadMountAllowlist();
    const second = loadMountAllowlist();
    expect(first).not.toBeNull();
    expect(second).toBe(first);
    expect(fs.readFileSync).toHaveBeenCalledTimes(1);
  });
});

// ── validateMount ─────────────────────────────────────────────────────────────

describe('validateMount — no allowlist', () => {
  it('blocks all mounts when allowlist is absent', () => {
    vi.mocked(fs.existsSync).mockReturnValue(false);
    const result = validateMount(
      { hostPath: '/allowed/projects/myrepo' },
      true,
    );
    expect(result.allowed).toBe(false);
    expect(result.reason).toMatch(/No mount allowlist/);
  });
});

describe('validateMount — container path validation', () => {
  beforeEach(() => setupAllowlist());

  it('blocks path traversal in container path', () => {
    const result = validateMount(
      { hostPath: '/allowed/projects/repo', containerPath: '../escape' },
      true,
    );
    expect(result.allowed).toBe(false);
    expect(result.reason).toMatch(/Invalid container path/);
  });

  it('blocks absolute container path', () => {
    const result = validateMount(
      { hostPath: '/allowed/projects/repo', containerPath: '/workspace/hack' },
      true,
    );
    expect(result.allowed).toBe(false);
  });

  it('falls back to hostPath basename when containerPath is empty string', () => {
    // '' is falsy — code treats it as "not specified" and uses basename
    const result = validateMount(
      { hostPath: '/allowed/projects/myrepo', containerPath: '' },
      true,
    );
    expect(result.allowed).toBe(true);
    expect(result.resolvedContainerPath).toBe('myrepo');
  });

  it('blocks colon in container path (Docker option injection)', () => {
    const result = validateMount(
      { hostPath: '/allowed/projects/repo', containerPath: 'repo:rw' },
      true,
    );
    expect(result.allowed).toBe(false);
  });

  it('blocks whitespace-only container path', () => {
    const result = validateMount(
      { hostPath: '/allowed/projects/repo', containerPath: '   ' },
      true,
    );
    expect(result.allowed).toBe(false);
  });
});

describe('validateMount — host path resolution', () => {
  beforeEach(() => setupAllowlist());

  it('blocks when host path does not exist', () => {
    vi.mocked(fs.realpathSync).mockImplementation((p: any) => {
      if (String(p) === '/nonexistent/repo') throw new Error('ENOENT');
      return String(p);
    });
    const result = validateMount({ hostPath: '/nonexistent/repo' }, true);
    expect(result.allowed).toBe(false);
    expect(result.reason).toMatch(/does not exist/);
  });

  it('derives containerPath from basename when not specified', () => {
    const result = validateMount(
      { hostPath: '/allowed/projects/myrepo' },
      true,
    );
    expect(result.allowed).toBe(true);
    expect(result.resolvedContainerPath).toBe('myrepo');
  });
});

describe('validateMount — blocked patterns', () => {
  beforeEach(() => setupAllowlist());

  it('blocks path matching a default blocked pattern (.ssh)', () => {
    const result = validateMount(
      { hostPath: '/allowed/projects/.ssh/config' },
      true,
    );
    expect(result.allowed).toBe(false);
    expect(result.reason).toMatch(/blocked pattern/);
  });

  it('blocks path matching a custom blocked pattern', () => {
    const result = validateMount(
      { hostPath: '/allowed/projects/mytoken' },
      true,
    );
    expect(result.allowed).toBe(false);
    expect(result.reason).toMatch(/blocked pattern/);
  });
});

describe('validateMount — allowed roots', () => {
  beforeEach(() => setupAllowlist());

  it('blocks path not under any allowed root', () => {
    const result = validateMount({ hostPath: '/home/user/secret' }, true);
    expect(result.allowed).toBe(false);
    expect(result.reason).toMatch(/not under any allowed root/);
  });

  it('allows path under a matching allowed root', () => {
    const result = validateMount(
      { hostPath: '/allowed/projects/myrepo' },
      true,
    );
    expect(result.allowed).toBe(true);
    expect(result.realHostPath).toBe('/allowed/projects/myrepo');
  });
});

describe('validateMount — readonly enforcement', () => {
  beforeEach(() => setupAllowlist());

  it('defaults to readonly when mount.readonly is not explicitly false', () => {
    const result = validateMount({ hostPath: '/allowed/projects/repo' }, true);
    expect(result.allowed).toBe(true);
    expect(result.effectiveReadonly).toBe(true);
  });

  it('allows read-write for main group under a rw-enabled root', () => {
    const result = validateMount(
      { hostPath: '/allowed/projects/repo', readonly: false },
      true, // isMain
    );
    expect(result.allowed).toBe(true);
    expect(result.effectiveReadonly).toBe(false);
  });

  it('forces readonly for non-main group when nonMainReadOnly=true', () => {
    const result = validateMount(
      { hostPath: '/allowed/projects/repo', readonly: false },
      false, // isMain = false
    );
    expect(result.allowed).toBe(true);
    expect(result.effectiveReadonly).toBe(true);
  });

  it('forces readonly when allowedRoot does not allowReadWrite', () => {
    // /allowed/docs root has allowReadWrite: false
    const result = validateMount(
      { hostPath: '/allowed/docs/report.pdf', readonly: false },
      true, // isMain — but root disallows rw
    );
    expect(result.allowed).toBe(true);
    expect(result.effectiveReadonly).toBe(true);
  });
});

// ── validateAdditionalMounts ──────────────────────────────────────────────────

describe('validateAdditionalMounts', () => {
  beforeEach(() => setupAllowlist());

  it('returns only mounts that pass validation', () => {
    const mounts = [
      { hostPath: '/allowed/projects/good' },
      { hostPath: '/not-allowed/bad' },
    ];
    const result = validateAdditionalMounts(mounts, 'test-group', true);
    expect(result).toHaveLength(1);
    expect(result[0].hostPath).toBe('/allowed/projects/good');
  });

  it('prefixes container paths with /workspace/extra/', () => {
    const result = validateAdditionalMounts(
      [{ hostPath: '/allowed/projects/myrepo' }],
      'test-group',
      true,
    );
    expect(result[0].containerPath).toBe('/workspace/extra/myrepo');
  });

  it('returns empty array when all mounts are rejected', () => {
    vi.mocked(fs.existsSync).mockReturnValue(false); // no allowlist
    _resetAllowlistCacheForTests();
    const result = validateAdditionalMounts(
      [{ hostPath: '/anything' }],
      'test-group',
      true,
    );
    expect(result).toHaveLength(0);
  });
});

// ── generateAllowlistTemplate ─────────────────────────────────────────────────

describe('generateAllowlistTemplate', () => {
  it('returns valid JSON', () => {
    expect(() => JSON.parse(generateAllowlistTemplate())).not.toThrow();
  });

  it('has required structure fields', () => {
    const tmpl = JSON.parse(generateAllowlistTemplate());
    expect(Array.isArray(tmpl.allowedRoots)).toBe(true);
    expect(Array.isArray(tmpl.blockedPatterns)).toBe(true);
    expect(typeof tmpl.nonMainReadOnly).toBe('boolean');
  });

  it('includes at least one allowed root with required fields', () => {
    const tmpl = JSON.parse(generateAllowlistTemplate());
    expect(tmpl.allowedRoots.length).toBeGreaterThan(0);
    const root = tmpl.allowedRoots[0];
    expect(typeof root.path).toBe('string');
    expect(typeof root.allowReadWrite).toBe('boolean');
  });
});
