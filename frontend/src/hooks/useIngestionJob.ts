import { useEffect, useState } from 'react';
import { getIngestionJob } from '../api/documents';
import type { IngestionJob } from '../types';
import { isTerminalJob } from '../types';

export function useIngestionJob(jobId: string | null) {
  const [job, setJob] = useState<IngestionJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!jobId) { setJob(null); setError(null); return; }
    let cancelled = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const next = await getIngestionJob(jobId);
        if (cancelled) return;
        setJob(next); setError(null);
        if (!isTerminalJob(next.status)) timer = window.setTimeout(() => void poll(), 1000);
      } catch (cause) {
        if (!cancelled) { setError(cause instanceof Error ? cause.message : 'Unable to read job status.'); timer = window.setTimeout(() => void poll(), 2000); }
      }
    };
    void poll();
    return () => { cancelled = true; if (timer) window.clearTimeout(timer); };
  }, [jobId]);
  return { job, error };
}
