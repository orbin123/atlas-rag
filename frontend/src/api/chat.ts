import { apiRequest, queryString } from './client';
import type { ChatResponse, RetrievalDetail, Suggestion } from '../types';
export const createChatQuery = (question: string, topK?: number, domain?: string) => apiRequest<ChatResponse>('/chat/queries', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, topK, domain: domain || null }) });
export const listSuggestions = (limit = 4) => apiRequest<Suggestion[]>(`/chat/suggestions${queryString({ limit })}`);
export const getRetrievalDetail = (queryId: string) => apiRequest<RetrievalDetail>(`/retrieval/${encodeURIComponent(queryId)}`);
