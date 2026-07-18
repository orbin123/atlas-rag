import React, { useState } from 'react';
import { 
  ArrowLeft, 
  FileText, 
  Folder, 
  User, 
  Layers, 
  Server, 
  Calendar, 
  HardDrive, 
  Bookmark, 
  ChevronLeft, 
  ChevronRight, 
  Search,
  CheckCircle2
} from 'lucide-react';
import { Document, Chunk } from '../types';
import { MOCK_CHUNKS } from '../data';

interface DocumentDetailProps {
  document: Document;
  onBack: () => void;
}

export default function DocumentDetail({ document, onBack }: DocumentDetailProps) {
  // Page preview control
  const [activePreviewPage, setActivePreviewPage] = useState(1);
  const [chunkSearch, setChunkSearch] = useState('');

  // Retrieve mock chunks for this document, fallback to a generated set if newly uploaded
  const documentChunks: Chunk[] = MOCK_CHUNKS[document.id] || [
    {
      id: `${document.id}-c1`,
      documentId: document.id,
      documentName: document.name,
      chunkNumber: 1,
      pageNumber: 1,
      text: `[STAGED PARSE CONTENT CHUNK 1] The newly ingested context file '${document.name}' has been split. Subject concerns ${document.domain} concepts. Detailed analytics track critical specifications.`,
      status: 'indexed',
      tokenCount: 125
    },
    {
      id: `${document.id}-c2`,
      documentId: document.id,
      documentName: document.name,
      chunkNumber: 2,
      pageNumber: 2,
      text: `[STAGED PARSE CONTENT CHUNK 2] Standard compliance structures are verified at Port 3000. Data transmission schemas execute on authorized node layers with mutual cryptographic signatures.`,
      status: 'indexed',
      tokenCount: 140
    }
  ];

  // Filter chunks based on simple keyword search
  const filteredChunks = documentChunks.filter(chunk => 
    chunk.text.toLowerCase().includes(chunkSearch.toLowerCase()) ||
    chunk.chunkNumber.toString().includes(chunkSearch)
  );

  // Extracted text preview pages (simulate 3 pages)
  const simulatedPagesText: Record<number, string> = {
    1: document.extractedTextPreview || 'Page 1 contents parsed. Key variables involve organizational metrics, local model parameters, and vector coordinate indexes. Authentication credentials verify client-side security limits.',
    2: 'Page 2 contents: Section 4.01. Technical compliance mandates that the local repository maintains direct serializations of all parsed files. In the event of system resets, indexes are hydrated from regional backups to avoid duplicate GPU runs.',
    3: 'Page 3 contents: In summary, the primary objective of this documentation is to streamline secure information access. Users query the Atlas vector space through similarity rankings to bypass standard unstructured document delays.'
  };

  const handleNextPage = () => {
    if (activePreviewPage < 3) setActivePreviewPage(prev => prev + 1);
  };

  const handlePrevPage = () => {
    if (activePreviewPage > 1) setActivePreviewPage(prev => prev - 1);
  };

  return (
    <div className="space-y-6 animate-fade-in" id="document-detail-page">
      
      {/* Back button */}
      <button 
        onClick={onBack}
        className="flex items-center gap-1.5 text-[10px] font-bold font-mono text-slate-400 hover:text-teal-400 transition-colors uppercase tracking-wider"
        id="detail-back-btn"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Document Library
      </button>

      {/* Detail Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-5 bg-slate-900 border border-slate-800 rounded-xl">
        <div className="flex items-start gap-4">
          <div className={`p-3 rounded shrink-0 mt-1 ${
            document.type === 'pdf' ? 'bg-red-500/10 text-red-400' :
            document.type === 'docx' ? 'bg-blue-500/10 text-blue-400' :
            'bg-emerald-500/10 text-emerald-400'
          }`}>
            <FileText className="w-8 h-8" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-bold text-slate-200 font-display">{document.name}</h1>
              <span className={`text-[10px] px-2.5 py-0.5 rounded font-mono uppercase tracking-wider font-bold ${
                document.status === 'indexed' ? 'bg-teal-400/10 text-teal-400 border border-teal-500/20' : 'bg-amber-500/10 text-amber-400'
              }`}>
                {document.status}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1 max-w-xl">{document.description}</p>
            
            {/* Horizontal badge row */}
            <div className="flex flex-wrap gap-3 mt-3">
              <span className="inline-flex items-center gap-1 text-[10px] text-slate-300 bg-slate-850 border border-slate-700 px-2.5 py-1 rounded font-mono">
                <Folder className="w-3 h-3 text-teal-400" />
                {document.domain}
              </span>
              <span className="inline-flex items-center gap-1 text-[10px] text-slate-300 bg-slate-850 border border-slate-700 px-2.5 py-1 rounded font-mono">
                <HardDrive className="w-3 h-3 text-teal-400" />
                {document.fileSize}
              </span>
              <span className="inline-flex items-center gap-1 text-[10px] text-slate-300 bg-slate-850 border border-slate-700 px-2.5 py-1 rounded font-mono">
                <Calendar className="w-3 h-3" />
                Uploaded: {document.uploadDate}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left Side: Metadata Card & Extracted Text Preview (6 cols) */}
        <div className="lg:col-span-6 space-y-6">
          
          {/* Metadata Grid */}
          <div className="bg-slate-900 border border-slate-800 p-5 rounded-xl" id="detail-metadata-card">
            <h3 className="text-[10px] font-bold tracking-widest text-slate-400 uppercase flex items-center gap-1.5 font-mono mb-4">
              <Bookmark className="w-4 h-4 text-teal-400" />
              Indexing Properties
            </h3>
            <div className="grid grid-cols-2 gap-4 text-xs font-mono font-bold uppercase">
              <div className="p-3 bg-slate-950 rounded border border-slate-800/80">
                <p className="text-[10px] text-slate-500 flex items-center gap-1 uppercase mb-1">
                  <User className="w-3.5 h-3.5 text-teal-400" /> Author / Source
                </p>
                <p className="text-slate-200 truncate font-sans text-xs capitalize">{document.author || 'Internal Database'}</p>
              </div>
              <div className="p-3 bg-slate-950 rounded border border-slate-800/80">
                <p className="text-[10px] text-slate-500 flex items-center gap-1 uppercase mb-1">
                  <Layers className="w-3.5 h-3.5 text-teal-400" /> Total Document Pages
                </p>
                <p className="text-slate-200 font-bold">{document.pages} pages</p>
              </div>
              <div className="p-3 bg-slate-950 rounded border border-slate-800/80">
                <p className="text-[10px] text-slate-500 flex items-center gap-1 uppercase mb-1">
                  <Server className="w-3.5 h-3.5 text-teal-400" /> Partitions Created
                </p>
                <p className="text-teal-400 font-bold">{document.chunksCount} chunks</p>
              </div>
              <div className="p-3 bg-slate-950 rounded border border-slate-800/80">
                <p className="text-[10px] text-slate-500 flex items-center gap-1 uppercase mb-1">
                  <CheckCircle2 className="w-3.5 h-3.5 text-teal-400" /> Index Host
                </p>
                <p className="text-slate-200 text-[11px] truncate">FAISS Local Matrix</p>
              </div>
            </div>
          </div>

          {/* Extracted Text Preview with Page Nav */}
          <div className="bg-slate-900 border border-slate-800 p-5 rounded-xl flex flex-col justify-between min-h-[350px]" id="extracted-text-preview-container">
            <div>
              <div className="flex items-center justify-between mb-4 border-b border-slate-800/80 pb-3">
                <h3 className="text-[10px] font-bold tracking-widest text-slate-400 uppercase flex items-center gap-1.5 font-mono">
                  <FileText className="w-4 h-4 text-teal-400" />
                  Extracted OCR Text Preview
                </h3>
                
                {/* Page Nav */}
                <div className="flex items-center gap-2">
                  <button 
                    onClick={handlePrevPage}
                    disabled={activePreviewPage === 1}
                    className="p-1 rounded bg-slate-950 hover:bg-slate-800 text-slate-400 hover:text-teal-400 border border-slate-800 disabled:opacity-30 transition-all cursor-pointer"
                    id="preview-prev-page"
                  >
                    <ChevronLeft className="w-3.5 h-3.5" />
                  </button>
                  <span className="text-[11px] font-mono text-slate-300">
                    Page {activePreviewPage} of 3
                  </span>
                  <button 
                    onClick={handleNextPage}
                    disabled={activePreviewPage === 3}
                    className="p-1 rounded bg-slate-950 hover:bg-slate-800 text-slate-400 hover:text-teal-400 border border-slate-800 disabled:opacity-30 transition-all cursor-pointer"
                    id="preview-next-page"
                  >
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              {/* Text Area */}
              <div className="p-4 bg-slate-950 rounded border border-slate-800/80 font-sans leading-relaxed text-xs text-slate-300 min-h-[180px] select-text">
                {simulatedPagesText[activePreviewPage]}
              </div>
            </div>

            <p className="text-[10px] text-slate-500 font-mono mt-4">
              * Showing OCR preview of parsed blocks. High-resolution text extraction is completed via local PDFMiner parser.
            </p>
          </div>

        </div>

        {/* Right Side: Chunk Partitions (6 cols) */}
        <div className="lg:col-span-6 space-y-4 flex flex-col h-full" id="chunks-partitions-panel">
          
          {/* Header & Chunk search */}
          <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-[10px] font-bold tracking-widest text-slate-400 uppercase flex items-center gap-1.5 font-mono">
                <Server className="w-4 h-4 text-teal-400" />
                Vector Chunk Partitions ({documentChunks.length})
              </h3>
              <span className="text-[10px] bg-teal-400/10 text-teal-400 border border-teal-500/20 px-2 py-0.5 rounded font-mono uppercase font-bold">
                768-D Indexed
              </span>
            </div>

            {/* Chunk Search Bar */}
            <div className="relative">
              <Search className="absolute left-3 top-2.5 w-3.5 h-3.5 text-slate-500" />
              <input
                type="text"
                placeholder="Search text in chunk partitions..."
                className="w-full bg-slate-850 border border-slate-700 rounded-lg pl-8.5 pr-4 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-teal-500 font-semibold"
                value={chunkSearch}
                onChange={(e) => setChunkSearch(e.target.value)}
                id="chunk-partition-search"
              />
            </div>
          </div>

          {/* Chunks List */}
          <div className="space-y-3 max-h-[500px] overflow-y-auto pr-1">
            {filteredChunks.length === 0 ? (
              <div className="text-center py-12 bg-slate-900 border border-slate-800 rounded-xl text-slate-500">
                <p className="text-xs">No matching chunk partitions found</p>
              </div>
            ) : (
              filteredChunks.map((chunk) => (
                <div 
                  key={chunk.id}
                  className="p-4 bg-slate-900 border border-slate-800 rounded-xl space-y-2 hover:border-teal-500/40 transition-colors"
                  id={`detail-chunk-card-${chunk.id}`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-mono text-teal-400 font-bold bg-teal-400/10 px-2 py-0.5 rounded border border-teal-500/20 uppercase tracking-wider">
                      Chunk #{chunk.chunkNumber}
                    </span>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-slate-500 font-mono font-bold uppercase">
                        Page {chunk.pageNumber}
                      </span>
                      <span className="inline-flex items-center gap-1 text-[9px] bg-teal-400/10 text-teal-400 px-2 py-0.5 rounded font-mono font-bold uppercase tracking-wider">
                        <span className="w-1 h-1 bg-teal-400 rounded-full animate-ping" />
                        Vector OK
                      </span>
                    </div>
                  </div>

                  <p className="text-[11px] text-slate-300 leading-relaxed italic bg-slate-950 p-2.5 rounded border border-slate-800/80">
                    "{chunk.text}"
                  </p>

                  <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono">
                    <span>Token length: {chunk.tokenCount} tokens</span>
                    <span>MD5: {chunk.id}</span>
                  </div>
                </div>
              ))
            )}
          </div>

        </div>

      </div>

    </div>
  );
}
