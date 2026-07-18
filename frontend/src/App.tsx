import React, { useState } from 'react';
import { 
  Database, 
  BookOpen, 
  Upload, 
  BarChart4, 
  RotateCcw, 
  LayoutDashboard, 
  Cpu, 
  Menu, 
  X,
  FileText,
  Layers,
  MessageSquare,
  Eye,
  Maximize2
} from 'lucide-react';
import { Document } from './types';
import { INITIAL_DOCUMENTS } from './data';

// Component imports
import DashboardChat from './components/DashboardChat';
import DocumentLibrary from './components/DocumentLibrary';
import UploadDocuments from './components/UploadDocuments';
import DocumentDetail from './components/DocumentDetail';
import Evaluation from './components/Evaluation';

export default function App() {
  // Navigation tabs state
  const [currentPage, setCurrentPage] = useState<'dashboard' | 'documents' | 'upload' | 'detail' | 'evaluation'>('dashboard');
  
  // Layout mode for Synthesis / Chat
  const [viewMode, setViewMode] = useState<'just-stay' | 'index' | 'chat' | 'evidence'>('just-stay');

  // Local document state (to allow live additions/deletions)
  const [documents, setDocuments] = useState<Document[]>(INITIAL_DOCUMENTS);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);

  // Mobile drawer toggle
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Ingestion: Add new document
  const handleAddDocument = (newDoc: Document) => {
    setDocuments(prev => [newDoc, ...prev]);
  };

  // Deletion: Remove document
  const handleDeleteDocument = (docId: string) => {
    setDocuments(prev => prev.filter(doc => doc.id !== docId));
  };

  // Inspect detail helper
  const handleSelectDocument = (docId: string) => {
    setSelectedDocId(docId);
    setCurrentPage('detail');
  };

  // Reset to initial state
  const handleResetCorpus = () => {
    if (window.confirm('Reset local vector store corpus back to default research presets? This will restore deleted files and clear current user sandbox uploads.')) {
      setDocuments(INITIAL_DOCUMENTS);
      setSelectedDocId(null);
      setCurrentPage('dashboard');
    }
  };

  // Find document currently in inspection
  const activeDocument = documents.find(doc => doc.id === selectedDocId) || documents[0];

  // Toggle viewMode helper. Clicking the same mode resets it to 'just-stay' (Collab Standard)
  const handleToggleViewMode = (mode: 'just-stay' | 'index' | 'chat' | 'evidence') => {
    if (viewMode === mode) {
      setViewMode('just-stay');
    } else {
      setViewMode(mode);
    }
  };

  return (
    <div className="bg-slate-950 text-slate-200 min-h-screen font-sans flex flex-col justify-between selection:bg-teal-500/30 selection:text-white" id="atlas-rag-app">
      
      {/* Top Banner Navigation Bar */}
      <header className="bg-slate-900/50 border-b border-slate-800 sticky top-0 z-40 px-6 h-14 flex items-center justify-between shadow-xl backdrop-blur-md" id="master-header">
        <div className="flex items-center gap-3">
          <button 
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="md:hidden p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg focus:outline-none"
            id="mobile-menu-toggle"
          >
            {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>

          {/* Logo */}
          <div 
            className="flex items-center gap-3 cursor-pointer group" 
            onClick={() => { setCurrentPage('dashboard'); setSelectedDocId(null); }}
          >
            <div className="w-8 h-8 bg-teal-500 rounded-lg flex items-center justify-center text-slate-950 shadow-lg shadow-teal-500/15 group-hover:scale-105 transition-all">
              <Database className="w-4 h-4 stroke-[2.5]" />
            </div>
            <div>
              <span className="text-lg font-bold tracking-tight text-white font-display">ATLAS<span className="text-teal-400">RAG</span></span>
              <p className="text-[9px] text-slate-500 font-mono tracking-wider">SECURE RESEARCH CORE</p>
            </div>
          </div>
        </div>

        {/* Top-Right Header controls for synthesis/chat view layout selection */}
        <div className="flex items-center gap-2" id="header-layout-controls">
          {currentPage === 'dashboard' && (
            <div className="flex items-center bg-slate-900/40 px-2 py-1.5 rounded-lg border border-slate-800/80 shadow-inner" id="just-stay-due-collapse-panel">
              {/* The Small Interactive Panel Toggle Div */}
              <button
                onClick={() => {
                  // Cycle behavior: just-stay -> index -> chat -> evidence -> just-stay
                  if (viewMode === 'just-stay') setViewMode('index');
                  else if (viewMode === 'index') setViewMode('chat');
                  else if (viewMode === 'chat') setViewMode('evidence');
                  else setViewMode('just-stay');
                }}
                className="w-8 h-5.5 rounded border border-slate-700 hover:border-slate-500 bg-slate-950 p-[2px] flex items-center justify-between gap-[2px] transition-all hover:scale-105 active:scale-95 cursor-pointer shrink-0"
                id="mini-layout-selector"
                title="Cycle View Layout (Standard / Index / Synthesis / Evidence)"
              >
                {/* Left Segment representing Index */}
                <div 
                  onClick={(e) => {
                    e.stopPropagation(); // prevent double triggers with parent cycle
                    setViewMode(viewMode === 'index' ? 'just-stay' : 'index');
                  }}
                  className={`w-1.5 h-full rounded-[1px] transition-all duration-200 cursor-pointer ${
                    viewMode === 'just-stay' ? 'bg-slate-600/70 hover:bg-teal-400' :
                    viewMode === 'index' ? 'bg-teal-400' : 'bg-slate-800/40'
                  }`}
                  title="Toggle Index Core Packs view"
                />
                
                {/* Center Segment representing Local Rack Synthesis (Chat) */}
                <div 
                  onClick={(e) => {
                    e.stopPropagation();
                    setViewMode(viewMode === 'chat' ? 'just-stay' : 'chat');
                  }}
                  className={`flex-1 h-full rounded-[1px] transition-all duration-200 cursor-pointer ${
                    viewMode === 'just-stay' ? 'bg-slate-600/70 hover:bg-teal-400' :
                    viewMode === 'chat' ? 'bg-teal-400' : 'bg-slate-800/40'
                  }`}
                  title="Toggle Local Rack Synthesis view"
                />
                
                {/* Right Segment representing Retrieval Evidence */}
                <div 
                  onClick={(e) => {
                    e.stopPropagation();
                    setViewMode(viewMode === 'evidence' ? 'just-stay' : 'evidence');
                  }}
                  className={`w-1.5 h-full rounded-[1px] transition-all duration-200 cursor-pointer ${
                    viewMode === 'just-stay' ? 'bg-slate-600/70 hover:bg-teal-400' :
                    viewMode === 'evidence' ? 'bg-teal-400' : 'bg-slate-800/40'
                  }`}
                  title="Toggle Retrieved Evidence view"
                />
              </button>
            </div>
          )}
        </div>
      </header>

      {/* Main Core Layout: Left Navigation + Central view stage */}
      <div className="flex-1 flex overflow-hidden" id="main-app-container">
        
        {/* Left Sidebar Menu (Desktop) */}
        <aside className="hidden md:flex flex-col justify-between w-64 bg-slate-900 border-r border-slate-800 p-4 shrink-0" id="desktop-sidebar">
          <div className="space-y-6">
            <div className="px-3">
              <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">RESEARCH CONTROLS</h3>
            </div>

            <nav className="space-y-1" id="desktop-nav-menu">
              <button
                onClick={() => { setCurrentPage('dashboard'); setSelectedDocId(null); }}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-bold transition-all cursor-pointer border-l-4 ${
                  currentPage === 'dashboard'
                    ? 'bg-slate-800 text-teal-400 border-teal-500 font-bold shadow-md shadow-teal-500/5'
                    : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800/50 border-transparent'
                }`}
                id="sidebar-nav-dashboard"
              >
                <LayoutDashboard className="w-4 h-4" />
                Synthesis / Chat
              </button>

              <button
                onClick={() => { setCurrentPage('documents'); setSelectedDocId(null); }}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-bold transition-all cursor-pointer border-l-4 ${
                  currentPage === 'documents' || currentPage === 'detail'
                    ? 'bg-slate-800 text-teal-400 border-teal-500 font-bold shadow-md shadow-teal-500/5'
                    : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800/50 border-transparent'
                }`}
                id="sidebar-nav-library"
              >
                <BookOpen className="w-4 h-4" />
                Document Library
              </button>

              <button
                onClick={() => { setCurrentPage('upload'); setSelectedDocId(null); }}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-bold transition-all cursor-pointer border-l-4 ${
                  currentPage === 'upload'
                    ? 'bg-slate-800 text-teal-400 border-teal-500 font-bold shadow-md shadow-teal-500/5'
                    : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800/50 border-transparent'
                }`}
                id="sidebar-nav-upload"
              >
                <Upload className="w-4 h-4" />
                Ingest Sandbox
              </button>

              <button
                onClick={() => { setCurrentPage('evaluation'); setSelectedDocId(null); }}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-bold transition-all cursor-pointer border-l-4 ${
                  currentPage === 'evaluation'
                    ? 'bg-slate-800 text-teal-400 border-teal-500 font-bold shadow-md shadow-teal-500/5'
                    : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800/50 border-transparent'
                }`}
                id="sidebar-nav-evaluation"
              >
                <BarChart4 className="w-4 h-4" />
                Evaluation Suite
              </button>
            </nav>
          </div>
        </aside>

        {/* Sliding Menu drawer (Mobile) */}
        {mobileMenuOpen && (
          <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 md:hidden animate-fade-in" id="mobile-menu-backdrop">
            <div className="bg-slate-900 w-64 h-full p-5 border-r border-slate-800 flex flex-col justify-between">
              <div className="space-y-6">
                <div className="flex items-center justify-between pb-4 border-b border-slate-800">
                  <div className="flex items-center gap-2">
                    <Database className="w-5 h-5 text-teal-400" />
                    <span className="font-bold text-white font-display">ATLAS<span className="text-teal-400">RAG</span></span>
                  </div>
                  <button 
                    onClick={() => setMobileMenuOpen(false)}
                    className="p-1 hover:bg-slate-800 text-slate-400 hover:text-white rounded-lg"
                    id="mobile-close-btn"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>

                <nav className="space-y-1.5" id="mobile-nav-menu">
                  <button
                    onClick={() => { setCurrentPage('dashboard'); setSelectedDocId(null); setMobileMenuOpen(false); }}
                    className={`w-full flex items-center gap-3 px-3 py-3 rounded-lg text-xs font-bold border-l-4 ${
                      currentPage === 'dashboard'
                        ? 'bg-slate-800 text-teal-400 border-teal-500 font-bold'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 border-transparent'
                    }`}
                  >
                    <LayoutDashboard className="w-4 h-4" />
                    Synthesis / Chat
                  </button>

                  <button
                    onClick={() => { setCurrentPage('documents'); setSelectedDocId(null); setMobileMenuOpen(false); }}
                    className={`w-full flex items-center gap-3 px-3 py-3 rounded-lg text-xs font-bold border-l-4 ${
                      currentPage === 'documents' || currentPage === 'detail'
                        ? 'bg-slate-800 text-teal-400 border-teal-500 font-bold'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 border-transparent'
                    }`}
                  >
                    <BookOpen className="w-4 h-4" />
                    Document Library
                  </button>

                  <button
                    onClick={() => { setCurrentPage('upload'); setSelectedDocId(null); setMobileMenuOpen(false); }}
                    className={`w-full flex items-center gap-3 px-3 py-3 rounded-lg text-xs font-bold border-l-4 ${
                      currentPage === 'upload'
                        ? 'bg-slate-800 text-teal-400 border-teal-500 font-bold'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 border-transparent'
                    }`}
                  >
                    <Upload className="w-4 h-4" />
                    Ingest Sandbox
                  </button>

                  <button
                    onClick={() => { setCurrentPage('evaluation'); setSelectedDocId(null); setMobileMenuOpen(false); }}
                    className={`w-full flex items-center gap-3 px-3 py-3 rounded-lg text-xs font-bold border-l-4 ${
                      currentPage === 'evaluation'
                        ? 'bg-slate-800 text-teal-400 border-teal-500 font-bold'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 border-transparent'
                    }`}
                  >
                    <BarChart4 className="w-4 h-4" />
                    Evaluation Suite
                  </button>
                </nav>
              </div>

              
            </div>
          </div>
        )}

        {/* Central Work Space Frame */}
        <main className="flex-1 overflow-y-auto p-4 md:p-6 bg-slate-950" id="stage-viewport">
          
          {currentPage === 'dashboard' && (
            <DashboardChat 
              documents={documents}
              onNavigateToUpload={() => setCurrentPage('upload')}
              onSelectDocument={handleSelectDocument}
              viewMode={viewMode}
              setViewMode={setViewMode}
            />
          )}

          {currentPage === 'documents' && (
            <DocumentLibrary 
              documents={documents}
              onDeleteDocument={handleDeleteDocument}
              onSelectDocument={handleSelectDocument}
              onNavigateToUpload={() => setCurrentPage('upload')}
            />
          )}

          {currentPage === 'upload' && (
            <UploadDocuments 
              onAddDocument={handleAddDocument}
              onNavigateToLibrary={() => setCurrentPage('documents')}
            />
          )}

          {currentPage === 'detail' && (
            <DocumentDetail 
              document={activeDocument}
              onBack={() => setCurrentPage('documents')}
            />
          )}

          {currentPage === 'evaluation' && (
            <Evaluation />
          )}

        </main>

      </div>

      {/* Global Status Footer */}
      <footer className="bg-slate-900 border-t border-slate-800 px-6 py-3 flex flex-col sm:flex-row items-center justify-between text-[11px] text-slate-500 font-mono gap-2" id="master-footer">
        <div>
          <span>© 2026 ATLAS RAG. All rights reserved.</span>
        </div>
      </footer>

    </div>
  );
}
