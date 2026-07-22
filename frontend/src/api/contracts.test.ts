import { afterEach, describe, expect, it, vi } from 'vitest';
import { createChatQuery, getRetrievalDetail } from './chat';
import { deleteDocument, listDocumentChunks, uploadDocument } from './documents';
import { createEvaluationRun, getLatestEvaluation } from './evaluation';

afterEach(() => vi.unstubAllGlobals());

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('frontend API contracts', () => {
  it('uses the versioned document detail routes and camelCase pagination', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ items: [], page: 2, pageSize: 25, total: 0, totalPages: 0 }));
    vi.stubGlobal('fetch', fetchMock);
    await listDocumentChunks('doc/id', 2, 'risk & policy');
    expect(String(fetchMock.mock.calls[0][0])).toContain('/documents/doc%2Fid/chunks?page=2&pageSize=25&search=risk+%26+policy');
  });

  it('sends the real file and optional upload metadata as multipart data', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ jobId: 'job-1', documentId: 'doc-1', status: 'queued', statusUrl: '/api/v1/ingestion-jobs/job-1' }, 202));
    vi.stubGlobal('fetch', fetchMock);
    const file = new File(['Atlas text'], 'atlas.txt', { type: 'text/plain' });
    await uploadDocument(file, { domain: 'Education', title: 'Atlas Notes', sourceUrl: 'https://example.test/source' });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(init.body).toBeInstanceOf(FormData);
    const form = init.body as FormData;
    expect((form.get('file') as File).name).toBe('atlas.txt');
    expect(form.get('domain')).toBe('Education');
    expect(form.get('sourceUrl')).toBe('https://example.test/source');
  });

  it('calls durable deletion, grounded chat, and evaluation endpoints', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ jobId: 'delete-1', documentId: 'doc-1', status: 'queued', statusUrl: '/api/v1/ingestion-jobs/delete-1' }, 202))
      .mockResolvedValueOnce(jsonResponse({ queryId: 'query-1' }))
      .mockResolvedValueOnce(jsonResponse({ runId: 'run-1', jobId: 'job-2', status: 'queued', statusUrl: '/api/v1/evaluation/runs/run-1' }, 202))
      .mockResolvedValueOnce(jsonResponse({ run: { id: 'run-1' }, domains: [], failures: [] }))
      .mockResolvedValueOnce(jsonResponse({ queryId: 'query-1', sources: [] }));
    vi.stubGlobal('fetch', fetchMock);
    await deleteDocument('doc-1');
    await createChatQuery('What is indexed?', 5, 'Education');
    await createEvaluationRun();
    await getLatestEvaluation();
    await getRetrievalDetail('query/1');
    expect(fetchMock.mock.calls.map(call => [new URL(String(call[0])).pathname, (call[1] as RequestInit).method || 'GET'])).toEqual([
      ['/api/v1/documents/doc-1', 'DELETE'],
      ['/api/v1/chat/queries', 'POST'],
      ['/api/v1/evaluation/runs', 'POST'],
      ['/api/v1/evaluation/latest', 'GET'],
      ['/api/v1/retrieval/query%2F1', 'GET'],
    ]);
    expect(JSON.parse(String((fetchMock.mock.calls[1][1] as RequestInit).body))).toEqual({ question: 'What is indexed?', topK: 5, domain: 'Education' });
  });
});
