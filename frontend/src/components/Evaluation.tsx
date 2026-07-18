import React, { useState } from 'react';
import { 
  BarChart4, 
  TrendingUp, 
  TrendingDown, 
  AlertOctagon, 
  Target, 
  ShieldCheck, 
  HelpCircle,
  FileCheck2,
  GitBranch,
  Search,
  CheckCircle2,
  XOctagon
} from 'lucide-react';
import { INITIAL_METRICS, DOMAIN_PERFORMANCE, FAILURE_ANALYSIS_DATA } from '../data';

export default function Evaluation() {
  const [activeMetricTab, setActiveMetricTab] = useState<'correctness' | 'groundedness' | 'recall'>('correctness');
  const [searchQuery, setSearchQuery] = useState('');

  // Filter failure analysis logs
  const filteredFailures = FAILURE_ANALYSIS_DATA.filter(fail => 
    fail.question.toLowerCase().includes(searchQuery.toLowerCase()) ||
    fail.category.toLowerCase().includes(searchQuery.toLowerCase()) ||
    fail.expectedSource.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="space-y-6 animate-fade-in" id="evaluation-analytics-page">
      
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-100 font-display flex items-center gap-2">
          <BarChart4 className="w-6 h-6 text-teal-400" />
          RAG Performance Evaluation
        </h1>
        <p className="text-xs text-slate-400">
          Continuous validation suite tracking information retrieval coverage, semantic precision, and grounding quality.
        </p>
      </div>

      {/* RAG KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" id="eval-kpi-grid">
        {INITIAL_METRICS.map((metric, idx) => {
          // Choose icon based on metric name
          let MetricIcon = Target;
          if (metric.name.includes('MRR')) MetricIcon = GitBranch;
          if (metric.name.includes('Correctness')) MetricIcon = FileCheck2;
          if (metric.name.includes('Groundedness')) MetricIcon = ShieldCheck;

          const isImprovement = metric.changeType === 'increase';

          return (
            <div 
              key={idx}
              className="bg-slate-900 border border-slate-800 p-4 rounded-xl relative overflow-hidden flex flex-col justify-between"
              id={`eval-kpi-card-${idx}`}
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] uppercase font-mono tracking-widest font-bold text-slate-500 truncate max-w-[120px]">
                    {metric.name.split(' (')[0]}
                  </span>
                  <div className="p-1.5 rounded bg-slate-950 text-teal-400 border border-slate-850">
                    <MetricIcon className="w-3.5 h-3.5" />
                  </div>
                </div>
                
                <h3 className="text-2xl font-bold text-slate-100 font-display mt-1">
                  {metric.value}
                </h3>
              </div>

              <div className="mt-4 flex items-center justify-between">
                <span className={`text-[10px] px-1.5 py-0.5 rounded flex items-center gap-0.5 font-mono font-bold ${
                  isImprovement ? 'bg-teal-400/10 text-teal-400 border border-teal-500/20' : 'bg-red-500/10 text-red-400 border border-red-500/20'
                }`}>
                  {isImprovement ? <TrendingUp className="w-2.5 h-2.5" /> : <TrendingDown className="w-2.5 h-2.5" />}
                  {metric.change}
                </span>
                <span className="text-[9px] text-slate-500 font-mono font-bold uppercase">Vs last run</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Domain Performance comparison chart */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Chart (7 cols) */}
        <div className="lg:col-span-8 bg-slate-900 border border-slate-800 p-5 rounded-xl flex flex-col justify-between" id="eval-chart-box">
          <div>
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6 border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-xs font-bold tracking-widest text-slate-400 uppercase flex items-center gap-1.5 font-mono">
                  <BarChart4 className="w-4 h-4 text-teal-400" />
                  Index Domain Quality Metrics
                </h3>
                <p className="text-[10px] text-slate-400">Comparing retriever & generation compliance across active document namespaces.</p>
              </div>

              {/* Chart Filter tabs */}
              <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-850">
                <button
                  onClick={() => setActiveMetricTab('correctness')}
                  className={`text-[10px] uppercase tracking-wider px-2.5 py-1 rounded font-mono font-bold transition-all ${
                    activeMetricTab === 'correctness' ? 'bg-slate-800 text-teal-400 border border-teal-500/30' : 'text-slate-500 hover:text-slate-300'
                  }`}
                  id="tab-chart-correctness"
                >
                  Correctness
                </button>
                <button
                  onClick={() => setActiveMetricTab('groundedness')}
                  className={`text-[10px] uppercase tracking-wider px-2.5 py-1 rounded font-mono font-bold transition-all ${
                    activeMetricTab === 'groundedness' ? 'bg-slate-800 text-teal-400 border border-teal-500/30' : 'text-slate-500 hover:text-slate-300'
                  }`}
                  id="tab-chart-groundedness"
                >
                  Groundedness
                </button>
                <button
                  onClick={() => setActiveMetricTab('recall')}
                  className={`text-[10px] uppercase tracking-wider px-2.5 py-1 rounded font-mono font-bold transition-all ${
                    activeMetricTab === 'recall' ? 'bg-slate-800 text-teal-400 border border-teal-500/30' : 'text-slate-500 hover:text-slate-300'
                  }`}
                  id="tab-chart-recall"
                >
                  Recall@5
                </button>
              </div>
            </div>

            {/* Custom Responsive Horizontal Bar Chart */}
            <div className="space-y-5" id="custom-responsive-bar-chart">
              {DOMAIN_PERFORMANCE.map((item, index) => {
                // Determine current active metric value and color theme
                const val = activeMetricTab === 'correctness' ? item.correctness :
                            activeMetricTab === 'groundedness' ? item.groundedness : item.recall;
                
                const barColor = activeMetricTab === 'correctness' ? 'bg-teal-500' :
                                 activeMetricTab === 'groundedness' ? 'bg-teal-400' : 'bg-teal-600';

                return (
                  <div key={index} className="space-y-1.5" id={`chart-row-${index}`}>
                    <div className="flex justify-between items-center text-xs font-mono">
                      <span className="text-slate-300 font-bold uppercase">{item.domain}</span>
                      <span className="text-white font-extrabold">{val}%</span>
                    </div>
                    
                    <div className="flex items-center gap-3">
                      {/* Bar Background */}
                      <div className="w-full h-4 bg-slate-950 rounded border border-slate-850 overflow-hidden relative group">
                        {/* Dynamic Bar Fill */}
                        <div 
                          className={`h-full ${barColor} shadow-inner rounded-full transition-all duration-500`}
                          style={{ width: `${val}%` }}
                        />
                      </div>
                      
                      {/* Sub-KPI detail list */}
                      <span className="text-[10px] font-mono font-bold text-slate-500 shrink-0 w-14 text-right uppercase">
                        MRR: {item.mrr}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="mt-6 pt-4 border-t border-slate-800 flex items-center justify-between text-[10px] text-slate-500 font-mono font-bold uppercase">
            <span>Validation frequency: Daily automatic cron</span>
            <span>Total testing cases: 480 queries</span>
          </div>
        </div>

        {/* Failure Explanation side-panel (5 cols) */}
        <div className="lg:col-span-4 bg-slate-900 border border-slate-800 p-5 rounded-xl flex flex-col justify-between" id="eval-failures-panel">
          <div>
            <h3 className="text-[10px] font-bold tracking-widest text-slate-400 uppercase flex items-center gap-1.5 font-mono mb-2">
              <AlertOctagon className="w-4 h-4 text-red-400" />
              RAG Guardrail Explanations
            </h3>
            <p className="text-[11px] text-slate-400 mb-4">
              Atlas employs a multi-tiered defense sequence to identify failures and handle anomalies:
            </p>

            <div className="space-y-4 text-xs font-sans">
              <div className="p-3 bg-red-950/20 border border-red-500/20 rounded-lg">
                <p className="font-bold font-mono text-[10px] uppercase tracking-wide text-red-400 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
                  Anti-Hallucination Safe Halt
                </p>
                <p className="text-[10px] text-slate-400 mt-1">
                  If cosine similarity is lower than <span className="font-mono font-bold text-slate-300">0.72</span>, generation is immediately aborted, rendering the "Insufficient Context" message.
                </p>
              </div>

              <div className="p-3 bg-slate-950 border border-slate-850 rounded-lg">
                <p className="font-bold font-mono text-[10px] uppercase tracking-wide text-slate-300 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-teal-400" />
                  Mean Reciprocal Rank (MRR)
                </p>
                <p className="text-[10px] text-slate-400 mt-1">
                  Assesses how high up the list the first correct source occurs. Ensures users read correct references first.
                </p>
              </div>

              <div className="p-3 bg-slate-950 border border-slate-850 rounded-lg">
                <p className="font-bold font-mono text-[10px] uppercase tracking-wide text-slate-300 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-teal-400" />
                  Groundedness Checking
                </p>
                <p className="text-[10px] text-slate-400 mt-1">
                  A verification step comparison mapping generated text sentences against source text coordinates.
                </p>
              </div>
            </div>
          </div>

          <p className="text-[10px] text-slate-500 font-mono font-bold uppercase mt-4">
            Validation host runs locally via synthetic query generation against indexed corpus vectors.
          </p>
        </div>

      </div>

      {/* Failure Analysis Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden" id="eval-failures-table">
        <div className="p-4 border-b border-slate-800 bg-slate-950 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h3 className="text-[10px] font-bold tracking-widest text-slate-400 uppercase flex items-center gap-1.5 font-mono">
              <AlertOctagon className="w-4 h-4 text-red-400" />
              Failure Analysis Logs
            </h3>
            <p className="text-[10px] text-slate-400 mt-0.5">Auditing queries where grounding validation flag generated errors.</p>
          </div>

          {/* Table Search */}
          <div className="relative">
            <Search className="absolute left-3 top-2.5 w-3.5 h-3.5 text-slate-500" />
            <input
              type="text"
              placeholder="Search failures by keyword..."
              className="bg-slate-850 border border-slate-700 rounded-lg pl-8.5 pr-4 py-1 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-teal-500 font-semibold"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              id="failure-analysis-search"
            />
          </div>
        </div>

        {filteredFailures.length === 0 ? (
          <div className="text-center py-10 text-slate-500">
            <CheckCircle2 className="w-10 h-10 mx-auto mb-2 text-teal-400 opacity-60" />
            <p className="text-xs font-bold uppercase tracking-wide">No active failures match search parameters.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-slate-950 border-b border-slate-800 text-[10px] uppercase font-mono tracking-widest font-bold text-slate-500">
                  <th className="p-4 pl-6">Research Question</th>
                  <th className="p-4">Expected Source</th>
                  <th className="p-4">Retrieved Source</th>
                  <th className="p-4">Anomaly Category</th>
                  <th className="p-4 pr-6">Validation Result Summary</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-xs">
                {filteredFailures.map((fail) => (
                  <tr key={fail.id} className="hover:bg-slate-800/30 transition-colors" id={`fail-row-${fail.id}`}>
                    {/* Question */}
                    <td className="p-4 pl-6 text-slate-200 font-semibold max-w-[220px]">
                      {fail.question}
                    </td>

                    {/* Expected */}
                    <td className="p-4 font-mono text-[11px] text-slate-400 font-bold">
                      {fail.expectedSource}
                    </td>

                    {/* Retrieved */}
                    <td className={`p-4 font-mono text-[11px] font-bold ${
                      fail.retrievedSource === 'No Context Retrieved' ? 'text-red-400' : 'text-slate-500'
                    }`}>
                      {fail.retrievedSource}
                    </td>

                    {/* Category badge */}
                    <td className="p-4">
                      <span className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded font-mono font-bold uppercase tracking-wider ${
                        fail.category === 'No Context Retrieved' ? 'bg-red-500/10 text-red-400 border border-red-500/20' :
                        fail.category === 'Irrelevant Chunk' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                        'bg-pink-500/10 text-pink-400 border border-pink-500/20'
                      }`}>
                        <XOctagon className="w-3 h-3 shrink-0" />
                        {fail.category}
                      </span>
                    </td>

                    {/* Result */}
                    <td className="p-4 pr-6 text-slate-400 text-[11px] leading-relaxed max-w-[280px]">
                      {fail.result}
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
