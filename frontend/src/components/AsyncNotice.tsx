import { AlertTriangle, Loader2, RefreshCw } from 'lucide-react';

export function LoadingNotice({ label = 'Loading from Atlas API…' }: { label?: string }) {
  return <div className="p-6 rounded-xl border border-slate-800 bg-slate-900 text-sm text-slate-400 flex items-center gap-3"><Loader2 className="w-4 h-4 animate-spin text-teal-400" />{label}</div>;
}

export function ErrorNotice({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="p-4 rounded-xl border border-red-500/30 bg-red-950/20 text-sm text-red-200 flex items-center justify-between gap-4"><span className="flex items-center gap-2"><AlertTriangle className="w-4 h-4 shrink-0" />{message}</span>{retry && <button onClick={retry} className="flex items-center gap-1 text-xs px-3 py-1.5 rounded border border-red-400/30 hover:bg-red-500/10"><RefreshCw className="w-3 h-3" />Retry</button>}</div>;
}
