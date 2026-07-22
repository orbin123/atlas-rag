import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, CheckCircle, Database, FileText, Folder, Loader2, Plus, Upload, XCircle } from 'lucide-react';
import { uploadDocument } from '../api/documents';
import { useIngestionJob } from '../hooks/useIngestionJob';
import type { SystemInfo } from '../types';
import { formatBytes, isTerminalJob } from '../types';
import { ErrorNotice } from './AsyncNotice';

interface Props { system: SystemInfo | null; onCompleted: (documentId: string) => Promise<void>; onNavigateToLibrary: () => void }

const stages = ['validating', 'extracting', 'cleaning', 'chunking', 'embedding', 'indexing', 'finalizing'];

export default function UploadDocuments({ system, onCompleted, onNavigateToLibrary }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [domain, setDomain] = useState('user-uploaded');
  const [title, setTitle] = useState('');
  const [author, setAuthor] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [licenseNote, setLicenseNote] = useState('');
  const [includeEvaluationCases, setIncludeEvaluationCases] = useState(false);
  const [evaluationQuestions, setEvaluationQuestions] = useState(['', '', '']);
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);
  const { job, error: pollingError } = useIngestionJob(jobId);

  useEffect(() => {
    if (!job || !isTerminalJob(job.status) || completed) return;
    if (job.status === 'succeeded' && (job.documentId || documentId)) {
      setCompleted(true); void onCompleted(job.documentId || documentId!);
    } else if (job.status !== 'succeeded') {
      setError(job.error?.message || `Ingestion ended with status ${job.status}.`);
    }
  }, [job, completed, documentId, onCompleted]);

  const choose = (candidate: File | null) => {
    if (!candidate) return;
    setError(null); setCompleted(false); setJobId(null); setDocumentId(null); setFile(candidate);
  };
  const submit = async () => {
    if (!file) { setError('Choose a PDF, DOCX, or TXT file first.'); return; }
    const questions = evaluationQuestions.map(question => question.trim());
    if (includeEvaluationCases && questions.some(question => !question)) { setError('Write all three evaluation questions before starting ingestion.'); return; }
    if (includeEvaluationCases && new Set(questions.map(question => question.toLocaleLowerCase())).size !== questions.length) { setError('Evaluation questions must be unique.'); return; }
    setSubmitting(true); setError(null); setCompleted(false);
    try {
      const accepted = await uploadDocument(file, { domain, title, author, sourceUrl, licenseNote, evaluationQuestions: includeEvaluationCases ? questions : undefined });
      setDocumentId(accepted.documentId); setJobId(accepted.jobId);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Upload could not be accepted.'); }
    finally { setSubmitting(false); }
  };
  const currentIndex = job?.stage ? stages.indexOf(job.stage) : -1;
  const busy = submitting || (!!job && !isTerminalJob(job.status));

  return <div className="space-y-6 animate-fade-in" id="upload-document-page">
    <button onClick={onNavigateToLibrary} className="flex items-center gap-1.5 text-[10px] font-bold font-mono text-slate-400 hover:text-teal-400 uppercase"><ArrowLeft className="w-4 h-4" />Back to Document Library</button>
    <div><h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2"><Upload className="w-6 h-6 text-teal-400" />Document Ingestion</h1><p className="text-xs text-slate-400">Upload a real file and monitor the durable backend pipeline through indexing.</p></div>
    {(error || pollingError) && <ErrorNotice message={error || pollingError || ''} />}
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <div className="lg:col-span-7 space-y-5">
        <button type="button" disabled={busy} onClick={() => input.current?.click()} onDragOver={event => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={event => { event.preventDefault(); setDragging(false); choose(event.dataTransfer.files[0] || null); }} className={`w-full border-2 border-dashed p-8 rounded-xl text-center ${dragging ? 'border-teal-500 bg-teal-500/5' : 'border-slate-700 bg-slate-900'} disabled:opacity-50`}>
          <Upload className="w-10 h-10 mx-auto mb-3 text-teal-400" /><p className="text-sm font-bold">{file ? file.name : 'Choose or drop a document'}</p><p className="text-xs text-slate-400 mt-1">{file ? `${formatBytes(file.size)} · ${file.type || 'unknown MIME'}` : `PDF, DOCX, TXT · maximum ${system ? formatBytes(system.capabilities.maximumUploadBytes) : 'configured by server'}`}</p>
        </button>
        <input ref={input} type="file" className="hidden" accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain" onChange={event => choose(event.target.files?.[0] || null)} />
        <div className="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-4">
          <label className="block text-[10px] uppercase font-mono text-slate-500">Domain<input value={domain} disabled={busy} maxLength={255} onChange={event => setDomain(event.target.value)} className="mt-1 w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200" /></label>
          <label className="block text-[10px] uppercase font-mono text-slate-500">Title (optional)<input value={title} disabled={busy} onChange={event => setTitle(event.target.value)} className="mt-1 w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200" /></label>
          <label className="block text-[10px] uppercase font-mono text-slate-500">Author (optional)<input value={author} disabled={busy} onChange={event => setAuthor(event.target.value)} className="mt-1 w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200" /></label>
          <label className="block text-[10px] uppercase font-mono text-slate-500">Trusted source URL (optional)<input type="url" value={sourceUrl} disabled={busy} onChange={event => setSourceUrl(event.target.value)} className="mt-1 w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200" /></label>
          <label className="block text-[10px] uppercase font-mono text-slate-500">License note (optional)<textarea value={licenseNote} disabled={busy} onChange={event => setLicenseNote(event.target.value)} className="mt-1 w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200" /></label>
          <fieldset className="border border-slate-700 rounded-lg p-3 space-y-3"><legend className="px-1 text-[10px] uppercase font-mono text-teal-400">Evaluation cases</legend><label className="flex items-center gap-2 text-xs text-slate-300"><input type="checkbox" checked={includeEvaluationCases} disabled={busy} onChange={event => setIncludeEvaluationCases(event.target.checked)} className="accent-teal-400" />Add evaluation cases for this upload (optional)</label>{includeEvaluationCases && <><p className="text-[10px] text-slate-400">Provide at least three questions. They will be evaluated against this document after it indexes.</p>{evaluationQuestions.map((question, index) => <label key={index} className="block text-[10px] uppercase font-mono text-slate-500">Question {index + 1}<textarea value={question} disabled={busy} maxLength={2000} required onChange={event => setEvaluationQuestions(current => current.map((value, questionIndex) => questionIndex === index ? event.target.value : value))} className="mt-1 min-h-16 w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200" /></label>)}<button type="button" disabled={busy} onClick={() => setEvaluationQuestions(current => [...current, ''])} className="flex items-center gap-1 text-[10px] font-bold text-teal-400 hover:text-teal-300 disabled:opacity-50"><Plus className="w-3.5 h-3.5" />Add question</button></>}</fieldset>
          <button onClick={() => void submit()} disabled={busy || !file} className="w-full flex items-center justify-center gap-2 bg-teal-500 hover:bg-teal-400 text-slate-950 text-xs font-bold py-2.5 rounded-lg uppercase disabled:opacity-40">{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Database className="w-4 h-4" />}{submitting ? 'Uploading…' : job && !isTerminalJob(job.status) ? 'Processing…' : 'Start Ingestion'}</button>
        </div>
      </div>
      <div className="lg:col-span-5 bg-slate-900 border border-slate-800 p-5 rounded-xl">
        <div className="flex justify-between items-center mb-5"><h2 className="text-xs font-bold uppercase font-mono text-slate-300">Durable ingestion job</h2><span className="text-xs text-teal-400 font-mono">{job?.progressPercent ?? 0}%</span></div>
        <div className="h-2 bg-slate-800 rounded-full overflow-hidden mb-6"><div className="h-full bg-teal-400 transition-all" style={{ width: `${job?.progressPercent ?? 0}%` }} /></div>
        <div className="space-y-3">{stages.map((stage, index) => { const done = job?.status === 'succeeded' || index < currentIndex; const active = index === currentIndex && job && !isTerminalJob(job.status); const failed = index === currentIndex && job?.status === 'failed'; return <div key={stage} className={`p-3 rounded-lg border flex items-center gap-3 ${active ? 'border-teal-500/50 bg-teal-500/5' : failed ? 'border-red-500/40 bg-red-500/5' : 'border-slate-800'}`}>{done ? <CheckCircle className="w-4 h-4 text-teal-400" /> : failed ? <XCircle className="w-4 h-4 text-red-400" /> : active ? <Loader2 className="w-4 h-4 animate-spin text-teal-400" /> : <span className="w-4 h-4 rounded-full border border-slate-600" />}<div><p className="text-xs font-bold capitalize">{stage}</p>{active && <p className="text-[10px] text-slate-400">{job.stageMessage || `Backend is ${stage} the document.`}</p>}</div></div>; })}</div>
        {!job && <div className="mt-6 p-4 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-400 flex gap-2"><FileText className="w-4 h-4 text-teal-400" />The server reports actual stages, counts, retries, and failures after upload acceptance.</div>}
        {job?.status === 'succeeded' && <div className="mt-5 text-sm text-teal-300 flex items-center gap-2"><CheckCircle className="w-4 h-4" />Indexed successfully. Opening the real document detail…</div>}
        {job?.error && <div className="mt-5 text-sm text-red-300 flex items-center gap-2"><XCircle className="w-4 h-4" />{job.error.code}: {job.error.message}</div>}
        {system && <div className="mt-6 pt-4 border-t border-slate-800 grid grid-cols-2 gap-3 text-[10px] font-mono text-slate-400"><span><Folder className="inline w-3 h-3 mr-1" />{system.chunking.targetTokens}/{system.chunking.maxTokens} tokens</span><span>{system.chunking.overlapTokens}-token overlap</span><span>{system.embedding.dimension}-D embeddings</span><span>OCR {system.capabilities.ocr ? 'enabled' : 'not supported'}</span></div>}
      </div>
    </div>
  </div>;
}
