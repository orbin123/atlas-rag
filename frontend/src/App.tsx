import { useEffect, useState } from 'react';
import { BarChart4, BookOpen, Database, LayoutDashboard, Menu, Upload, X } from 'lucide-react';
import DashboardChat from './components/DashboardChat';
import DocumentDetail from './components/DocumentDetail';
import DocumentLibrary from './components/DocumentLibrary';
import Evaluation from './components/Evaluation';
import UploadDocuments from './components/UploadDocuments';
import { getSystemInfo } from './api/system';
import { useDocuments } from './hooks/useDocuments';
import type { SystemInfo } from './types';

type Page = 'dashboard' | 'documents' | 'upload' | 'detail' | 'evaluation';
type ViewMode = 'just-stay' | 'index' | 'chat' | 'evidence';

export function runtimeStatusText(system: SystemInfo | null): string {
  if (!system) return 'API STATUS UNAVAILABLE';
  if (system.index.status !== 'ready') return `INDEX ${system.index.status.toUpperCase()}`;
  if (system.generation.ready) return `GENERATION READY · ${system.generation.model}`;
  return system.generation.enabled
    ? 'RETRIEVAL READY · GENERATION UNAVAILABLE'
    : 'RETRIEVAL READY · GENERATION NOT CONFIGURED';
}

export default function App() {
  const [currentPage, setCurrentPage] = useState<Page>('dashboard');
  const [viewMode, setViewMode] = useState<ViewMode>('just-stay');
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [systemError, setSystemError] = useState<string | null>(null);
  const library = useDocuments();

  const loadSystem = async () => {
    try { setSystem(await getSystemInfo()); setSystemError(null); }
    catch (cause) { setSystemError(cause instanceof Error ? cause.message : 'System information is unavailable.'); }
  };
  useEffect(() => { void loadSystem(); }, []);

  const navigate = (page: Page) => {
    setCurrentPage(page); setMobileMenuOpen(false);
    if (page !== 'detail') setSelectedDocId(null);
  };
  const selectDocument = (id: string) => { setSelectedDocId(id); setCurrentPage('detail'); };
  const refresh = async () => { await Promise.all([library.reload(), loadSystem()]); };

  const navItems: { page: Page; label: string; icon: typeof LayoutDashboard }[] = [
    { page: 'dashboard', label: 'Synthesis / Chat', icon: LayoutDashboard },
    { page: 'documents', label: 'Document Library', icon: BookOpen },
    { page: 'upload', label: 'Ingest Document', icon: Upload },
    { page: 'evaluation', label: 'Evaluation Suite', icon: BarChart4 },
  ];
  const navigation = <nav className="space-y-1">{navItems.map(item => <button key={item.page} onClick={() => navigate(item.page)} className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-bold border-l-4 ${currentPage === item.page || (item.page === 'documents' && currentPage === 'detail') ? 'bg-slate-800 text-teal-400 border-teal-500' : 'text-slate-400 hover:bg-slate-800/50 border-transparent'}`}><item.icon className="w-4 h-4" />{item.label}</button>)}</nav>;

  return <div className="bg-slate-950 text-slate-200 min-h-screen font-sans flex flex-col" id="atlas-rag-app">
    <header className="bg-slate-900/80 border-b border-slate-800 sticky top-0 z-40 px-6 h-14 flex items-center justify-between backdrop-blur-md">
      <div className="flex items-center gap-3">
        <button onClick={() => setMobileMenuOpen(value => !value)} className="md:hidden p-1.5 text-slate-400">{mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}</button>
        <button className="flex items-center gap-3" onClick={() => navigate('dashboard')}><span className="w-8 h-8 bg-teal-500 rounded-lg flex items-center justify-center text-slate-950"><Database className="w-4 h-4" /></span><span className="text-lg font-bold text-white">ATLAS<span className="text-teal-400">RAG</span></span></button>
      </div>
      <div className="text-[10px] font-mono text-slate-400 text-right">
        <p className={system?.index.status === 'ready' ? 'text-teal-400' : 'text-amber-400'}>{system ? `INDEX ${system.index.status.toUpperCase()} · ${system.index.vectorCount.toLocaleString()} VECTORS` : 'API STATUS UNAVAILABLE'}</p>
        {system && <p>{system.embedding.dimension}-D · TOP K {system.retrieval.defaultTopK}</p>}
      </div>
    </header>
    <div className="flex flex-1 min-h-0">
      <aside className="hidden md:block w-64 bg-slate-900 border-r border-slate-800 p-4 shrink-0"><p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4 px-3">Research controls</p>{navigation}</aside>
      {mobileMenuOpen && <div className="fixed inset-0 z-50 bg-slate-950/80 md:hidden" onClick={() => setMobileMenuOpen(false)}><aside className="w-64 h-full bg-slate-900 p-5" onClick={event => event.stopPropagation()}>{navigation}</aside></div>}
      <main className="flex-1 overflow-y-auto p-4 md:p-6">
        {systemError && <p className="mb-3 text-xs text-amber-400">{systemError}</p>}
        {currentPage === 'dashboard' && <DashboardChat documents={library.documents} documentsLoading={library.loading} documentsError={library.error} system={system} onReload={refresh} onNavigateToUpload={() => navigate('upload')} onSelectDocument={selectDocument} viewMode={viewMode} setViewMode={setViewMode} />}
        {currentPage === 'documents' && <DocumentLibrary documents={library.documents} stats={library.stats} loading={library.loading} error={library.error} onReload={refresh} onSelectDocument={selectDocument} onNavigateToUpload={() => navigate('upload')} />}
        {currentPage === 'upload' && <UploadDocuments system={system} onCompleted={async id => { await refresh(); selectDocument(id); }} onNavigateToLibrary={() => navigate('documents')} />}
        {currentPage === 'detail' && selectedDocId && <DocumentDetail documentId={selectedDocId} onBack={() => navigate('documents')} />}
        {currentPage === 'evaluation' && <Evaluation system={system} />}
      </main>
    </div>
    <footer className="bg-slate-900 border-t border-slate-800 px-6 py-3 text-[10px] text-slate-500 font-mono flex justify-between"><span>ATLAS RAG · LOCAL RESEARCH CORE</span><span>{runtimeStatusText(system)}</span></footer>
  </div>;
}
