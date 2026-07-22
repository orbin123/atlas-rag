import { apiRequest, queryString } from './client';
import type { AcceptedJob, DocumentChunk, DocumentDetail, DocumentPage, DocumentStats, DocumentSummary, IngestionJob, Paginated } from '../types';

export const listDocuments = (filters: { page?: number; pageSize?: number; search?: string; domain?: string; fileType?: string; status?: string } = {}) =>
  apiRequest<Paginated<DocumentSummary>>(`/documents${queryString(filters)}`);
export const getDocumentStats = () => apiRequest<DocumentStats>('/documents/stats');
export const getDocument = (id: string) => apiRequest<DocumentDetail>(`/documents/${encodeURIComponent(id)}`);
export const listDocumentPages = (id: string, page = 1, text: 'cleaned' | 'raw' = 'cleaned') =>
  apiRequest<Paginated<DocumentPage>>(`/documents/${encodeURIComponent(id)}/pages${queryString({ page, pageSize: 1, text })}`);
export const listDocumentChunks = (id: string, page = 1, search = '') =>
  apiRequest<Paginated<DocumentChunk>>(`/documents/${encodeURIComponent(id)}/chunks${queryString({ page, pageSize: 25, search })}`);
export const deleteDocument = (id: string) => apiRequest<AcceptedJob>(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' });
export const getIngestionJob = (id: string) => apiRequest<IngestionJob>(`/ingestion-jobs/${encodeURIComponent(id)}`);

export interface UploadMetadata { domain: string; title?: string; author?: string; sourceUrl?: string; licenseNote?: string; evaluationQuestions?: string[] }
export function uploadDocument(file: File, metadata: UploadMetadata): Promise<AcceptedJob> {
  const body = new FormData();
  body.append('file', file, file.name);
  Object.entries(metadata).forEach(([key, value]) => {
    if (key === 'evaluationQuestions' && Array.isArray(value) && value.length) body.append(key, JSON.stringify(value));
    else if (typeof value === 'string' && value.trim()) body.append(key, value.trim());
  });
  return apiRequest<AcceptedJob>('/documents/upload', { method: 'POST', body });
}
