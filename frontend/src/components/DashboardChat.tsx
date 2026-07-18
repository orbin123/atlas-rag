import React, { useState, useEffect, useRef } from 'react';
import { 
  Search, 
  Sparkles, 
  FileText, 
  Database, 
  Folder, 
  Send, 
  ArrowRight, 
  AlertTriangle, 
  HelpCircle, 
  ChevronRight, 
  Loader2, 
  SlidersHorizontal,
  Bookmark
} from 'lucide-react';
import { Document, Chunk, Message } from '../types';
import { INITIAL_DOCUMENTS, PRESET_QAS } from '../data';

interface DashboardChatProps {
  documents: Document[];
  onNavigateToUpload: () => void;
  onSelectDocument: (docId: string) => void;
  viewMode?: 'just-stay' | 'index' | 'chat' | 'evidence';
  setViewMode?: (mode: 'just-stay' | 'index' | 'chat' | 'evidence') => void;
}

export default function DashboardChat({ 
  documents, 
  onNavigateToUpload, 
  onSelectDocument,
  viewMode = 'just-stay',
  setViewMode
}: DashboardChatProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedDomain, setSelectedDomain] = useState<string>('All');
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome-msg',
      sender: 'assistant',
      text: 'Welcome to **Atlas RAG**. I am connected to your local vector database containing your indexed multi-domain documents. Select a preset query below or type your own research question to perform an authenticated context-grounded retrieval search.',
      timestamp: 'Just now'
    }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [searchPhase, setSearchPhase] = useState('');
  const [retrievedChunks, setRetrievedChunks] = useState<Chunk[]>([]);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Extract unique domains for filtering
  const domains = ['All', ...Array.from(new Set(documents.map(doc => doc.domain)))];

  // Filter documents in the left panel
  const filteredDocs = documents.filter(doc => {
    const matchesSearch = doc.name.toLowerCase().includes(searchTerm.toLowerCase()) || 
                          (doc.description && doc.description.toLowerCase().includes(searchTerm.toLowerCase()));
    const matchesDomain = selectedDomain === 'All' || doc.domain === selectedDomain;
    return matchesSearch && matchesDomain;
  });

  // Scroll to bottom of chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isSearching]);

  // Execute RAG Query pipeline simulation
  const handleQuery = async (queryText: string) => {
    if (!queryText.trim()) return;

    // Add user message
    const userMsgId = `msg-${Date.now()}`;
    const newMsg: Message = {
      id: userMsgId,
      sender: 'user',
      text: queryText,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };
    
    setMessages(prev => [...prev, newMsg]);
    setInputValue('');
    setIsSearching(true);

    // Multi-phase loader simulation to match a high-end AI research feel
    const phases = [
      'Tokenizing & extracting query embeddings...',
      'Searching local FAISS vector store (Top-K=5)...',
      'Re-ranking retrieved chunks using cross-encoder...',
      'Synthesizing answer grounded strictly in retrieved context...'
    ];

    for (let i = 0; i < phases.length; i++) {
      setSearchPhase(phases[i]);
      await new Promise(resolve => setTimeout(resolve, i === 1 ? 550 : 350));
    }

    // Determine response based on query text similarity to our mock preset queries
    const normalizedQuery = queryText.toLowerCase();
    let matchedQA = PRESET_QAS.find(qa => {
      // Direct or key terms match
      return normalizedQuery.includes('carbon') || 
             normalizedQuery.includes('neutrality') || 
             normalizedQuery.includes('climate') || 
             normalizedQuery.includes('decarbonization') ? qa.question.includes('carbon') :
             normalizedQuery.includes('indemnification') || 
             normalizedQuery.includes('merger') || 
             normalizedQuery.includes('liability') || 
             normalizedQuery.includes('apex') ? qa.question.includes('indemnification') :
             normalizedQuery.includes('revenue') || 
             normalizedQuery.includes('financial') || 
             normalizedQuery.includes('operating income') || 
             normalizedQuery.includes('overhead') || 
             normalizedQuery.includes('q2') ? qa.question.includes('operating income') :
             normalizedQuery.includes('ehr') || 
             normalizedQuery.includes('metadata') || 
             normalizedQuery.includes('fhir') || 
             normalizedQuery.includes('compliance') ? qa.question.includes('compliance') : false;
    });

    // Fallback direct match if query matches a preset query precisely
    if (!matchedQA) {
      matchedQA = PRESET_QAS.find(qa => normalizedQuery.includes(qa.question.toLowerCase().split(' ').slice(0, 3).join(' ')));
    }

    if (matchedQA) {
      // Context found!
      const assistantMsg: Message = {
        id: `msg-${Date.now() + 1}`,
        sender: 'assistant',
        text: matchedQA.answer,
        citations: matchedQA.citations,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      setMessages(prev => [...prev, assistantMsg]);
      setRetrievedChunks(matchedQA.retrievedChunks);
    } else {
      // Insufficient Context State!
      const assistantMsg: Message = {
        id: `msg-${Date.now() + 1}`,
        sender: 'assistant',
        text: `**INSUFFICIENT CONTEXT WARNING:** Atlas RAG cannot generate a safe response to your query. 
        
The retrieved document chunks did not yield a vector similarity score above the minimum configuration threshold (t > 0.72) required for grounding, and no pertinent textual evidence was detected. Atlas RAG operates under an **anti-hallucination guardrail** which prohibits answering questions outside of the indexed document database.`,
        isInsufficientContext: true,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      setMessages(prev => [...prev, assistantMsg]);
      
      // Show some mock "irrelevant" low-similarity chunks in right panel to simulate the failure
      setRetrievedChunks([
        {
          id: 'chunk-fail-1',
          documentId: 'doc-3',
          documentName: 'Q2_Financial_Report.pdf',
          chunkNumber: 8,
          pageNumber: 15,
          text: '...and other unrelated organizational parameters including general employee benefits and overhead accounts not directly correlated to specified clinical queries...',
          status: 'indexed',
          similarityScore: 0.284,
          tokenCount: 110
        },
        {
          id: 'chunk-fail-2',
          documentId: 'doc-1',
          documentName: 'Climate_Action_Plan_2026.pdf',
          chunkNumber: 15,
          pageNumber: 12,
          text: '...waste logistics and collection protocols for recyclable materials within regional corporate parks...',
          status: 'indexed',
          similarityScore: 0.154,
          tokenCount: 95
        }
      ]);
    }

    setIsSearching(false);
    setSearchPhase('');
  };

  const isJustStay = viewMode === 'just-stay';
  const showLeft = isJustStay || viewMode === 'index';
  const showCenter = isJustStay || viewMode === 'chat';
  const showRight = isJustStay || viewMode === 'evidence';

  const leftColSpan = isJustStay ? "lg:col-span-3" : "lg:col-span-12";
  const centerColSpan = isJustStay ? "lg:col-span-6" : "lg:col-span-12";
  const rightColSpan = isJustStay ? "lg:col-span-3" : "lg:col-span-12";
  
  const isChatExpanded = viewMode === 'chat';

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 h-[calc(100vh-100px)] min-h-[550px] animate-fade-in text-slate-200" id="dashboard-rag">
      
      {/* 1. LEFT SIDEBAR: Document Collection (3 Cols) */}
      {showLeft && (
        <div className={`${leftColSpan} bg-slate-900 border border-slate-800 rounded-xl flex flex-col h-full overflow-hidden`} id="left-sidebar-panel">
          <div className="p-4 border-b border-slate-800 bg-slate-900/50">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs font-bold tracking-wider text-slate-400 uppercase flex items-center gap-1.5 font-mono">
                <Database className="w-3.5 h-3.5 text-teal-400" />
                Index Core Packs
              </h3>
              <div className="flex items-center gap-1.5 font-mono">
                {!isJustStay && (
                  <button
                    onClick={() => setViewMode && setViewMode('just-stay')}
                    className="text-[9px] text-teal-400 hover:text-teal-300 bg-teal-500/10 hover:bg-teal-500/20 px-2 py-0.5 rounded border border-teal-500/30 font-bold uppercase transition-all cursor-pointer"
                    title="Return to standard 3-column layout"
                  >
                    Just Stay
                  </button>
                )}
                <span className="text-[10px] bg-slate-800 text-slate-300 px-2 py-0.5 rounded border border-slate-700/60 font-bold">
                  {documents.length} FILES
                </span>
              </div>
            </div>

            {/* Search Box */}
            <div className="relative mb-3">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
              <input
                type="text"
                placeholder="Search indexed documents..."
                className="w-full bg-slate-850 border border-slate-700 rounded-lg pl-9 pr-4 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-teal-500"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                id="search-corpus-input"
              />
            </div>

            {/* Domain Filter */}
            <div className="flex items-center gap-1 overflow-x-auto pb-1 scrollbar-thin">
              {domains.map((dom) => (
                <button
                  key={dom}
                  onClick={() => setSelectedDomain(dom)}
                  className={`text-[10px] uppercase font-bold tracking-wider whitespace-nowrap px-2.5 py-1 rounded transition-all duration-200 ${
                    selectedDomain === dom 
                      ? 'bg-teal-500 text-slate-950' 
                      : 'bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-700/60'
                  }`}
                  id={`filter-domain-${dom.replace(/\s+/g, '-').toLowerCase()}`}
                >
                  {dom}
                </button>
              ))}
            </div>
          </div>

          {/* Scrollable Doc List */}
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {filteredDocs.length === 0 ? (
              <div className="text-center py-8 text-slate-500">
                <AlertTriangle className="w-8 h-8 mx-auto mb-2 opacity-40 text-slate-400" />
                <p className="text-xs">No indexed files match query</p>
              </div>
            ) : (
              filteredDocs.map((doc) => (
                <div
                  key={doc.id}
                  onClick={() => onSelectDocument(doc.id)}
                  className="group p-2.5 rounded-lg bg-slate-800/40 hover:bg-slate-800/80 border border-slate-800 hover:border-slate-700 cursor-pointer transition-all duration-200 flex flex-col gap-1.5"
                  id={`sidebar-doc-${doc.id}`}
                  title="Click to view Document Details"
                >
                  <div className="flex items-start justify-between gap-1">
                    <div className="flex items-start gap-2 min-w-0">
                      <div className={`p-1.5 rounded shrink-0 mt-0.5 ${
                        doc.type === 'pdf' ? 'bg-red-500/10 text-red-400' :
                        doc.type === 'docx' ? 'bg-blue-500/10 text-blue-400' :
                        'bg-emerald-500/10 text-emerald-400'
                      }`}>
                        <FileText className="w-3.5 h-3.5" />
                      </div>
                      <span className="text-xs font-semibold text-slate-200 group-hover:text-teal-400 truncate max-w-[130px] transition-colors">
                        {doc.name}
                      </span>
                    </div>
                    <span className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-bold uppercase tracking-wider shrink-0 ${
                      doc.status === 'indexed' ? 'bg-teal-400/10 text-teal-400 border border-teal-500/20' : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                    }`}>
                      {doc.status}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono mt-0.5">
                    <span className="flex items-center gap-1">
                      <Folder className="w-2.5 h-2.5 text-teal-400" />
                      {doc.domain}
                    </span>
                    <span>{doc.pages} pages</span>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Upload documents trigger */}
          <div className="p-4 border-t border-slate-800 bg-slate-900/50">
            <button
              onClick={onNavigateToUpload}
              className="w-full flex items-center justify-center gap-2 bg-teal-500 hover:bg-teal-400 text-slate-950 text-xs font-bold py-2.5 px-4 rounded-lg transition-colors shadow-lg shadow-teal-500/10 focus:outline-none uppercase tracking-wider cursor-pointer"
              id="sidebar-upload-btn"
            >
              Upload files
              <ArrowRight className="w-3.5 h-3.5 stroke-[2.5]" />
            </button>
          </div>
        </div>
      )}

      {/* 2. CENTER: Chat Conversation (6 Cols or full width) */}
      {showCenter && (
        <div className={`${centerColSpan} bg-slate-950 border border-slate-800 rounded-xl flex flex-col h-full overflow-hidden`} id="center-chat-panel">
          
          {/* Chat Header */}
          <div className="p-4 border-b border-slate-800 bg-slate-900/50 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded bg-teal-500/10 border border-teal-500/30">
                <Sparkles className="w-4 h-4 text-teal-400" />
              </div>
              <div>
                <h2 className="text-sm font-bold text-white uppercase tracking-wider font-mono">Local Rack Synthesis</h2>
                <p className="text-[10px] text-slate-500 flex items-center gap-1.5 font-mono">
                  <span className="w-1.5 h-1.5 bg-teal-400 rounded-full animate-pulse"></span>
                  {isChatExpanded ? 'Expanded Workspace Active' : 'FAISS Vector Store Ready • Local Model Online'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 font-mono">
              {!isJustStay && (
                <button
                  onClick={() => setViewMode && setViewMode('just-stay')}
                  className="text-[9px] text-teal-400 hover:text-teal-300 bg-teal-500/10 hover:bg-teal-500/20 px-2.5 py-1 rounded border border-teal-500/30 font-bold uppercase transition-all cursor-pointer"
                  title="Return to standard 3-column layout"
                >
                  Collab Standard
                </button>
              )}
              <span className="text-[10px] text-slate-400 bg-slate-800 px-2.5 py-1 rounded border border-slate-700/50 flex items-center gap-1">
                <SlidersHorizontal className="w-3 h-3 text-slate-400" />
                Temp: 0.1
              </span>
            </div>
          </div>

          {/* Chat Messages */}
          <div className={`flex-grow overflow-y-auto transition-all ${
            isChatExpanded ? 'p-8 space-y-6 max-w-5xl mx-auto w-full' : 'p-4 space-y-4'
          }`}>
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex flex-col transition-all ${
                  isChatExpanded ? 'max-w-[75%]' : 'max-w-[85%]'
                } ${
                  msg.sender === 'user' ? 'ml-auto items-end' : 'mr-auto items-start'
                }`}
                id={`chat-msg-${msg.id}`}
              >
                {/* Message Header */}
                <div className="flex items-center gap-1.5 text-[10px] text-slate-500 mb-1 font-mono">
                  <span>{msg.sender === 'user' ? 'Research Agent' : 'Atlas Engine'}</span>
                  <span>•</span>
                  <span>{msg.timestamp}</span>
                </div>

                {/* Message Body */}
                <div className={`rounded-xl leading-relaxed transition-all ${
                  isChatExpanded ? 'p-5 text-sm shadow-2xl shadow-teal-500/5' : 'p-4 text-xs'
                } ${
                  msg.sender === 'user' 
                    ? 'bg-slate-800 border border-slate-700 text-slate-200 rounded-tr-none' 
                    : msg.isInsufficientContext
                      ? 'bg-red-950/40 border border-red-500/40 text-red-100 rounded-tl-none'
                      : 'bg-slate-900 border border-slate-800 text-slate-300 rounded-tl-none shadow-xl'
                }`}>
                  {msg.isInsufficientContext ? (
                    <div className="flex items-center gap-2 mb-2 text-red-400 font-semibold uppercase tracking-wider text-[10px] font-mono">
                      <AlertTriangle className="w-4 h-4 shrink-0 animate-bounce" />
                      Security Guardrail Triggered
                    </div>
                  ) : msg.sender !== 'user' ? (
                    <div className="flex items-center gap-2 mb-3">
                      <div className="w-5 h-5 bg-teal-500 rounded flex items-center justify-center text-[10px] text-slate-950 font-bold">A</div>
                      <span className="text-xs font-bold text-slate-400 uppercase tracking-tighter">Verified Answer</span>
                    </div>
                  ) : null}
                  
                  {/* Parse simple bold text and custom brackets highlight */}
                  <div className="space-y-2">
                    {msg.text.split('\n\n').map((paragraph, index) => {
                      // Highlight citations
                      let htmlText = paragraph
                        .replace(/\*\*(.*?)\*\*/g, '<strong class="text-white font-bold">$1</strong>')
                        .replace(/\[(.*?)\]/g, '<span class="text-teal-400 font-mono text-[11px] cursor-help font-semibold font-bold">[$1]</span>');

                      return (
                        <p 
                          key={index} 
                          dangerouslySetInnerHTML={{ __html: htmlText }}
                        />
                      );
                    })}
                  </div>

                  {/* Explicit Citation Pills inside the card */}
                  {msg.citations && msg.citations.length > 0 && (
                    <div className="mt-4 pt-4 border-t border-slate-800 flex flex-wrap items-center gap-2">
                      <span className="text-[9px] uppercase tracking-wider text-slate-400 font-mono font-bold flex items-center gap-1">
                        <Bookmark className="w-3 h-3 text-teal-400" />
                        Cited Evidence:
                      </span>
                      {msg.citations.map((cit, idx) => (
                        <span 
                          key={idx} 
                          className="text-[10px] bg-slate-850 hover:bg-slate-800 text-slate-300 font-mono px-2 py-0.5 rounded border border-slate-700/60 flex items-center gap-1 transition-colors"
                          title="Linked context segment retrieved by semantic match"
                        >
                          <FileText className="w-2.5 h-2.5 text-slate-400" />
                          {cit.documentName} (p. {cit.page})
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* Local RAG multi-phase Loading Indicator */}
            {isSearching && (
              <div className="flex flex-col items-start max-w-[80%] mr-auto" id="chat-loading-indicator">
                <div className="flex items-center gap-1.5 text-[10px] text-slate-500 mb-1 font-mono">
                  <span>Atlas Engine</span>
                  <span>•</span>
                  <span className="animate-pulse">Processing...</span>
                </div>
                <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-300 rounded-tl-none flex items-center gap-3 w-full">
                  <Loader2 className="w-5 h-5 text-teal-400 animate-spin shrink-0" />
                  <div className="space-y-1 w-full">
                    <p className="font-bold text-slate-200 uppercase tracking-wider text-[10px] font-mono">Executing Retrieval Pipeline</p>
                    <p className="text-[10px] text-slate-400 font-mono animate-pulse">{searchPhase}</p>
                  </div>
                </div>
              </div>
            )}

            <div ref={chatEndRef} />
          </div>

          {/* Quick Suggestion Prompts */}
          {messages.length === 1 && !isSearching && (
            <div className={`border-t border-slate-800 bg-slate-900/30 transition-all ${
              isChatExpanded ? 'p-6 max-w-5xl mx-auto w-full border-x border-slate-800' : 'px-4 py-3'
            }`}>
              <p className="text-[10px] text-slate-500 uppercase tracking-wider font-mono mb-2 font-bold flex items-center gap-1">
                <HelpCircle className="w-3.5 h-3.5 text-teal-400" />
                Suggested Queries (Grounded context available)
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {PRESET_QAS.map((qa, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleQuery(qa.question)}
                    className="p-2 rounded bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-teal-500/50 text-left text-[11px] text-slate-300 transition-all flex items-start gap-1.5 group cursor-pointer"
                    id={`preset-prompt-${idx}`}
                  >
                    <ChevronRight className="w-3.5 h-3.5 mt-0.5 text-teal-400 group-hover:translate-x-0.5 transition-transform" />
                    <span className="truncate">{qa.question}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Question Input Form */}
          <div className={`border-t border-slate-800 bg-slate-900/50 flex flex-col gap-2 transition-all ${
            isChatExpanded ? 'p-6 max-w-5xl mx-auto w-full border-x rounded-b-xl border-slate-800 shadow-2xl' : 'p-4'
          }`}>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleQuery(inputValue);
              }}
              className="relative flex items-center"
              id="chat-input-form"
            >
              <input
                type="text"
                placeholder={isSearching ? 'Atlas is researching...' : 'Ask a research question grounded in your corpus...'}
                disabled={isSearching}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg pl-4 pr-12 py-3 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-teal-500 disabled:opacity-50"
                id="chat-message-input"
              />
              <button
                type="submit"
                disabled={isSearching || !inputValue.trim()}
                className="absolute right-2 p-2 rounded bg-teal-500 hover:bg-teal-400 text-slate-950 disabled:opacity-30 transition-all focus:outline-none cursor-pointer"
                id="send-message-btn"
              >
                <Send className="w-3.5 h-3.5 stroke-[2.5]" />
              </button>
            </form>
            <div className="flex items-center justify-between text-[10px] text-slate-500 px-1 font-mono">
              <span>Anti-Hallucination Guardrail Active</span>
              <span>Query hits limit to indexed context</span>
            </div>
          </div>
        </div>
      )}

      {/* 3. RIGHT SIDEBAR: Retrieved Evidence (3 Cols or full width) */}
      {showRight && (
        <div className={`${rightColSpan} bg-slate-900 border border-slate-800 rounded-xl flex flex-col h-full overflow-hidden`} id="right-sidebar-panel">
          <div className="p-4 border-b border-slate-800 bg-slate-900/50 flex items-center justify-between">
            <h3 className="text-xs font-bold tracking-wider text-slate-400 uppercase flex items-center gap-1.5 font-mono">
              <Database className="w-3.5 h-3.5 text-teal-400" />
              Retrieved Evidence
            </h3>
            <div className="flex items-center gap-2 font-mono">
              {!isJustStay && (
                <button
                  onClick={() => setViewMode && setViewMode('just-stay')}
                  className="text-[9px] text-teal-400 hover:text-teal-300 bg-teal-500/10 hover:bg-teal-500/20 px-2 py-0.5 rounded border border-teal-500/30 font-bold uppercase transition-all cursor-pointer"
                  title="Return to standard 3-column layout"
                >
                  Just Stay
                </button>
              )}
              <span className="text-[10px] text-slate-400 bg-slate-800 px-2 py-0.5 rounded border border-slate-700 font-bold">
                K=5
              </span>
            </div>
          </div>

          {/* Retrieved Evidence list */}
          <div className="flex-1 overflow-y-auto p-3 space-y-3">
            {retrievedChunks.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center p-6 text-slate-500">
                <Database className="w-10 h-10 mb-2 opacity-20 text-teal-400" />
                <p className="text-xs font-semibold">No active retrieval query</p>
                <p className="text-[10px] text-slate-500 mt-1 max-w-[180px]">
                  Submit a query or click a suggestion to inspect semantic vector space hits.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-[10px] font-mono uppercase tracking-widest text-slate-500 font-bold">
                  FAISS Near Neighbors
                </p>
                
                {retrievedChunks.map((chunk, idx) => {
                  const matchPct = Math.round((chunk.similarityScore || 0.72) * 100);
                  return (
                    <div
                      key={chunk.id}
                      className="bg-slate-800/50 border border-slate-700 p-3 rounded-lg flex flex-col gap-2 hover:border-teal-500/30 transition-all"
                      id={`retrieved-chunk-card-${idx}`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-bold text-teal-400 bg-teal-400/10 px-1.5 py-0.5 rounded">
                          {matchPct}% MATCH
                        </span>
                        <span className="text-[10px] text-slate-500 font-mono">
                          Chunk #{chunk.chunkNumber}
                        </span>
                      </div>
                      
                      <p className="text-[11px] text-slate-300 line-clamp-4 leading-relaxed italic">
                        "{chunk.text}"
                      </p>

                      <div className="flex items-center gap-2 mt-1 min-w-0">
                        <div className="w-5 h-4 bg-teal-500/15 rounded flex items-center justify-center text-[8px] text-teal-400 font-mono font-bold shrink-0">
                          {chunk.documentName.split('.').pop()?.toUpperCase() || 'TXT'}
                        </div>
                        <span className="text-[10px] font-semibold text-slate-400 truncate" title={chunk.documentName}>
                          {chunk.documentName}
                        </span>
                        <span className="text-[10px] text-slate-500 font-mono ml-auto shrink-0">
                          Page {chunk.pageNumber}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

    </div>
  );
}
