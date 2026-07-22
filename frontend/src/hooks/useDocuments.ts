import { useCallback, useEffect, useState } from 'react';
import { getDocumentStats, listDocuments } from '../api/documents';
import type { DocumentStats, DocumentSummary } from '../types';

export function useDocuments() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [stats, setStats] = useState<DocumentStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [list, nextStats] = await Promise.all([listDocuments({ pageSize: 100 }), getDocumentStats()]);
      setDocuments(list.items); setStats(nextStats);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to load documents.'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void reload(); }, [reload]);
  return { documents, stats, loading, error, reload };
}
