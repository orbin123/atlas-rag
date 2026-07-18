import React, { useState, useEffect } from 'react';
import { 
  Upload, 
  FileText, 
  Settings, 
  CheckCircle, 
  XCircle, 
  Loader2, 
  ArrowLeft, 
  Folder, 
  HelpCircle,
  Database,
  ArrowRight,
  ChevronDown,
  Plus
} from 'lucide-react';
import { Document } from '../types';

interface UploadDocumentsProps {
  onAddDocument: (newDoc: Document) => void;
  onNavigateToLibrary: () => void;
}

type StepStatus = 'pending' | 'active' | 'completed' | 'failed';

interface TimelineStep {
  id: string;
  label: string;
  description: string;
}

const INGESTION_STEPS: TimelineStep[] = [
  { id: 'uploading', label: 'Uploading Document', description: 'Transmitting raw binary stream to secure sandbox.' },
  { id: 'extracting', label: 'Extracting Text', description: 'OCR & native structural parsing of text paragraphs.' },
  { id: 'cleaning', label: 'Normalizing Content', description: 'Stripping noise, formatting whitespace, and cleaning symbols.' },
  { id: 'chunking', label: 'Chunking & Segmenting', description: 'Applying sliding window chunking with 150-token overlap.' },
  { id: 'embeddings', label: 'Generating Embeddings', description: 'Calling local model to output 768-dim dense vectors.' },
  { id: 'indexing', label: 'FAISS Index Serialization', description: 'Inserting vectors into FAISS index and updating partition registry.' }
];

