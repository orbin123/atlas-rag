import { useEffect, useState } from 'react';
import { ArrowLeft, Bookmark, Calendar, ChevronLeft, ChevronRight, FileText, Folder, HardDrive, Search, Server, User } from 'lucide-react';
import { getDocument, listDocumentChunks, listDocumentPages } from '../api/documents';
import type { DocumentChunk, DocumentDetail as Detail, DocumentPage, Paginated } from '../types';
import { formatBytes } from '../types';
import { ErrorNotice, LoadingNotice } from './AsyncNotice';

export default function DocumentDetail({ documentId, onBack }: { documentId: string; onBack: () => void }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [preview, setPreview] = useState<DocumentPage | null>(null);
  const [page, setPage] = useState(1);
  const [textKind, setTextKind] = useState<'cleaned' | 'raw'>('cleaned');
  const [chunks, setChunks] = useState<Paginated<DocumentChunk> | null>(null);
  const [chunkPage, setChunkPage] = useState(1);
  const [searchInput, setSearchInput] = useState('');
  const [chunkSearch, setChunkSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { const timer = window.setTimeout(() => { setChunkPage(1); setChunkSearch(searchInput.trim()); }, 300); return () => window.clearTimeout(timer); }, [searchInput]);
  useEffect(() => { setLoading(true); setError(null); getDocument(documentId).then(setDetail).catch(cause => setError(cause instanceof Error ? cause.message : 'Unable to load document.')).finally(() => setLoading(false)); }, [documentId]);
  useEffect(() => { listDocumentPages(documentId, page, textKind).then(result => setPreview(result.items[0] || null)).catch(cause => setError(cause instanceof Error ? cause.message : 'Unable to load page text.')); }, [documentId, page, textKind]);
  useEffect(() => { listDocumentChunks(documentId, chunkPage, chunkSearch).then(setChunks).catch(cause => setError(cause instanceof Error ? cause.message : 'Unable to load chunks.')); }, [documentId, chunkPage, chunkSearch]);

  if (loading) return <LoadingNotice label="Loading document detail…" />;
  if (!detail) return <ErrorNotice message={error || 'Document was not found.'} retry={onBack} />;
  return <div className="space-y-6 animate-fade-in" id="document-detail-page">
    <button onClick={onBack} className="flex items-center gap-1.5 text-[10px] font-bold font-mono text-slate-400 hover:text-teal-400 uppercase"><ArrowLeft className="w-4 h-4" />Back to Library</button>
    {error && <ErrorNotice message={error} />}
    <div className="bg-slate-900 border border-slate-800 p-5 rounded-xl flex gap-4"><div className="p-3 rounded bg-teal-500/10 text-teal-400"><FileText className="w-8 h-8" /></div><div className="min-w-0"><div className="flex flex-wrap gap-2 items-center"><h1 className="text-xl font-bold text-slate-200 break-all">{detail.name}</h1><span className={`text-[10px] uppercase font-mono ${detail.status === 'indexed' ? 'text-teal-400' : detail.status === 'failed' ? 'text-red-400' : 'text-amber-400'}`}>{detail.status}</span></div><p className="text-xs text-slate-400 mt-1">{detail.description || detail.title || 'No description supplied.'}</p><div className="flex flex-wrap gap-3 mt-3 text-[10px] font-mono"><span className="flex gap-1"><Folder className="w-3 h-3 text-teal-400" />{detail.domain}</span><span className="flex gap-1"><HardDrive className="w-3 h-3" />{formatBytes(detail.sizeBytes)}</span><span className="flex gap-1"><Calendar className="w-3 h-3" />{new Date(detail.createdAt).toLocaleString()}</span></div></div></div>
    {detail.failure && <ErrorNotice message={`${detail.failure.code}: ${detail.failure.message}`} />}
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <div className="lg:col-span-6 space-y-6">
        <div className="bg-slate-900 border border-slate-800 p-5 rounded-xl"><h2 className="text-[10px] font-bold tracking-widest text-slate-400 uppercase flex gap-2 mb-4"><Bookmark className="w-4 h-4 text-teal-400" />Indexing Properties</h2><div className="grid grid-cols-2 gap-3 text-xs"><Property icon={User} label="Author / Source" value={detail.author || detail.sourceKind} /><Property icon={FileText} label="Pages" value={String(detail.pageCount)} /><Property icon={Server} label="Chunks" value={String(detail.chunkCount)} /><Property icon={HardDrive} label="Embedding" value={`${detail.embedding.dimension}-D`} /><Property icon={Bookmark} label="Model" value={detail.embedding.model} /><Property icon={DatabaseIcon} label="Index Version" value={detail.indexVersion || 'Not indexed'} /></div></div>
        <div className="bg-slate-900 border border-slate-800 p-5 rounded-xl min-h-[360px]"><div className="flex flex-wrap justify-between gap-3 border-b border-slate-800 pb-3 mb-4"><h2 className="text-[10px] font-bold uppercase font-mono text-slate-400">Extracted text</h2><div className="flex items-center gap-2"><select value={textKind} onChange={event => setTextKind(event.target.value as 'cleaned' | 'raw')} className="bg-slate-950 border border-slate-700 rounded text-[10px] p-1"><option value="cleaned">Cleaned</option><option value="raw">Raw</option></select><button disabled={page <= 1} onClick={() => setPage(value => value - 1)} className="p-1 border border-slate-700 rounded disabled:opacity-30"><ChevronLeft className="w-3 h-3" /></button><span className="text-[10px] font-mono">Page {page} / {detail.pageCount}</span><button disabled={page >= detail.pageCount} onClick={() => setPage(value => value + 1)} className="p-1 border border-slate-700 rounded disabled:opacity-30"><ChevronRight className="w-3 h-3" /></button></div></div><div className="p-4 bg-slate-950 rounded border border-slate-800 text-xs text-slate-300 leading-relaxed whitespace-pre-wrap max-h-72 overflow-y-auto">{preview?.text || 'This page contains no extracted text.'}</div>{preview && <p className="mt-3 text-[10px] text-slate-500">{preview.characterCount.toLocaleString()} characters · {preview.repeatedLinesRemoved.length} repeated margin lines removed</p>}</div>
      </div>
      <div className="lg:col-span-6 space-y-4"><div className="bg-slate-900 border border-slate-800 p-4 rounded-xl"><div className="flex justify-between"><h2 className="text-[10px] font-bold uppercase font-mono text-slate-400">Vector chunks ({chunks?.total ?? 0})</h2><span className="text-[10px] text-teal-400 font-mono">{detail.embedding.dimension}-D</span></div><label className="relative block mt-3"><Search className="absolute left-3 top-2.5 w-3.5 h-3.5 text-slate-500" /><input value={searchInput} onChange={event => setSearchInput(event.target.value)} placeholder="Search stored chunk text" className="w-full bg-slate-950 border border-slate-700 rounded-lg pl-9 pr-3 py-2 text-xs" /></label></div><div className="space-y-3 max-h-[610px] overflow-y-auto">{chunks?.items.length === 0 && <div className="p-8 text-center bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-500">No chunks match this search.</div>}{chunks?.items.map(chunk => <article key={chunk.id} className="p-4 bg-slate-900 border border-slate-800 rounded-xl"><div className="flex justify-between text-[10px] font-mono"><span className="text-teal-400">Chunk #{chunk.chunkIndex}</span><span>Page {chunk.pageNumber} · {chunk.status}</span></div><p className="mt-2 p-3 bg-slate-950 rounded text-[11px] leading-relaxed whitespace-pre-wrap">{chunk.text}</p><p className="mt-2 text-[10px] text-slate-500 font-mono">{chunk.tokenCount} tokens · ID {chunk.id}</p></article>)}</div>{chunks && chunks.totalPages > 1 && <div className="flex justify-center items-center gap-3 text-xs"><button disabled={chunkPage <= 1} onClick={() => setChunkPage(value => value - 1)} className="px-2 py-1 border border-slate-700 rounded disabled:opacity-30">Previous</button><span>{chunkPage} / {chunks.totalPages}</span><button disabled={chunkPage >= chunks.totalPages} onClick={() => setChunkPage(value => value + 1)} className="px-2 py-1 border border-slate-700 rounded disabled:opacity-30">Next</button></div>}</div>
    </div>
  </div>;
}

const DatabaseIcon = Server;
function Property({ icon: Icon, label, value }: { icon: typeof User; label: string; value: string }) { return <div className="p-3 bg-slate-950 rounded border border-slate-800 min-w-0"><p className="text-[9px] text-slate-500 uppercase flex gap-1"><Icon className="w-3 h-3 text-teal-400" />{label}</p><p className="text-slate-200 mt-1 truncate" title={value}>{value}</p></div>; }
