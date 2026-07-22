import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiRequest, queryString } from './client';

afterEach(() => vi.unstubAllGlobals());

describe('apiRequest', () => {
  it('returns camelCase JSON from a successful response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ documentCount: 60 }), { status: 200, headers: { 'Content-Type': 'application/json' } })));
    await expect(apiRequest<{ documentCount: number }>('/system/info')).resolves.toEqual({ documentCount: 60 });
  });

  it('preserves the backend error envelope', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'INDEX_NOT_READY', message: 'Index unavailable.', details: null, requestId: 'req-1' } }), { status: 503, headers: { 'Content-Type': 'application/json' } })));
    const error = await apiRequest('/documents').catch(cause => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).body).toMatchObject({ code: 'INDEX_NOT_READY', requestId: 'req-1' });
  });

  it('maps connection failures to a typed network error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    await expect(apiRequest('/documents')).rejects.toMatchObject({ status: 0, body: { code: 'NETWORK_ERROR' } });
  });
});

it('builds encoded query strings without empty values', () => {
  expect(queryString({ page: 1, search: 'climate risk', domain: null })).toBe('?page=1&search=climate+risk');
});