export default function UploadDocuments({ onAddDocument, onNavigateToLibrary }: UploadDocumentsProps) {
  // Config state
  const [fileName, setFileName] = useState('annual_growth_forecast.pdf');
  const [domain, setDomain] = useState('Finance');
  const [pageSize, setPageSize] = useState(12);
  const [simulateError, setSimulateError] = useState(false);

  // Drag and drop / staging states
  const [isDragging, setIsDragging] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);
  const [currentStepIndex, setCurrentStepIndex] = useState(-1);
  const [stepStatuses, setStepStatuses] = useState<Record<string, StepStatus>>({});
  const [progressPercent, setProgressPercent] = useState(0);
  const [resultState, setResultState] = useState<'none' | 'success' | 'failed'>('none');
  const [errorMessage, setErrorMessage] = useState('');

  // Domain selections state to support adding custom categories
  const [domainsList, setDomainsList] = useState<string[]>([
    'Climate Science', 
    'Legal Compliance', 
    'Finance', 
    'Healthcare Informatics', 
    'Cybersecurity Framework'
  ]);

  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [newDomainInput, setNewDomainInput] = useState('');

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const container = document.getElementById('domain-dropdown-container');
      if (container && !container.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const handleAddCustomDomain = () => {
    const trimmed = newDomainInput.trim();
    if (!trimmed) return;
    
    // Check if it already exists (case-insensitive check)
    const exists = domainsList.some(d => d.toLowerCase() === trimmed.toLowerCase());
    if (!exists) {
      setDomainsList(prev => [...prev, trimmed]);
    }
    
    // Find matching case or use the typed one
    const matchingDomain = domainsList.find(d => d.toLowerCase() === trimmed.toLowerCase()) || trimmed;
    setDomain(matchingDomain);
    setNewDomainInput('');
    setIsDropdownOpen(false);
  };

  const handleNewDomainKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAddCustomDomain();
    }
  };

  // Drag handles
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      setFileName(file.name);
      // Try to guess domain from keywords
      const lowerName = file.name.toLowerCase();
      if (lowerName.includes('climate') || lowerName.includes('carbon') || lowerName.includes('green')) {
        setDomain('Climate Science');
      } else if (lowerName.includes('law') || lowerName.includes('agreement') || lowerName.includes('contract') || lowerName.includes('merger')) {
        setDomain('Legal Compliance');
      } else if (lowerName.includes('health') || lowerName.includes('clinical') || lowerName.includes('ehr') || lowerName.includes('fhir')) {
        setDomain('Healthcare Informatics');
      } else if (lowerName.includes('security') || lowerName.includes('hack') || lowerName.includes('audit')) {
        setDomain('Cybersecurity Framework');
      } else {
        setDomain('Finance');
      }
    }
  };

  const startIngestion = () => {
    if (isIngesting) return;
    
    setIsIngesting(true);
    setResultState('none');
    setErrorMessage('');
    setCurrentStepIndex(0);
    setProgressPercent(0);

    // Initial status reset
    const initialStatuses: Record<string, StepStatus> = {};
    INGESTION_STEPS.forEach((step, idx) => {
      initialStatuses[step.id] = idx === 0 ? 'active' : 'pending';
    });
    setStepStatuses(initialStatuses);
  };

  // Run the ingestion timeline simulation
  useEffect(() => {
    if (!isIngesting || currentStepIndex === -1) return;

    const totalSteps = INGESTION_STEPS.length;
    const currentStep = INGESTION_STEPS[currentStepIndex];

    // Calculate progression percentage
    const stepWeight = 100 / totalSteps;
    const baseProgress = currentStepIndex * stepWeight;
    setProgressPercent(Math.round(baseProgress + stepWeight / 2));

    // Simulate work duration for current step
    const duration = 1200; // 1.2s per phase
    const timer = setTimeout(() => {
      // Check if we should fail at the embeddings step
      if (simulateError && currentStep.id === 'embeddings') {
        setStepStatuses(prev => ({
          ...prev,
          [currentStep.id]: 'failed'
        }));
        setResultState('failed');
        setErrorMessage('local embedding-model API Timeout: GPU resources exhausted. Pipeline failed at 768-dimensional dense vector serialization.');
        setIsIngesting(false);
        return;
      }

      // Mark current step completed
      setStepStatuses(prev => ({
        ...prev,
        [currentStep.id]: 'completed'
      }));

      // Move to next step if there is one
      if (currentStepIndex < totalSteps - 1) {
        const nextIdx = currentStepIndex + 1;
        setCurrentStepIndex(nextIdx);
        setStepStatuses(prev => ({
          ...prev,
          [INGESTION_STEPS[nextIdx].id]: 'active'
        }));
      } else {
        // Complete! Add document to state
        setProgressPercent(100);
        setIsIngesting(false);
        setResultState('success');

        const fileExtension = fileName.split('.').pop()?.toLowerCase();
        const docType = (fileExtension === 'docx' || fileExtension === 'doc') ? 'docx' : 
                          (fileExtension === 'txt' ? 'txt' : 'pdf');

        const newDoc: Document = {
          id: `uploaded-doc-${Date.now()}`,
          name: fileName,
          type: docType as 'pdf' | 'docx' | 'txt',
          domain: domain,
          pages: pageSize,
          chunksCount: pageSize * 4, // 4 chunks per page average
          uploadDate: new Date().toISOString().split('T')[0],
          status: 'indexed',
          fileSize: `${(Math.random() * 3 + 1).toFixed(1)} MB`,
          author: 'Atlas RAG Sandbox Upload',
          description: `Custom ingested source document focusing on ${domain.toLowerCase()} context, successfully indexed in FAISS store.`,
          extractedTextPreview: `[AUTHENTICATED ATLAS EXTENDED TEXT PREVIEW] Document: ${fileName}. Core elements loaded. Initial parsing identified specific subject structures related to ${domain}. The text segmentation window has broken this document into standard partitions mapping to 768-dimension dense vector coordinates.`
        };

        onAddDocument(newDoc);
      }
    }, duration);

    return () => clearTimeout(timer);
  }, [isIngesting, currentStepIndex, simulateError]);

  return (
    <div className="space-y-6 animate-fade-in" id="upload-document-page">
      
      {/* Back button */}
      <button 
        onClick={onNavigateToLibrary}
        className="flex items-center gap-1.5 text-[10px] font-bold font-mono text-slate-400 hover:text-teal-400 transition-colors uppercase tracking-wider"
        id="upload-back-btn"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Document Library
      </button>

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-100 font-display flex items-center gap-2">
          <Upload className="w-6 h-6 text-teal-400" />
          Document Ingestion Sandbox
        </h1>
        <p className="text-xs text-slate-400">
          Upload text corpora to run text extraction, split content into overlapping chunk intervals, and write vectors directly to the local FAISS registry.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left Side: Upload Setup (5 cols) */}
        <div className="lg:col-span-5 space-y-5">
          
          {/* Draggable upload zone */}
          <div 
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`border-2 border-dashed p-8 rounded-xl flex flex-col items-center justify-center text-center transition-all cursor-pointer ${
              isDragging 
                ? 'border-teal-500 bg-slate-850/60' 
                : 'border-slate-800 bg-slate-900 hover:bg-slate-850/40'
            }`}
            id="drag-drop-zone"
          >
            <Upload className={`w-12 h-12 mb-3 transition-colors ${isDragging ? 'text-teal-400' : 'text-slate-500'}`} />
            <p className="text-xs text-slate-200 font-bold uppercase tracking-wider">
              Drag & drop document here
            </p>
            <p className="text-[11px] text-slate-400 mt-1">
              Supports <span className="text-teal-400 font-mono font-bold">PDF, DOCX, TXT</span> files
            </p>
            <div className="mt-4 pt-4 border-t border-slate-800/80 w-full flex justify-center gap-4 text-[10px] text-slate-500 font-mono font-bold uppercase">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-red-500" />
                PDF
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-blue-500" />
                DOCX
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                TXT
              </span>
            </div>
          </div>

          {/* Document configuration box */}
          <div className="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-4" id="upload-config-box">
            <h3 className="text-[10px] font-bold tracking-widest text-slate-400 uppercase flex items-center gap-1.5 font-mono">
              <Settings className="w-4 h-4 text-teal-400" />
              Ingestion Metadata Config
            </h3>

            {/* Input Name */}
            <div className="space-y-1">
              <label className="text-[10px] uppercase font-mono font-bold text-slate-500">Target File Name</label>
              <input
                type="text"
                value={fileName}
                onChange={(e) => setFileName(e.target.value)}
                disabled={isIngesting}
                className="w-full bg-slate-850 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-teal-500 font-semibold"
                id="config-filename-input"
              />
            </div>

            {/* Input Domain selection */}
            <div className="space-y-1 relative" id="domain-dropdown-container">
              <label className="text-[10px] uppercase font-mono font-bold text-slate-500">Domain Category</label>
              <button
                type="button"
                onClick={() => !isIngesting && setIsDropdownOpen(!isDropdownOpen)}
                disabled={isIngesting}
                className="w-full flex items-center justify-between bg-slate-850 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 hover:bg-slate-800/60 transition-colors focus:outline-none focus:ring-1 focus:ring-teal-500 font-semibold disabled:opacity-50 text-left cursor-pointer"
                id="config-domain-dropdown-trigger"
              >
                <span className="flex items-center gap-1.5">
                  <Folder className="w-3.5 h-3.5 text-teal-400" />
                  {domain}
                </span>
                <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform duration-200 ${isDropdownOpen ? 'rotate-180' : ''}`} />
              </button>

              {isDropdownOpen && (
                <div 
                  className="absolute z-50 left-0 right-0 mt-1 bg-slate-900 border border-slate-700 rounded-lg shadow-xl overflow-hidden animate-fade-in"
                  id="domain-dropdown-menu"
                >
                  <div className="max-h-48 overflow-y-auto p-1.5 space-y-0.5">
                    {domainsList.map((dom) => (
                      <button
                        key={dom}
                        type="button"
                        onClick={() => {
                          setDomain(dom);
                          setIsDropdownOpen(false);
                        }}
                        className={`w-full text-left text-xs px-2.5 py-1.5 rounded transition-all flex items-center justify-between cursor-pointer ${
                          domain === dom 
                            ? 'bg-teal-500/10 text-teal-400 font-bold' 
                            : 'text-slate-300 hover:bg-slate-800 hover:text-slate-100'
                        }`}
                      >
                        <span>{dom}</span>
                        {domain === dom && <CheckCircle className="w-3.5 h-3.5 text-teal-400" />}
                      </button>
                    ))}
                  </div>
                  
                  {/* Custom domain input */}
                  <div className="border-t border-slate-800 p-2 bg-slate-950/80">
                    <div className="relative">
                      <input
                        type="text"
                        value={newDomainInput}
                        onChange={(e) => setNewDomainInput(e.target.value)}
                        onKeyDown={handleNewDomainKeyDown}
                        placeholder="Add custom domain..."
                        className="w-full bg-slate-900 border border-slate-800 focus:border-teal-500/50 rounded px-2.5 py-1.5 text-[11px] text-slate-200 placeholder-slate-600 focus:outline-none pr-8 font-semibold"
                        id="new-domain-category-input"
                      />
                      <button
                        type="button"
                        onClick={handleAddCustomDomain}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-teal-400 transition-colors cursor-pointer"
                        title="Add Category"
                      >
                        <Plus className="w-3.5 h-3.5" />
                      </button>
                    </div>
                    <p className="text-[9px] text-slate-500 mt-1 font-mono pl-1">Press Enter or click + to add</p>
                  </div>
                </div>
              )}
            </div>

            {/* Simulated pages */}
            <div className="space-y-1">
              <label className="text-[10px] uppercase font-mono font-bold text-slate-500">Simulate Pages</label>
              <input
                type="number"
                min={1}
                max={100}
                value={pageSize}
                onChange={(e) => setPageSize(Number(e.target.value))}
                disabled={isIngesting}
                className="w-full bg-slate-850 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-teal-500 font-mono font-bold"
                id="config-pages-input"
              />
            </div>

            {/* Simulated failures checkbox */}
            <div className="pt-2 border-t border-slate-800">
              <label className="flex items-center gap-2 cursor-pointer" id="simulate-error-label">
                <input
                  type="checkbox"
                  checked={simulateError}
                  onChange={(e) => setSimulateError(e.target.checked)}
                  disabled={isIngesting}
                  className="w-4 h-4 rounded bg-slate-850 border-slate-700 text-teal-400 focus:ring-teal-500"
                />
                <span className="text-[11px] text-slate-300 hover:text-slate-100 transition-colors">
                  Trigger simulation failure (Embedding Stage)
                </span>
              </label>
            </div>

            <button
              onClick={startIngestion}
              disabled={isIngesting}
              className="w-full flex items-center justify-center gap-2 bg-teal-500 hover:bg-teal-400 text-slate-950 text-xs font-bold py-2.5 px-4 rounded-lg transition-all uppercase tracking-wider disabled:opacity-50 cursor-pointer"
              id="start-ingestion-btn"
            >
              {isIngesting ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Processing RAG Pipeline...
                </>
              ) : (
                <>
                  <Database className="w-3.5 h-3.5" />
                  Start Ingestion Pipeline
                </>
              )}
            </button>
          </div>

        </div>

        {/* Right Side: Timeline Progress (7 cols) */}
        <div className="lg:col-span-7 bg-slate-900 border border-slate-800 p-5 rounded-xl flex flex-col h-full justify-between" id="upload-timeline-panel">
          
          <div className="space-y-4">
            <h3 className="text-[10px] font-bold tracking-widest text-slate-400 uppercase flex items-center gap-1.5 font-mono">
              <Loader2 className={`w-4 h-4 text-teal-400 ${isIngesting ? 'animate-spin' : ''}`} />
              Staged Ingestion Timeline
            </h3>

            {/* Ingestion progress slider bar */}
            {isIngesting && (
              <div className="space-y-1 bg-slate-950 p-3 rounded-lg border border-slate-800/80">
                <div className="flex justify-between text-[10px] font-mono">
                  <span className="text-slate-400 font-bold uppercase tracking-wide">Total Progress</span>
                  <span className="text-teal-400 font-bold">{progressPercent}%</span>
                </div>
                <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-teal-400 transition-all duration-300 rounded-full"
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>
              </div>
            )}

            {/* Stages Timeline stack */}
            <div className="relative pl-6 space-y-6 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-[1px] before:bg-slate-800">
              {INGESTION_STEPS.map((step, idx) => {
                const status = stepStatuses[step.id] || 'pending';
                
                return (
                  <div key={step.id} className="relative group" id={`timeline-step-${step.id}`}>
                    
                    {/* Circle Indicator */}
                    <div className="absolute -left-6 top-1 transform -translate-x-1/2">
                      {status === 'completed' ? (
                        <div className="w-4.5 h-4.5 rounded-full bg-teal-400/20 border border-teal-400 flex items-center justify-center">
                          <div className="w-1.5 h-1.5 rounded-full bg-teal-400" />
                        </div>
                      ) : status === 'active' ? (
                        <div className="w-4.5 h-4.5 rounded-full bg-teal-400/20 border border-teal-400 flex items-center justify-center animate-pulse">
                          <Loader2 className="w-2.5 h-2.5 text-teal-400 animate-spin" />
                        </div>
                      ) : status === 'failed' ? (
                        <div className="w-4.5 h-4.5 rounded-full bg-red-500/20 border border-red-500 flex items-center justify-center">
                          <div className="w-1.5 h-1.5 rounded-full bg-red-500" />
                        </div>
                      ) : (
                        <div className="w-4.5 h-4.5 rounded-full bg-slate-950 border border-slate-800 flex items-center justify-center">
                          <div className="w-1.5 h-1.5 rounded-full bg-slate-700" />
                        </div>
                      )}
                    </div>

                    {/* Step Labels */}
                    <div className="pl-2">
                      <div className="flex items-center gap-2">
                        <h4 className={`text-xs font-semibold ${
                          status === 'completed' ? 'text-slate-200' :
                          status === 'active' ? 'text-teal-400 font-bold' :
                          status === 'failed' ? 'text-red-400 font-bold' : 'text-slate-500'
                        }`}>
                          {step.label}
                        </h4>
                        {status === 'completed' && <span className="text-[9px] text-teal-400 font-mono font-bold">OK</span>}
                        {status === 'active' && <span className="text-[9px] text-teal-400 font-mono font-bold animate-pulse">RUNNING</span>}
                        {status === 'failed' && <span className="text-[9px] text-red-400 font-mono font-bold">ERROR</span>}
                      </div>
                      <p className="text-[10px] text-slate-400 mt-0.5">{step.description}</p>
                    </div>

                  </div>
                );
              })}
            </div>
          </div>

          {/* Results Block */}
          <div className="mt-6 pt-5 border-t border-slate-800">
            {resultState === 'none' && !isIngesting && (
              <div className="bg-slate-950 p-4 rounded-lg border border-slate-800/80 flex items-start gap-3">
                <HelpCircle className="w-5 h-5 text-slate-400 shrink-0 mt-0.5" />
                <div>
                  <p className="text-xs font-semibold text-slate-300">Ready for index deployment</p>
                  <p className="text-[10px] text-slate-500 mt-0.5">
                    Select a document configuration on the left and trigger ingestion. The RAG pipeline will parse text and register embeddings in local FAISS workspace.
                  </p>
                </div>
              </div>
            )}

            {resultState === 'success' && (
              <div className="bg-teal-400/10 border border-teal-500/20 p-4 rounded-lg flex items-start gap-3 animate-fade-in" id="ingest-success-alert">
                <CheckCircle className="w-5 h-5 text-teal-400 shrink-0 mt-0.5" />
                <div className="flex-1">
                  <p className="text-xs font-bold text-teal-400 uppercase tracking-wide">Corpus Registered Successfully</p>
                  <p className="text-[10px] text-slate-400 mt-1">
                    Document <strong className="text-slate-200 font-mono font-bold">{fileName}</strong> has been fully serialized. {pageSize * 4} chunks are indexed at 768 dimensions.
                  </p>
                  <div className="mt-3 flex gap-2">
                    <button
                      onClick={onNavigateToLibrary}
                      className="text-[10px] bg-teal-400/10 hover:bg-teal-400/20 text-teal-300 font-bold uppercase tracking-wider px-2.5 py-1 rounded border border-teal-500/20 transition-all flex items-center gap-1 cursor-pointer"
                      id="view-library-btn"
                    >
                      Inspect Library
                      <ArrowRight className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              </div>
            )}

            {resultState === 'failed' && (
              <div className="bg-red-950/20 border border-red-500/30 p-4 rounded-lg flex items-start gap-3 animate-fade-in" id="ingest-failure-alert">
                <XCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
                <div>
                  <p className="text-xs font-bold text-red-400 uppercase tracking-wide">Ingestion Pipeline Failed</p>
                  <p className="text-[10px] text-slate-400 mt-1 leading-relaxed">
                    {errorMessage}
                  </p>
                  <p className="text-[10px] text-slate-500 mt-2">
                    Check your GPU resources, ensure local model host is reachable on Port 3000, or turn off "simulation failure" configuration to try again.
                  </p>
                </div>
              </div>
            )}
          </div>

        </div>

      </div>

    </div>
  );
}
