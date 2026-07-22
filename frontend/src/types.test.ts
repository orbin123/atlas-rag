import { describe, expect, it } from 'vitest';
import { formatBytes, formatPercent, isTerminalJob } from './types';

describe('truthful UI formatters', () => {
  it('formats byte counts sent by the API', () => { expect(formatBytes(1536)).toBe('1.50 KB'); expect(formatBytes(0)).toBe('0 B'); });
  it('keeps nullable metrics unavailable', () => { expect(formatPercent(null)).toBe('N/A'); expect(formatPercent(0.966667)).toBe('96.7%'); });
  it('recognizes durable terminal states', () => { expect(isTerminalJob('succeeded')).toBe(true); expect(isTerminalJob('running')).toBe(false); });
});
