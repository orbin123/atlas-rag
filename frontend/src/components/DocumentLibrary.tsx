import { useEffect, useMemo, useState } from 'react';
import type { LucideIcon } from 'lucide-react';
import { BookOpen, Calendar, CheckCircle, Eye, FileText, Folder, Layers, Plus, Search, Server, Trash2 } from 'lucide-react';
import { deleteDocument } from '../api/documents';
import { ErrorNotice, LoadingNotice } from './AsyncNotice';
import { useIngestionJob } from '../hooks/useIngestionJob';
import type { DocumentStats, DocumentSummary } from '../types';
import { formatBytes, isTerminalJob } from '../types';

interface Props {
  documents: DocumentSummary[];
  stats: DocumentStats | null;
  loading: boolean;
  error: string | null;
  onReload: () => Promise<void>;
  onSelectDocument: (id: string) => void;
  onNavigateToUpload: () => void;
}

export default function DocumentLibrary({ documents, stats, loading, error, onReload, onSelectDocument, onNavigateToUpload }: Props) {
  const [search, setSearch] = useState('');
  const [domain, setDomain] = useState('All');
  const [deleteJobId, setDeleteJobId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const { job: deleteJob, error: jobError } = useIngestionJob(deleteJobId);

  useEffect(() => {
    if (deleteJob && isTerminalJob(deleteJob.status) && deleteJobId) {
      setDeleteJobId(null); setDeletingId(null);
      if (deleteJob.status === 'succeeded') void onReload();
      else setActionError(deleteJob.error?.message || `Deletion ended with status ${deleteJob.status}.`);
    }
  }, [deleteJob, deleteJobId, onReload]);

  const domains = ['All', ...Array.from(new Set(documents.map(item => item.domain))).sort()];
  const filtered = useMemo(() => documents.filter(item => {
    const term = search.trim().toLowerCase();
    return (domain === 'All' || item.domain === domain) && (!term || [item.name, item.description || '', item.author || ''].some(value => value.toLowerCase().includes(term)));
  }), [documents, search, domain]);
  const statCards: [string, number, string, LucideIcon][] = [
    ['Total Corpus', stats?.totalDocuments ?? 0, 'Documents', FileText],
    ['Parsed Pages', stats?.totalPages ?? 0, 'Stored page records', Layers],
    ['FAISS Vectors', stats?.indexHealth.vectorCount ?? 0, stats?.indexHealth.status || 'unknown', Server],
    ['Indexed', stats?.indexedDocuments ?? 0, `${stats?.processingDocuments ?? 0} processing · ${stats?.failedDocuments ?? 0} failed`, CheckCircle],
  ];

  const remove = async (document: DocumentSummary) => {
    if (!window.confirm(`Delete ${document.name} from the corpus and vector index?`)) return;
    setActionError(null); setDeletingId(document.id);
    try { const accepted = await deleteDocument(document.id); setDeleteJobId(accepted.jobId); }
    catch (cause) { setDeletingId(null); setActionError(cause instanceof Error ? cause.message : 'Deletion could not be started.'); }
  };

  return <div className="space-y-6 animate-fade-in" id="document-library-page">
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4"><div><h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2"><BookOpen className="w-6 h-6 text-teal-400" />Document Library</h1><p className="text-xs text-slate-400">Real documents and index state from the Atlas API.</p></div><button onClick={onNavigateToUpload} className="flex items-center justify-center gap-2 bg-teal-500 hover:bg-teal-400 text-slate-950 text-xs font-bold py-2.5 px-4 rounded-lg uppercase"><Plus className="w-4 h-4" />Ingest New Document</button></div>
    {error && <ErrorNotice message={error} retry={() => void onReload()} />}
    {(actionError || jobError) && <ErrorNotice message={actionError || jobError || ''} />}
    {deleteJob && !isTerminalJob(deleteJob.status) && <div className="p-3 border border-amber-500/30 bg-amber-950/20 rounded-lg text-xs text-amber-200">Deleting document: {deleteJob.stageMessage || deleteJob.stage || deleteJob.status} ({deleteJob.progressPercent}%)</div>}
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {statCards.map(([label, value, note, Icon]) => <div key={label} className="bg-slate-900 border border-slate-800 p-4 rounded-xl"><Icon className="w-5 h-5 text-teal-400 mb-2" /><p className="text-[10px] uppercase font-mono tracking-widest text-slate-500">{label}</p><p className="text-2xl font-bold text-slate-200">{value.toLocaleString()}</p><p className="text-[10px] text-slate-400">{note}</p></div>)}
    </div>
    <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl flex flex-col md:flex-row gap-3 justify-between">
      <label className="relative flex-1 max-w-md"><Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-500" /><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search name, description, or author" className="w-full bg-slate-950 border border-slate-700 rounded-lg pl-10 pr-4 py-2 text-xs" /></label>
      <select value={domain} onChange={event => setDomain(event.target.value)} className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs">{domains.map(value => <option key={value}>{value}</option>)}</select>
    </div>
    {loading ? <LoadingNotice label="Loading document library…" /> : <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
      {filtered.length === 0 ? <div className="py-16 text-center text-sm text-slate-500">No documents match the current filters.</div> : <div className="overflow-x-auto"><table className="w-full text-left"><thead><tr className="bg-slate-950 text-[10px] uppercase font-mono text-slate-500"><th className="p-4">Document</th><th className="p-4">Domain</th><th className="p-4">Pages / Chunks</th><th className="p-4">Indexed</th><th className="p-4">Size</th><th className="p-4">Status</th><th className="p-4 text-right">Actions</th></tr></thead><tbody className="divide-y divide-slate-800">{filtered.map(item => <tr key={item.id} className="hover:bg-slate-800/30"><td className="p-4"><button onClick={() => onSelectDocument(item.id)} className="text-left"><span className="text-xs font-semibold text-slate-200 hover:text-teal-400 flex items-center gap-2"><FileText className="w-4 h-4" />{item.name}</span><span className="block text-[10px] text-slate-500 max-w-xs truncate">{item.description || item.mimeType}</span></button></td><td className="p-4 text-xs"><span className="flex gap-1"><Folder className="w-3 h-3 text-teal-400" />{item.domain}</span></td><td className="p-4 text-xs font-mono">{item.pageCount} / <span className="text-teal-400">{item.chunkCount}</span></td><td className="p-4 text-xs text-slate-400"><span className="flex gap-1"><Calendar className="w-3 h-3" />{item.indexedAt ? new Date(item.indexedAt).toLocaleDateString() : '—'}</span></td><td className="p-4 text-xs font-mono">{formatBytes(item.sizeBytes)}</td><td className="p-4"><span className={`text-[10px] uppercase font-mono ${item.status === 'indexed' ? 'text-teal-400' : item.status === 'failed' ? 'text-red-400' : 'text-amber-400'}`}>{item.status}</span></td><td className="p-4"><div className="flex justify-end gap-2"><button onClick={() => onSelectDocument(item.id)} title="Inspect" className="p-1.5 rounded border border-slate-700"><Eye className="w-3.5 h-3.5" /></button><button disabled={deletingId !== null} onClick={() => void remove(item)} title="Delete" className="p-1.5 rounded border border-slate-700 hover:text-red-400 disabled:opacity-40"><Trash2 className="w-3.5 h-3.5" /></button></div></td></tr>)}</tbody></table></div>}
    </div>}
  </div>;
}
