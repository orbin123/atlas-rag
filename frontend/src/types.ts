export interface Document {
  id: string;
  name: string;
  type: 'pdf' | 'docx' | 'txt';
  domain: string;
  pages: number;
  chunksCount: number;
  uploadDate: string;
  status: 'indexed' | 'processing' | 'failed';
  fileSize: string;
  author?: string;
  description?: string;
  extractedTextPreview?: string;
}

export interface Chunk {
  id: string;
  documentId: string;
  documentName: string;
  chunkNumber: number;
  pageNumber: number;
  text: string;
  similarityScore?: number; // Used for retrieved results
  status: 'indexed' | 'pending';
  tokenCount: number;
}

export interface Message {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  timestamp: string;
  citations?: {
    documentName: string;
    page: number;
    chunkIndex: number;
  }[];
  isInsufficientContext?: boolean;
}

export interface EvalMetric {
  name: string;
  value: string | number;
  change: string;
  changeType: 'increase' | 'decrease' | 'neutral';
  description: string;
}

export interface FailureAnalysis {
  id: string;
  question: string;
  expectedSource: string;
  retrievedSource: string;
  result: string;
  category: 'Irrelevant Chunk' | 'Incomplete Answer' | 'Hallucination' | 'No Context Retrieved';
}

export interface PresetQA {
  question: string;
  answer: string;
  citations: { documentName: string; page: number; chunkIndex: number }[];
  retrievedChunks: Chunk[];
}
