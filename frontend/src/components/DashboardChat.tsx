import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, ArrowRight, Bookmark, ChevronRight, Database, FileText, Folder, HelpCircle, Loader2, RotateCcw, Search, Send, Sparkles } from 'lucide-react';
import { createChatQuery, getRetrievalDetail, listSuggestions } from '../api/chat';
import { ApiError } from '../api/client';
import type { ChatMessage, ChatSource, DocumentSummary, Suggestion, SystemInfo } from '../types';
import { ErrorNotice, LoadingNotice } from './AsyncNotice';

type ViewMode = 'just-stay' | 'index' | 'chat' | 'evidence';
interface Props { documents: DocumentSummary[]; documentsLoading: boolean; documentsError: string | null; system: SystemInfo | null; onReload: () => Promise<void>; onNavigateToUpload: () => void; onSelectDocument: (id: string) => void; viewMode: ViewMode; setViewMode: (mode: ViewMode) => void }

const welcomeMessage = (): ChatMessage => ({ id: 'welcome', sender: 'assistant', text: 'Welcome to Atlas RAG. Ask a question to retrieve evidence from the local corpus. Supported answers require a configured generation provider; low-evidence questions return the deterministic safety fallback.', timestamp: 'Ready' });

export default function DashboardChat({ documents, documentsLoading, documentsError, system, onReload, onNavigateToUpload, onSelectDocument, viewMode, setViewMode }: Props) {
  const [search, setSearch] = useState('');
  const [domain, setDomain] = useState('All');
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([welcomeMessage()]);
  const [sources, setSources] = useState<ChatSource[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [suggestionError, setSuggestionError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { listSuggestions(4).then(setSuggestions).catch(cause => setSuggestionError(cause instanceof Error ? cause.message : 'Suggestions are unavailable.')); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, searching]);
  const domains = ['All', ...Array.from(new Set(documents.map(item => item.domain))).sort()];
  const filtered = useMemo(() => documents.filter(item => (domain === 'All' || item.domain === domain) && (!search.trim() || item.name.toLowerCase().includes(search.trim().toLowerCase()))), [documents, domain, search]);
  const showLeft = viewMode === 'just-stay' || viewMode === 'index';
  const showCenter = viewMode === 'just-stay' || viewMode === 'chat';
  const showRight = viewMode === 'just-stay' || viewMode === 'evidence';

  const ask = async (question: string) => {
    const trimmed = question.trim(); if (!trimmed || searching) return;
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    setMessages(value => [...value, { id: crypto.randomUUID(), sender: 'user', text: trimmed, timestamp }]); setInput(''); setSearching(true);
    try {
      const response = await createChatQuery(trimmed, system?.retrieval.defaultTopK, domain === 'All' ? undefined : domain);
      setSources(response.sources);
      setMessages(value => [...value, { id: response.queryId, sender: 'assistant', text: response.answer, timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), response }]);
    } catch (cause) {
      let message = cause instanceof Error ? cause.message : 'The query failed.';
      if (cause instanceof ApiError && cause.body.code === 'GENERATION_PROVIDER_UNAVAILABLE') {
        const details = cause.body.details;
        const queryId = details && !Array.isArray(details) && typeof details.queryId === 'string' ? details.queryId : null;
        if (queryId) {
          try {
            const retrieval = await getRetrievalDetail(queryId);
            setSources(retrieval.sources);
            message = `Evidence was found (${retrieval.sources.length} source chunks), but answer generation is not configured. The retrieved evidence remains available for inspection.`;
          } catch {
            message = 'Evidence was found, but answer generation is not configured and the persisted retrieval details could not be reopened.';
          }
        } else {
          message = 'Evidence was found, but answer generation is not configured.';
        }
      }
      setMessages(value => [...value, { id: crypto.randomUUID(), sender: 'assistant', text: message, timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), error: message }]);
    } finally { setSearching(false); }
  };

  const retry = () => {
    if (searching) return;
    setInput('');
    setSearch('');
    setDomain('All');
    setSources([]);
    setMessages([welcomeMessage()]);
    setViewMode('just-stay');
  };

  return <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 h-[calc(100vh-130px)] min-h-[560px]">
    {showLeft && <section className={`${viewMode === 'just-stay' ? 'lg:col-span-3' : 'lg:col-span-12'} bg-slate-900 border border-slate-800 rounded-xl flex flex-col overflow-hidden`}><PanelHeader title="Index Core Packs" action={viewMode !== 'just-stay' ? () => setViewMode('just-stay') : undefined} /><div className="p-3 border-b border-slate-800 space-y-2"><label className="relative block"><Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-500" /><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search real documents" className="w-full bg-slate-950 border border-slate-700 rounded-lg pl-9 py-2 pr-3 text-xs" /></label><select value={domain} onChange={event => setDomain(event.target.value)} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-2 text-xs">{domains.map(value => <option key={value}>{value}</option>)}</select></div><div className="flex-1 overflow-y-auto p-3 space-y-2">{documentsLoading && <LoadingNotice label="Loading corpus…" />}{documentsError && <ErrorNotice message={documentsError} retry={() => void onReload()} />}{filtered.map(item => <button key={item.id} onClick={() => onSelectDocument(item.id)} className="w-full text-left p-3 rounded-lg bg-slate-800/40 hover:bg-slate-800 border border-slate-800"><div className="flex justify-between gap-2"><span className="text-xs font-semibold truncate">{item.name}</span><span className="text-[9px] uppercase text-teal-400">{item.status}</span></div><div className="flex justify-between mt-1 text-[10px] text-slate-400"><span className="flex gap-1"><Folder className="w-3 h-3" />{item.domain}</span><span>{item.pageCount} pages</span></div></button>)}</div><div className="p-3 border-t border-slate-800"><button onClick={onNavigateToUpload} className="w-full flex justify-center items-center gap-2 bg-teal-500 text-slate-950 text-xs font-bold py-2 rounded">Upload a document<ArrowRight className="w-3 h-3" /></button></div></section>}
    {showCenter && <section className={`${viewMode === 'just-stay' ? 'lg:col-span-6' : 'lg:col-span-12'} bg-slate-950 border border-slate-800 rounded-xl flex flex-col overflow-hidden`}><div className="p-4 border-b border-slate-800 flex justify-between"><div className="flex gap-2 items-center"><Sparkles className="w-4 h-4 text-teal-400" /><div><h2 className="text-sm font-bold uppercase font-mono">Grounded Synthesis</h2><p className="text-[10px] text-slate-500">{system?.generation.ready ? `Generation ready · ${system.generation.model}` : 'Retrieval ready · generation not configured'}</p></div></div>{viewMode !== 'just-stay' && <button onClick={() => setViewMode('just-stay')} className="text-[10px] text-teal-400">Standard layout</button>}</div><div className="flex-1 overflow-y-auto p-4 space-y-4">{messages.map(message => <article key={message.id} className={`max-w-[88%] ${message.sender === 'user' ? 'ml-auto' : ''}`}><p className="text-[9px] text-slate-500 mb-1">{message.sender === 'user' ? 'Researcher' : 'Atlas'} · {message.timestamp}</p><div className={`p-4 rounded-xl text-xs whitespace-pre-wrap leading-relaxed ${message.sender === 'user' ? 'bg-slate-800 border border-slate-700' : message.error || message.response?.insufficientContext ? 'bg-red-950/20 border border-red-500/30' : 'bg-slate-900 border border-slate-800'}`}>{message.response?.insufficientContext && <p className="mb-2 text-red-400 uppercase font-bold flex gap-2"><AlertTriangle className="w-4 h-4" />Insufficient context</p>}<SafeAnswer text={message.text} />{message.error && <button type="button" onClick={retry} disabled={searching} className="mt-3 inline-flex items-center gap-1.5 rounded border border-teal-400/40 px-2.5 py-1.5 text-[10px] font-bold text-teal-300 hover:bg-teal-400/10 disabled:opacity-40"><RotateCcw className="h-3 w-3" />Retry chat</button>}{message.response && <div className="mt-3 pt-3 border-t border-slate-800"><p className="text-[9px] text-slate-500 font-mono">Retrieval {message.response.timing.retrievalMs.toFixed(1)} ms · Generation {message.response.timing.generationMs.toFixed(1)} ms · threshold {message.response.config.minimumContextScore}</p><div className="flex flex-wrap gap-1 mt-2">{message.response.citations.map(citation => <button key={citation.label} onClick={() => onSelectDocument(citation.documentId)} className="text-[10px] px-2 py-1 bg-teal-500/10 text-teal-300 border border-teal-500/20 rounded"><Bookmark className="inline w-3 h-3 mr-1" />{citation.label} · {citation.documentName} p.{citation.pageNumber}</button>)}</div></div>}</div></article>)}{searching && <div className="flex gap-2 items-center text-xs text-slate-400"><Loader2 className="w-4 h-4 animate-spin text-teal-400" />Embedding, retrieving, and applying the context gate…</div>}<div ref={endRef} /></div>{messages.length === 1 && <div className="p-3 border-t border-slate-800"><p className="text-[10px] text-slate-500 uppercase flex gap-1"><HelpCircle className="w-3 h-3" />Questions backed by the versioned gold set</p>{suggestionError && <p className="text-[10px] text-amber-400 mt-1">{suggestionError}</p>}<div className="grid sm:grid-cols-2 gap-2 mt-2">{suggestions.map(item => <button key={item.id} onClick={() => void ask(item.question)} className="p-2 text-left text-[11px] bg-slate-900 border border-slate-800 rounded flex gap-1"><ChevronRight className="w-3 h-3 text-teal-400 shrink-0" />{item.question}</button>)}</div></div>}<form onSubmit={event => { event.preventDefault(); void ask(input); }} className="p-4 border-t border-slate-800 flex gap-2"><input maxLength={2000} disabled={searching} value={input} onChange={event => setInput(event.target.value)} placeholder="Ask a question grounded in the corpus" className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs" /><button disabled={searching || !input.trim()} className="p-2 bg-teal-500 text-slate-950 rounded disabled:opacity-30"><Send className="w-4 h-4" /></button></form></section>}
    {showRight && <section className={`${viewMode === 'just-stay' ? 'lg:col-span-3' : 'lg:col-span-12'} bg-slate-900 border border-slate-800 rounded-xl flex flex-col overflow-hidden`}><PanelHeader title={`Retrieved Evidence · K=${system?.retrieval.defaultTopK ?? '—'}`} action={viewMode !== 'just-stay' ? () => setViewMode('just-stay') : undefined} /><div className="flex-1 overflow-y-auto p-3 space-y-3">{sources.length === 0 ? <div className="h-full flex flex-col items-center justify-center text-center text-xs text-slate-500 p-4"><Database className="w-9 h-9 text-teal-400/30 mb-2" />Submit a query to inspect persisted source chunks.</div> : sources.map(source => <button key={source.chunkId} onClick={() => onSelectDocument(source.documentId)} className="w-full text-left p-3 bg-slate-800/50 border border-slate-700 rounded-lg"><div className="flex justify-between text-[10px]"><span className="text-teal-400 font-bold">{source.label} · {(source.similarityScore * 100).toFixed(1)}%</span><span>#{source.chunkIndex}</span></div><p className="mt-2 text-[11px] leading-relaxed line-clamp-5">{source.text}</p><p className="mt-2 text-[10px] text-slate-500 flex gap-1"><FileText className="w-3 h-3" />{source.documentName} · page {source.pageNumber}</p></button>)}</div></section>}
  </div>;
}

function PanelHeader({ title, action }: { title: string; action?: () => void }) { return <div className="p-4 border-b border-slate-800 flex justify-between"><h2 className="text-[10px] font-bold uppercase font-mono text-slate-400">{title}</h2>{action && <button onClick={action} className="text-[9px] text-teal-400">Standard layout</button>}</div>; }

export function SafeAnswer({ text }: { text: string }) {
  return <>{text.split(/(\[S\d+\])/g).map((part, index) => /^\[S\d+\]$/.test(part) ? <span key={`${part}-${index}`} className="text-teal-400 font-mono font-bold">{part}</span> : <span key={index}>{part}</span>)}</>;
}
