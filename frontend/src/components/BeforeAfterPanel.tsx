import { useState } from 'react';
import {
  TrendingDown,
  TrendingUp,
  Minus,
  CheckCircle2,
  AlertTriangle,
  History,
  ArrowRight,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';

export interface DeltaFinding {
  title: string;
  severity: 'critical' | 'high' | 'medium';
  what_happened?: string;
  impact?: string;
  recommendation?: string;
  suggested_fix?: string;
  discovered_by?: string;
  screenshot?: string | null;
}

export interface ReportDelta {
  previous_session_id?: string;
  previous_score: number;
  new_score: number;
  score_delta: number;
  previous_outcome: string;
  new_outcome: string;
  resolved_findings: DeltaFinding[];
  new_findings: DeltaFinding[];
  persistent_findings: DeltaFinding[];
}

interface BeforeAfterPanelProps {
  delta: ReportDelta;
}

export function BeforeAfterPanel({ delta }: BeforeAfterPanelProps) {
  const [activeTab, setActiveTab] = useState<'resolved' | 'new' | 'persistent'>('resolved');
  const [isCollapsed, setIsCollapsed] = useState(false);

  const isImproved = delta.score_delta < 0;
  const isRegressed = delta.score_delta > 0;

  const resolvedCount = delta.resolved_findings?.length ?? 0;
  const newCount = delta.new_findings?.length ?? 0;
  const persistentCount = delta.persistent_findings?.length ?? 0;

  return (
    <div className="bg-gradient-to-r from-bg-card/90 via-black/80 to-bg-card/90 border border-gremlin-purple/40 rounded-xl overflow-hidden shadow-2xl transition-all">
      {/* Header bar */}
      <div className="px-6 py-4 bg-black/60 border-b border-gray-800/80 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gremlin-purple/20 border border-gremlin-purple/40 flex items-center justify-center">
            <History className="w-4 h-4 text-gremlin-purple" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold uppercase tracking-wider text-white">
                Re-Test Usability Comparison
              </h2>
              {delta.previous_session_id && (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-gray-800 text-gray-400 border border-gray-700">
                  vs {delta.previous_session_id.slice(0, 8)}
                </span>
              )}
            </div>
            <p className="text-xs text-gray-400">
              Automated delta against previous audit session
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Score Delta Badge */}
          <div
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border font-mono text-xs font-bold tracking-tight shadow-md ${
              isImproved
                ? 'bg-emerald-950/70 border-emerald-500/60 text-gremlin-green'
                : isRegressed
                ? 'bg-rose-950/70 border-rose-500/60 text-red-400'
                : 'bg-gray-800/80 border-gray-700 text-gray-300'
            }`}
          >
            {isImproved ? (
              <TrendingDown className="w-4 h-4" />
            ) : isRegressed ? (
              <TrendingUp className="w-4 h-4" />
            ) : (
              <Minus className="w-4 h-4" />
            )}
            <span>
              {delta.score_delta > 0 ? `+${delta.score_delta}` : delta.score_delta} pts{' '}
              {isImproved ? '(Improved!)' : isRegressed ? '(Regressed)' : '(Unchanged)'}
            </span>
          </div>

          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="p-1.5 rounded-lg bg-gray-800/60 hover:bg-gray-700 text-gray-400 hover:text-white transition-colors cursor-pointer"
            title={isCollapsed ? 'Expand delta panel' : 'Collapse delta panel'}
          >
            {isCollapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {!isCollapsed && (
        <div className="p-6 space-y-5">
          {/* Top Comparison Metrics Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Score Delta Card */}
            <div className="bg-black/40 border border-gray-800 rounded-lg p-4 flex items-center justify-between">
              <div>
                <span className="text-[11px] font-bold uppercase tracking-wider text-gray-400 block mb-1">
                  Friction Score Delta
                </span>
                <div className="flex items-center gap-3">
                  <span className="text-2xl font-black text-gray-400 font-mono">
                    {delta.previous_score}
                  </span>
                  <ArrowRight className="w-4 h-4 text-gray-600" />
                  <span
                    className={`text-3xl font-black font-mono ${
                      delta.new_score <= 20
                        ? 'text-gremlin-green'
                        : delta.new_score <= 45
                        ? 'text-amber-400'
                        : 'text-red-500'
                    }`}
                  >
                    {delta.new_score}
                  </span>
                  <span className="text-xs text-gray-500 font-mono">/ 100</span>
                </div>
              </div>
              <div className="text-right">
                <span className="text-[10px] text-gray-500 uppercase font-semibold block">
                  Net Impact
                </span>
                <span
                  className={`text-sm font-extrabold ${
                    isImproved
                      ? 'text-gremlin-green'
                      : isRegressed
                      ? 'text-red-400'
                      : 'text-gray-400'
                  }`}
                >
                  {isImproved
                    ? `${Math.abs(delta.score_delta)} pts lower friction`
                    : isRegressed
                    ? `${delta.score_delta} pts more friction`
                    : 'Identical friction score'}
                </span>
              </div>
            </div>

            {/* Outcome Comparison Card */}
            <div className="bg-black/40 border border-gray-800 rounded-lg p-4 flex items-center justify-between">
              <div>
                <span className="text-[11px] font-bold uppercase tracking-wider text-gray-400 block mb-1">
                  Task Completion Status
                </span>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono uppercase px-2 py-0.5 rounded bg-gray-800 text-gray-300">
                    {delta.previous_outcome}
                  </span>
                  <ArrowRight className="w-3.5 h-3.5 text-gray-600" />
                  <span
                    className={`text-xs font-mono uppercase px-2.5 py-1 rounded font-bold border ${
                      delta.new_outcome === 'completed'
                        ? 'bg-emerald-950/70 border-emerald-500/50 text-emerald-300'
                        : 'bg-rose-950/70 border-rose-500/50 text-rose-300'
                    }`}
                  >
                    {delta.new_outcome}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-1.5 text-xs text-gray-400 font-medium">
                {delta.previous_outcome !== 'completed' && delta.new_outcome === 'completed' ? (
                  <span className="flex items-center gap-1 text-gremlin-green font-semibold">
                    <ShieldCheck className="w-4 h-4" /> Blockers Solved
                  </span>
                ) : (
                  <span>Outcome verified</span>
                )}
              </div>
            </div>
          </div>

          {/* Findings Filter Tabs */}
          <div className="border-t border-gray-800/80 pt-4">
            <div className="flex items-center gap-2 mb-3">
              <button
                onClick={() => setActiveTab('resolved')}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition-all cursor-pointer ${
                  activeTab === 'resolved'
                    ? 'bg-emerald-950/80 border-emerald-500/80 text-emerald-300 shadow-sm'
                    : 'bg-black/30 border-gray-800 text-gray-400 hover:text-white hover:border-gray-700'
                }`}
              >
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                <span>Resolved Findings</span>
                <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-emerald-900/60 text-emerald-300 border border-emerald-500/30">
                  {resolvedCount}
                </span>
              </button>

              <button
                onClick={() => setActiveTab('new')}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition-all cursor-pointer ${
                  activeTab === 'new'
                    ? 'bg-rose-950/80 border-rose-500/80 text-rose-300 shadow-sm'
                    : 'bg-black/30 border-gray-800 text-gray-400 hover:text-white hover:border-gray-700'
                }`}
              >
                <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
                <span>New Findings</span>
                <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-rose-900/60 text-rose-300 border border-rose-500/30">
                  {newCount}
                </span>
              </button>

              <button
                onClick={() => setActiveTab('persistent')}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition-all cursor-pointer ${
                  activeTab === 'persistent'
                    ? 'bg-amber-950/80 border-amber-500/80 text-amber-300 shadow-sm'
                    : 'bg-black/30 border-gray-800 text-gray-400 hover:text-white hover:border-gray-700'
                }`}
              >
                <History className="w-3.5 h-3.5 text-amber-400" />
                <span>Persistent Findings</span>
                <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-amber-900/60 text-amber-300 border border-amber-500/30">
                  {persistentCount}
                </span>
              </button>
            </div>

            {/* Findings List per Active Tab */}
            <div className="space-y-2.5">
              {activeTab === 'resolved' && (
                resolvedCount === 0 ? (
                  <p className="text-xs text-gray-500 italic py-2">
                    No findings were completely resolved compared to the previous test run.
                  </p>
                ) : (
                  delta.resolved_findings.map((f, idx) => (
                    <div
                      key={idx}
                      className="p-3.5 bg-emerald-950/20 border border-emerald-500/30 rounded-lg flex items-start justify-between gap-4"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                          <span className="text-xs font-bold text-emerald-200 line-through">
                            {f.title}
                          </span>
                          <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-emerald-900/60 text-emerald-300 border border-emerald-500/30 font-semibold">
                            RESOLVED
                          </span>
                        </div>
                        {f.what_happened && (
                          <p className="text-xs text-gray-400 pl-6">{f.what_happened}</p>
                        )}
                      </div>
                      <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-black/40 text-gray-400 border border-gray-800 shrink-0">
                        {f.severity}
                      </span>
                    </div>
                  ))
                )
              )}

              {activeTab === 'new' && (
                newCount === 0 ? (
                  <p className="text-xs text-gray-500 italic py-2">
                    No new usability issues or defects were detected in this re-test.
                  </p>
                ) : (
                  delta.new_findings.map((f, idx) => (
                    <div
                      key={idx}
                      className="p-3.5 bg-rose-950/20 border border-rose-500/30 rounded-lg flex items-start justify-between gap-4"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                          <span className="text-xs font-bold text-rose-200">
                            {f.title}
                          </span>
                          <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-rose-900/60 text-rose-300 border border-rose-500/30 font-semibold animate-pulse">
                            NEW
                          </span>
                        </div>
                        {f.what_happened && (
                          <p className="text-xs text-gray-300 pl-6">{f.what_happened}</p>
                        )}
                        {f.recommendation && (
                          <p className="text-xs text-gremlin-green pl-6">
                            Fix: {f.recommendation}
                          </p>
                        )}
                      </div>
                      <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-500/40 shrink-0 font-bold">
                        {f.severity}
                      </span>
                    </div>
                  ))
                )
              )}

              {activeTab === 'persistent' && (
                persistentCount === 0 ? (
                  <p className="text-xs text-gray-500 italic py-2">
                    None of the previous findings persisted into this re-test.
                  </p>
                ) : (
                  delta.persistent_findings.map((f, idx) => (
                    <div
                      key={idx}
                      className="p-3.5 bg-gray-900/40 border border-amber-500/20 rounded-lg flex items-start justify-between gap-4"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <History className="w-4 h-4 text-amber-400 shrink-0" />
                          <span className="text-xs font-bold text-gray-200">
                            {f.title}
                          </span>
                          <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-amber-950/60 text-amber-300 border border-amber-500/30 font-semibold">
                            STILL PERSISTS
                          </span>
                        </div>
                        {f.what_happened && (
                          <p className="text-xs text-gray-400 pl-6">{f.what_happened}</p>
                        )}
                        {f.recommendation && (
                          <p className="text-xs text-gremlin-green pl-6">
                            Fix: {f.recommendation}
                          </p>
                        )}
                      </div>
                      <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-black/40 text-gray-400 border border-gray-800 shrink-0">
                        {f.severity}
                      </span>
                    </div>
                  ))
                )
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
