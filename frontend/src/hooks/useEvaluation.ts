import { useCallback, useEffect, useState } from 'react';
import { createEvaluationRun, getEvaluationRun, getLatestEvaluation } from '../api/evaluation';
import type { EvaluationLatest, EvaluationRun } from '../types';

export function useEvaluation() {
  const [latest, setLatest] = useState<EvaluationLatest | null>(null);
  const [activeRun, setActiveRun] = useState<EvaluationRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setLatest(await getLatestEvaluation()); }
    catch (cause) { setLatest(null); setError(cause instanceof Error ? cause.message : 'No evaluation results are available.'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const run = useCallback(async () => {
    setRunning(true); setError(null);
    try {
      const accepted = await createEvaluationRun();
      for (;;) {
        const next = await getEvaluationRun(accepted.runId);
        setActiveRun(next);
        if (['succeeded', 'failed', 'cancelled'].includes(next.status)) {
          if (next.status !== 'succeeded') throw new Error(`Evaluation ended with status ${next.status}.`);
          break;
        }
        await new Promise(resolve => window.setTimeout(resolve, 1000));
      }
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Evaluation failed.'); }
    finally { setRunning(false); }
  }, [load]);
  return { latest, activeRun, loading, running, error, run, reload: load };
}
