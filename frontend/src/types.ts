export type DocumentStatus = 'queued' | 'processing' | 'indexed' | 'failed' | 'deleting';
export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';

export interface Paginated<T> {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}

export interface DocumentSummary {
  id: string;
  name: string;
  fileType: 'pdf' | 'docx' | 'txt';
  mimeType: string;
  domain: string;
  pageCount: number;
  chunkCount: number;
  createdAt: string;
  indexedAt: string | null;
  status: DocumentStatus;
  sizeBytes: number;
  author: string | null;
  description: string | null;
  sourceUrl: string | null;
  licenseNote: string | null;
}

export interface DocumentDetail extends DocumentSummary {
  title: string | null;
  sourceKind: 'bootstrap' | 'upload';
  relativeSourcePath: string | null;
  failure: { code: string; message: string } | null;
  activeJobId: string | null;
  updatedAt: string;
  indexVersion: string | null;
  embedding: { model: string; revision: string; dimension: number };
}

export interface DocumentStats {
  totalDocuments: number;
  totalPages: number;
  totalChunks: number;
  indexedDocuments: number;
  processingDocuments: number;
  failedDocuments: number;
  deletingDocuments: number;
  domainCounts: { value: string; count: number }[];
  fileTypeCounts: { value: string; count: number }[];
  indexHealth: { status: 'ready' | 'not_ready' | 'inconsistent'; vectorCount: number };
}

export interface DocumentPage {
  id: string;
  documentId: string;
  pageNumber: number;
  text: string;
  textKind: 'cleaned' | 'raw';
  characterCount: number;
  isEmpty: boolean;
  repeatedLinesRemoved: string[];
}

export interface DocumentChunk {
  id: string;
  documentId: string;
  documentName: string;
  chunkIndex: number;
  pageNumber: number;
  text: string;
  tokenCount: number;
  status: string;
  embeddingDimension: number;
}

export interface AcceptedJob {
  jobId: string;
  documentId: string;
  status: string;
  statusUrl: string;
}

export interface IngestionJob {
  id: string;
  documentId: string | null;
  kind: string;
  status: JobStatus;
  stage: string | null;
  progressPercent: number;
  stageMessage: string | null;
  attempt: number;
  maxAttempts: number;
  result: Record<string, unknown> | null;
  error: { code: string; message: string } | null;
  createdAt: string;
  startedAt: string | null;
  heartbeatAt: string | null;
  updatedAt: string;
  completedAt: string | null;
}

export interface SystemInfo {
  corpus: { documentCount: number; pageCount: number; chunkCount: number };
  index: { status: string; type: string; version: string | null; vectorCount: number; dimension: number };
  embedding: { model: string; revision: string; dimension: number; maxInputTokens: number };
  chunking: { version: string; targetTokens: number; maxTokens: number; overlapTokens: number };
  retrieval: { defaultTopK: number; maximumTopK: number; minimumContextScore: number; duplicateSimilarityThreshold: number; rerankerEnabled: boolean };
  generation: { enabled: boolean; ready: boolean; provider: string; model: string | null; timeoutSeconds: number; maximumConcurrentRequests: number };
  capabilities: { ocr: boolean; supportedFileTypes: string[]; maximumUploadBytes: number };
}

export interface ChatSource {
  label: string;
  chunkId: string;
  documentId: string;
  documentName: string;
  domain: string;
  pageNumber: number;
  chunkIndex: number;
  text: string;
  tokenCount: number;
  similarityScore: number;
  rank: number;
}

export interface ChatResponse {
  queryId: string;
  question: string;
  answer: string;
  insufficientContext: boolean;
  insufficientReason: string | null;
  citations: { label: string; documentId: string; documentName: string; pageNumber: number; chunkIndex: number }[];
  sources: ChatSource[];
  timing: { retrievalMs: number; generationMs: number; totalMs: number };
  config: { topK: number; minimumContextScore: number; indexVersion: string };
}

export interface RetrievalDetail {
  queryId: string;
  question: string;
  status: string;
  insufficientContext: boolean;
  sources: ChatSource[];
  timing: { retrievalMs: number };
  config: { topK: number; domain: string | null; minimumContextScore: number; indexVersion: string | null };
  createdAt: string;
}

export interface Suggestion { id: string; question: string; domain: string }

export interface EvaluationMetrics {
  recallAt1: number | null;
  recallAt3: number | null;
  recallAt5: number | null;
  recallAt10: number | null;
  mrr: number | null;
  meanRetrievalLatencyMs: number | null;
  fallbackAccuracy: number | null;
  citationRate: number | null;
  answerCorrectness: number | null;
  groundedness: number | null;
}

export interface EvaluationRun {
  id: string;
  mode: string;
  status: string;
  progressPercent: number;
  datasetVersion: string;
  datasetHash: string;
  indexVersion: string | null;
  evaluatedQuestions: number;
  totalQuestions: number;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  metrics: EvaluationMetrics;
}

export interface EvaluationDomain extends EvaluationMetrics {
  domain: string;
  documentCount: number;
  questionCount: number;
}

export interface EvaluationFailure {
  id: string;
  evaluationId: string;
  question: string;
  domain: string;
  category: string;
  expectedDocumentName: string | null;
  expectedPageNumber: number | null;
  retrievedDocumentName: string | null;
  retrievedPageNumber: number | null;
  firstRelevantRank: number | null;
  topScore: number | null;
  summary: string;
}

export interface EvaluationLatest { run: EvaluationRun; domains: EvaluationDomain[]; failures: EvaluationFailure[] }

export interface EvaluationAccepted { runId: string; jobId: string; status: string; statusUrl: string }

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  timestamp: string;
  response?: ChatResponse;
  error?: string;
}

export const isTerminalJob = (status: string) => ['succeeded', 'failed', 'cancelled'].includes(status);

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return `${value.toFixed(value >= 10 ? 1 : 2)} ${units[unit]}`;
}

export const formatPercent = (value: number | null, digits = 1) => value === null ? 'N/A' : `${(value * 100).toFixed(digits)}%`;
