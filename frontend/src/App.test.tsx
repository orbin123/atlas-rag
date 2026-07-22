import { describe, expect, it } from 'vitest';
import { runtimeStatusText } from './App';
import type { SystemInfo } from './types';

function system(overrides: Partial<SystemInfo['generation']> = {}, indexStatus = 'ready') {
  return {
    index: { status: indexStatus },
    generation: { enabled: false, ready: false, model: null, ...overrides },
  } as SystemInfo;
}

describe('runtimeStatusText', () => {
  it('never claims retrieval readiness before the backend reports a ready index', () => {
    expect(runtimeStatusText(null)).toBe('API STATUS UNAVAILABLE');
    expect(runtimeStatusText(system({}, 'not_ready'))).toBe('INDEX NOT_READY');
  });

  it('distinguishes disabled, unavailable, and ready generation', () => {
    expect(runtimeStatusText(system())).toBe('RETRIEVAL READY · GENERATION NOT CONFIGURED');
    expect(runtimeStatusText(system({ enabled: true }))).toBe(
      'RETRIEVAL READY · GENERATION UNAVAILABLE',
    );
    expect(runtimeStatusText(system({ enabled: true, ready: true, model: 'local-model' }))).toBe(
      'GENERATION READY · local-model',
    );
  });
});
