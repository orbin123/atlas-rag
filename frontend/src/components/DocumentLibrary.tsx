import React, { useState } from 'react';
import { 
  Search, 
  Trash2, 
  FileText, 
  Eye, 
  Plus, 
  Folder, 
  Calendar, 
  Layers, 
  Server, 
  BookOpen, 
  CheckCircle, 
  AlertTriangle,
  ExternalLink
} from 'lucide-react';
import { Document } from '../types';

interface DocumentLibraryProps {
  documents: Document[];
  onDeleteDocument: (docId: string) => void;
  onSelectDocument: (docId: string) => void;
  onNavigateToUpload: () => void;
}

export default function DocumentLibrary({ 
  documents, 
  onDeleteDocument, 
  onSelectDocument, 
  onNavigateToUpload 
}: DocumentLibraryProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedDomain, setSelectedDomain] = useState<string>('All');

  // Extract unique domains
  const domains = ['All', ...Array.from(new Set(documents.map(doc => doc.domain)))];

  // Filters
  const filteredDocs = documents.filter(doc => {
    const matchesSearch = doc.name.toLowerCase().includes(searchTerm.toLowerCase()) || 
                          (doc.description && doc.description.toLowerCase().includes(searchTerm.toLowerCase())) ||
                          (doc.author && doc.author.toLowerCase().includes(searchTerm.toLowerCase()));
    const matchesDomain = selectedDomain === 'All' || doc.domain === selectedDomain;
    return matchesSearch && matchesDomain;
  });

  // Calculation parameters for stats overview
  const totalPages = documents.reduce((sum, doc) => sum + doc.pages, 0);
  const totalChunks = documents.reduce((sum, doc) => sum + doc.chunksCount, 0);
  const successfulIndexes = documents.filter(doc => doc.status === 'indexed').length;

  return (
    <div className="space-y-6 animate-fade-in" id="document-library-page">
      
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100 font-display flex items-center gap-2">
            <BookOpen className="w-6 h-6 text-teal-400" />
            Document Library
          </h1>
          <p className="text-xs text-slate-400">
            Inspect, search, and manage source documents ingested into the local vector database.
          </p>
        </div>
        <button
          onClick={onNavigateToUpload}
          className="flex items-center justify-center gap-2 bg-teal-500 hover:bg-teal-400 text-slate-950 text-xs font-bold py-2.5 px-4 rounded-lg transition-all uppercase tracking-wider"
          id="lib-add-doc-btn"
        >
          <Plus className="w-4 h-4 stroke-[2.5]" />
          Ingest New Document
        </button>
      </div>

      {/* Bento-grid Statistics Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4" id="library-stats-bento">
        {/* Total Documents Card */}
        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl relative overflow-hidden group hover:border-slate-700 transition-all">
          <div className="absolute top-0 right-0 p-3 opacity-10">
            <FileText className="w-12 h-12 text-teal-400" />
          </div>
          <p className="text-[10px] uppercase font-mono tracking-widest font-bold text-slate-500">Total Corpus</p>
          <p className="text-2xl font-bold text-slate-200 mt-1 font-display">{documents.length}</p>
          <p className="text-[10px] text-slate-400 mt-1">Multi-domain documents</p>
        </div>

        {/* Total Pages Card */}
        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl relative overflow-hidden group hover:border-slate-700 transition-all">
          <div className="absolute top-0 right-0 p-3 opacity-10">
            <Layers className="w-12 h-12 text-teal-400" />
          </div>
          <p className="text-[10px] uppercase font-mono tracking-widest font-bold text-slate-500">Total Page Count</p>
          <p className="text-2xl font-bold text-slate-200 mt-1 font-display">{totalPages}</p>
          <p className="text-[10px] text-slate-400 mt-1">Fully parsed pages</p>
        </div>

        {/* Total Chunk Partitions */}
        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl relative overflow-hidden group hover:border-slate-700 transition-all">
          <div className="absolute top-0 right-0 p-3 opacity-10">
            <Server className="w-12 h-12 text-teal-400" />
          </div>
          <p className="text-[10px] uppercase font-mono tracking-widest font-bold text-slate-500">FAISS Index Nodes</p>
          <p className="text-2xl font-bold text-slate-200 mt-1 font-display">{totalChunks}</p>
          <p className="text-[10px] text-slate-400 mt-1">Text chunk embeddings</p>
        </div>

        {/* Active Indexes Card */}
        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl relative overflow-hidden group hover:border-slate-700 transition-all">
          <div className="absolute top-0 right-0 p-3 opacity-10">
            <CheckCircle className="w-12 h-12 text-teal-400" />
          </div>
          <p className="text-[10px] uppercase font-mono tracking-widest font-bold text-slate-500">Healthy Vector Indexes</p>
          <p className="text-2xl font-bold text-teal-400 mt-1 font-display">
            {Math.round((successfulIndexes / (documents.length || 1)) * 100)}%
          </p>
          <p className="text-[10px] text-slate-400 mt-1">{successfulIndexes} healthy partitions</p>
        </div>
      </div>

      {/* Filtering Control Block */}
      <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl flex flex-col md:flex-row gap-4 justify-between items-center" id="library-filters-bar">
        {/* Search */}
        <div className="relative w-full md:max-w-md">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
          <input
            type="text"
            placeholder="Search documents by name, description, author..."
            className="w-full bg-slate-850 border border-slate-700 rounded-lg pl-10 pr-4 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-teal-500"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            id="lib-search-input"
          />
        </div>

        {/* Domain Selection Tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto w-full md:w-auto pb-1 md:pb-0 scrollbar-none justify-start md:justify-end">
          <span className="text-[11px] font-mono font-bold text-slate-500 hidden sm:inline mr-1 uppercase">Domain:</span>
          {domains.map((dom) => (
            <button
              key={dom}
              onClick={() => setSelectedDomain(dom)}
              className={`text-[10px] uppercase font-bold tracking-wider whitespace-nowrap px-3 py-1.5 rounded transition-all duration-200 ${
                selectedDomain === dom 
                  ? 'bg-slate-850 text-teal-400 font-bold border border-teal-500/40' 
                  : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
              }`}
              id={`lib-filter-domain-${dom.replace(/\s+/g, '-').toLowerCase()}`}
            >
              {dom}
            </button>
          ))}
        </div>
      </div>

      {/* Main Table view */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden" id="library-table-container">
        {filteredDocs.length === 0 ? (
          <div className="text-center py-16 text-slate-500">
            <FileText className="w-12 h-12 mx-auto mb-3 opacity-30 text-slate-400" />
            <p className="text-sm font-semibold">No indexed documents found</p>
            <p className="text-xs text-slate-500 mt-1 max-w-[280px] mx-auto">
              Try adjusting your query or upload a new file to index it into Atlas.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-slate-950 border-b border-slate-800 text-[10px] uppercase font-mono tracking-widest font-bold text-slate-500">
                  <th className="p-4 pl-6">Document Name</th>
                  <th className="p-4">Domain Context</th>
                  <th className="p-4">Pages / Chunks</th>
                  <th className="p-4">Upload Date</th>
                  <th className="p-4">File Size</th>
                  <th className="p-4">Index Status</th>
                  <th className="p-4 pr-6 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {filteredDocs.map((doc) => (
                  <tr 
                    key={doc.id}
                    className="hover:bg-slate-800/30 transition-colors group"
                    id={`lib-row-doc-${doc.id}`}
                  >
                    {/* Name */}
                    <td className="p-4 pl-6">
                      <div className="flex items-center gap-3">
                        <div className={`p-2 rounded shrink-0 ${
                          doc.type === 'pdf' ? 'bg-red-500/10 text-red-400' :
                          doc.type === 'docx' ? 'bg-blue-500/10 text-blue-400' :
                          'bg-emerald-500/10 text-emerald-400'
                        }`}>
                          <FileText className="w-4 h-4" />
                        </div>
                        <div className="min-w-0 max-w-[200px] sm:max-w-[300px]">
                          <p 
                            className="text-xs font-semibold text-slate-200 group-hover:text-teal-400 truncate cursor-pointer transition-colors"
                            onClick={() => onSelectDocument(doc.id)}
                            title="Click to view details"
                          >
                            {doc.name}
                          </p>
                          <p className="text-[10px] text-slate-500 truncate mt-0.5">{doc.description}</p>
                        </div>
                      </div>
                    </td>

                    {/* Domain */}
                    <td className="p-4">
                      <span className="inline-flex items-center gap-1 text-[11px] bg-slate-850 border border-slate-700 text-slate-300 px-2 py-0.5 rounded font-mono">
                        <Folder className="w-3 h-3 text-teal-400" />
                        {doc.domain}
                      </span>
                    </td>

                    {/* Pages & Chunks */}
                    <td className="p-4">
                      <div className="text-[11px] font-mono text-slate-300">
                        <span>{doc.pages} pages</span>
                        <span className="mx-1 text-slate-600">/</span>
                        <span className="text-teal-400 font-bold">{doc.chunksCount} chunks</span>
                      </div>
                    </td>

                    {/* Upload Date */}
                    <td className="p-4">
                      <div className="flex items-center gap-1.5 text-[11px] text-slate-400 font-mono">
                        <Calendar className="w-3 h-3" />
                        {doc.uploadDate}
                      </div>
                    </td>

                    {/* File Size */}
                    <td className="p-4 text-[11px] text-slate-400 font-mono">
                      {doc.fileSize}
                    </td>

                    {/* Status */}
                    <td className="p-4">
                      <span className={`inline-flex items-center gap-1.5 text-[10px] px-2.5 py-0.5 rounded font-mono font-bold uppercase tracking-wider ${
                        doc.status === 'indexed' ? 'bg-teal-400/10 text-teal-400 border border-teal-500/20' :
                        doc.status === 'processing' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                        'bg-red-500/10 text-red-400 border border-red-500/20'
                      }`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${
                          doc.status === 'indexed' ? 'bg-teal-400' :
                          doc.status === 'processing' ? 'bg-amber-400 animate-pulse' :
                          'bg-red-400'
                        }`} />
                        {doc.status}
                      </span>
                    </td>

                    {/* Actions */}
                    <td className="p-4 pr-6 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => onSelectDocument(doc.id)}
                          className="p-1.5 rounded bg-slate-800 border border-slate-700 text-slate-300 hover:text-teal-400 hover:border-teal-500/40 transition-colors"
                          title="Inspect Document Details"
                          id={`lib-inspect-${doc.id}`}
                        >
                          <Eye className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => onDeleteDocument(doc.id)}
                          className="p-1.5 rounded bg-slate-800 border border-slate-700 text-slate-300 hover:text-red-400 hover:border-red-500/30 transition-colors"
                          title="Delete index from corpus"
                          id={`lib-delete-${doc.id}`}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

    </div>
  );
}
