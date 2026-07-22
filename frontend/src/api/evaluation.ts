import { apiRequest } from './client';
import type { EvaluationAccepted, EvaluationLatest, EvaluationRun } from '../types';
export const getLatestEvaluation = () => apiRequest<EvaluationLatest>('/evaluation/latest');
export const createEvaluationRun = () => apiRequest<EvaluationAccepted>('/evaluation/runs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode: 'retrieval' }) });
export const getEvaluationRun = (id: string) => apiRequest<EvaluationRun>(`/evaluation/runs/${encodeURIComponent(id)}`);
