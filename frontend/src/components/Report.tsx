import { useEffect, useState } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  RefreshCcw,
  ShieldAlert,
  Share2,
  Download,
  Printer,
  RotateCcw,
  Check,
} from 'lucide-react';
import { ComparisonSummary, type ComparisonItem } from './ComparisonSummary';
import { BeforeAfterPanel, type ReportDelta } from './BeforeAfterPanel';

export interface HistoryItem {
  thought: string;
  screenshot: string | null;
  step_number?: number;
  action?: string;
}

export interface ActionItem {
  step_number: number;
  action: string;
  target?: string;
  thought: string;
  screenshot: string | null;
  ok?: boolean;
  url?: string;
  url_after?: string;
  friction_type?: string | null;
  friction_note?: string;
}

interface ScorePart {
  name: string;
  points: number;
  evidence: number[];
  why: string;
}

export interface Finding {
  title: string;
  severity: 'critical' | 'high' | 'medium';
  evidence_steps: number[];
  what_happened: string;
  impact: string;
  recommendation: string;
  consistency?: 'consistent' | 'occasional';
  step_number?: number;
  screenshot?: string | null;
  bounding_box?: { x: number; y: number; width: number; height: number } | null;
  suggested_fix?: string;
  selector?: string;
  discovered_by?: string;
}

export interface SabotageReport {
  session_id?: string;
  previous_session_id?: string;
  delta?: ReportDelta;
  url?: string;
  task?: string;
  persona?: string;
  personas?: string[];
  is_compare?: boolean;
  comparison?: Record<string, ComparisonItem>;
  comparison_summary?: ComparisonItem[];
  persona_reports?: Record<string, SabotageReport>;
  outcome?: 'completed' | 'abandoned' | 'gave_up' | 'max_steps_reached' | 'error';
  outcome_reason?: string;
  claimed_outcome?: string;
  verified_outcome?: string;
  baseline_failed?: boolean;
  baseline_note?: string;
  expected_steps?: number;
  runs?: number;
  score_min?: number;
  score_max?: number;
  score_mean?: number;
  score: {
    total: number;
    label: string;
    parts: ScorePart[];
    steps_taken: number;
    ideal_steps: number;
    runs?: number;
    score_min?: number;
    score_max?: number;
    score_mean?: number;
  };
  verdict: string;
  findings: Finding[];
  bugs?: number;
  actions?: ActionItem[];
}

export interface ReportProps {
  session: {
    session_id?: string;
    previous_session_id?: string;
    url: string;
    task: string;
    persona: string;
    personas?: string[];
  };
  history: HistoryItem[];
  initialReport?: SabotageReport | null;
  isReadOnly?: boolean;
  onRestart: () => void;
  onReRun?: (prevSession: {
    url: string;
    task: string;
    persona: string;
    personas?: string[];
    previous_session_id: string;
  }) => void;
}

const PERSONA_NAMES: Record<string, string> = {
  pro_tester: '🎯 Professional UX Tester',
  impatient: '😈 Impatient User',
  confused: '😵‍💫 Confused User',
  skeptic: '🧐 Skeptical User',
  mobile: '📱 Mobile User',
};

const OUTCOME_CONFIG: Record<
  string,
  { label: string; bg: string; border: string; text: string; dot: string }
> = {
  completed: {
    label: 'Completed',
    bg: 'bg-emerald-950/60',
    border: 'border-emerald-500/50',
    text: 'text-emerald-400',
    dot: 'bg-emerald-400',
  },
  abandoned: {
    label: 'Abandoned',
    bg: 'bg-amber-950/60',
    border: 'border-amber-500/50',
    text: 'text-amber-400',
    dot: 'bg-amber-400',
  },
  gave_up: {
    label: 'Gave Up',
    bg: 'bg-rose-950/60',
    border: 'border-rose-500/50',
    text: 'text-rose-400',
    dot: 'bg-rose-400',
  },
  max_steps_reached: {
    label: 'Max Steps Reached',
    bg: 'bg-amber-950/60',
    border: 'border-amber-500/50',
    text: 'text-amber-400',
    dot: 'bg-amber-400',
  },
  error: {
    label: 'Execution Error',
    bg: 'bg-rose-950/60',
    border: 'border-rose-500/50',
    text: 'text-rose-400',
    dot: 'bg-rose-400',
  },
};

export function Report({
  session,
  history,
  initialReport,
  isReadOnly,
  onRestart,
  onReRun,
}: ReportProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [report, setReport] = useState<SabotageReport | null>(initialReport || null);
  const [copiedShare, setCopiedShare] = useState(false);
  const [selectedPersona, setSelectedPersona] = useState<string>(
    initialReport?.personas?.[0] || session.personas?.[0] || session.persona
  );

  const currentSessionId = report?.session_id || session.session_id;

  const handleShare = async () => {
    if (!currentSessionId) return;
    const shareUrl = `${window.location.origin}/report/${currentSessionId}`;
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopiedShare(true);
      setTimeout(() => setCopiedShare(false), 2500);
    } catch {
      prompt('Copy shareable report link:', shareUrl);
    }
  };

  const handleExportJson = () => {
    if (!currentSessionId) return;
    window.open(
      `http://127.0.0.1:8000/api/report/${encodeURIComponent(currentSessionId)}/export/json`,
      '_blank'
    );
  };

  const handlePrintHtml = () => {
    if (!currentSessionId) return;
    window.open(
      `http://127.0.0.1:8000/api/report/${encodeURIComponent(currentSessionId)}/export/html`,
      '_blank'
    );
  };

  useEffect(() => {
    if (initialReport && initialReport.score) {
      return;
    }

    let cancelled = false;
    let tries = 0;
    const reportUrl = session.session_id
      ? `http://127.0.0.1:8000/api/report?session_id=${encodeURIComponent(session.session_id)}`
      : 'http://127.0.0.1:8000/api/report';

    const load = async () => {
      try {
        const res = await fetch(reportUrl);
        const data = await res.json();
        if (data?.score || data?.comparison) {
          if (!cancelled) {
            setReport(data as SabotageReport);
            if (data.personas && data.personas.length > 0) {
              setSelectedPersona((curr) =>
                data.personas.includes(curr) ? curr : data.personas[0]
              );
            }
            if (session.session_id && !window.location.pathname.startsWith('/report/')) {
              window.history.pushState(null, '', `/report/${session.session_id}`);
            }
          }
          return;
        }
      } catch {
        /* retry below */
      }
      if (!cancelled && ++tries < 15) setTimeout(load, 1000);
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [session.session_id, initialReport]);

  // Active persona report (for switching between archetypes)
  const activeReport: SabotageReport =
    (report?.persona_reports && report.persona_reports[selectedPersona]) ||
    report ||
    ({} as SabotageReport);

  // ONE source of truth: the backend's saved action list
  const slideshowItems: (ActionItem | HistoryItem)[] =
    activeReport?.actions && activeReport.actions.length > 0
      ? activeReport.actions
      : report?.actions && report.actions.length > 0
      ? report.actions
      : history;
  const totalSteps = slideshowItems.length;

  const jumpToStep = (n: number) => {
    if (activeReport?.actions && activeReport.actions.length > 0) {
      const idx = activeReport.actions.findIndex((a) => a.step_number === n);
      if (idx >= 0) {
        setCurrentIndex(idx);
        return;
      }
    }
    const prefix = `Step ${n} · `;
    const exec = history.findIndex((h) => h.thought.startsWith(`${prefix}Executing`));
    const any = history.findIndex((h) => h.thought.startsWith(prefix));
    const i = exec >= 0 ? exec : any;
    if (i >= 0) setCurrentIndex(i);
  };

  const currentScore = activeReport?.score || report?.score;
  const total = currentScore?.total ?? 0;
  const scoreColor =
    total <= 20
      ? 'text-gremlin-green'
      : total <= 45
      ? 'text-amber-400'
      : total <= 70
      ? 'text-orange-400'
      : 'text-red-500';

  const handlePrev = () => {
    setCurrentIndex((prev) => Math.max(0, prev - 1));
  };

  const handleNext = () => {
    setCurrentIndex((prev) => Math.min(Math.max(0, totalSteps - 1), prev + 1));
  };

  const currentItem = slideshowItems[currentIndex];
  const outcome = activeReport?.outcome || report?.outcome;
  const outcomeReason = activeReport?.outcome_reason || report?.outcome_reason;
  const claimedOutcome = activeReport?.claimed_outcome || report?.claimed_outcome;
  const verifiedOutcome = activeReport?.verified_outcome || report?.verified_outcome;
  const currentFindings =
    activeReport?.findings && activeReport.findings.length > 0
      ? activeReport.findings
      : report?.findings || [];

  return (
    <div className="h-screen w-screen flex flex-col bg-bg-dark text-white">
      {/* Header */}
      <div className="h-16 border-b border-gray-800 flex items-center justify-between px-6 bg-bg-card shrink-0 gap-4">
        <div className="flex items-center gap-3">
          <ShieldAlert className="text-gremlin-purple w-6 h-6" />
          <h1 className="text-xl font-bold uppercase tracking-widest text-transparent bg-clip-text bg-gradient-to-r from-gremlin-purple to-gremlin-green">
            Sabotage Report
          </h1>
          {isReadOnly && (
            <span className="text-[11px] font-mono px-2.5 py-0.5 rounded bg-gremlin-purple/20 text-purple-300 border border-gremlin-purple/40">
              Archived Report
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Share Button */}
          <button
            onClick={handleShare}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-xs font-semibold rounded-lg border border-gray-700 text-gray-200 transition-colors cursor-pointer"
            title="Copy shareable report link"
          >
            {copiedShare ? (
              <>
                <Check className="w-3.5 h-3.5 text-gremlin-green" />
                <span className="text-gremlin-green">Copied!</span>
              </>
            ) : (
              <>
                <Share2 className="w-3.5 h-3.5 text-gray-400" />
                <span>Share</span>
              </>
            )}
          </button>

          {/* Export JSON Button */}
          <button
            onClick={handleExportJson}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-xs font-semibold rounded-lg border border-gray-700 text-gray-200 transition-colors cursor-pointer"
            title="Download JSON report payload"
          >
            <Download className="w-3.5 h-3.5 text-gray-400" />
            <span>Export JSON</span>
          </button>

          {/* Print / PDF Button */}
          <button
            onClick={handlePrintHtml}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-xs font-semibold rounded-lg border border-gray-700 text-gray-200 transition-colors cursor-pointer"
            title="Print or save as PDF"
          >
            <Printer className="w-3.5 h-3.5 text-gray-400" />
            <span>Print / PDF</span>
          </button>

          {/* Re-run Test Button */}
          {onReRun && (
            <button
              onClick={() => {
                const targetSessionId = report?.session_id || session.session_id;
                if (!targetSessionId) return;
                onReRun({
                  url: report?.url || session.url,
                  task: report?.task || session.task,
                  persona: selectedPersona || session.persona,
                  personas: report?.personas || session.personas,
                  previous_session_id: targetSessionId,
                });
              }}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-gremlin-purple hover:bg-purple-600 text-xs font-bold rounded-lg text-white shadow-sm transition-all cursor-pointer"
              title="Re-run this test and link to previous session"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Re-run this test</span>
            </button>
          )}

          {/* New Attack / Restart Button */}
          <button
            onClick={onRestart}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-xs font-semibold rounded-lg text-gray-300 transition-colors cursor-pointer"
          >
            <RefreshCcw className="w-3.5 h-3.5" />
            <span>New Attack</span>
          </button>
        </div>
      </div>

      {/* Before / After Delta Panel if this was a Re-test */}
      {report?.delta && (
        <div className="border-b border-gray-800 bg-black/60 px-8 py-4 shrink-0 max-h-96 overflow-y-auto">
          <BeforeAfterPanel delta={report.delta} />
        </div>
      )}

      {/* Comparison Summary at top of Report */}
      {(report?.comparison ||
        report?.comparison_summary ||
        (session.personas && session.personas.length > 1)) && (
        <div className="border-b border-gray-800 bg-black/50 px-8 py-5 shrink-0 max-h-80 overflow-y-auto">
          <ComparisonSummary
            comparison={report?.comparison}
            comparisonSummary={report?.comparison_summary}
            selectedPersona={selectedPersona}
            onSelectPersona={(p) => {
              setSelectedPersona(p);
              setCurrentIndex(0);
            }}
          />
        </div>
      )}

      <div className="flex-1 flex overflow-hidden">
        {/* Left Side: Summary */}
        <div className="w-1/3 border-r border-gray-800 p-8 flex flex-col gap-6 overflow-y-auto">
          {outcome && (
            <div
              className={`p-4 rounded-xl border ${
                OUTCOME_CONFIG[outcome]?.bg ?? 'bg-gray-800/60'
              } ${
                OUTCOME_CONFIG[outcome]?.border ?? 'border-gray-700'
              } shadow-lg flex flex-col gap-2.5`}
            >
              <div className="flex items-center justify-between">
                <span className="text-[11px] uppercase tracking-wider text-gray-400 font-bold">
                  Task Outcome ({PERSONA_NAMES[selectedPersona]?.split(' ')[0] || selectedPersona})
                </span>
                {claimedOutcome &&
                  verifiedOutcome &&
                  claimedOutcome !== verifiedOutcome && (
                    <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-black/60 text-amber-300 border border-amber-500/30">
                      Claimed: {claimedOutcome} · Verified: {verifiedOutcome}
                    </span>
                  )}
              </div>
              <div className="flex items-center gap-2.5">
                <span
                  className={`w-3 h-3 rounded-full ${
                    OUTCOME_CONFIG[outcome]?.dot ?? 'bg-gray-400'
                  } animate-pulse`}
                />
                <span
                  className={`text-lg font-extrabold tracking-wide uppercase ${
                    OUTCOME_CONFIG[outcome]?.text ?? 'text-white'
                  }`}
                >
                  {OUTCOME_CONFIG[outcome]?.label ?? outcome}
                </span>
              </div>
              {outcomeReason && (
                <p className="text-xs text-gray-300 leading-relaxed pl-3 border-l-2 border-white/20 mt-0.5">
                  {outcomeReason}
                </p>
              )}
            </div>
          )}

          {(activeReport?.baseline_failed || report?.baseline_failed) && (
            <div className="p-4 rounded-xl border border-amber-500/50 bg-amber-950/40 text-amber-300 text-xs flex items-start gap-3 shadow-lg">
              <ShieldAlert className="w-5 h-5 shrink-0 text-amber-400 mt-0.5" />
              <div>
                <span className="font-bold uppercase tracking-wider block text-[11px] text-amber-400 mb-0.5">
                  Baseline Warning
                </span>
                <span>
                  Task may be unreachable or unclear: direct baseline agent failed to achieve completion. Friction score fell back to heuristic step budget.
                </span>
              </div>
            </div>
          )}

          <div>
            <h2 className="text-gray-400 text-sm uppercase tracking-wider mb-2">Target</h2>
            <p className="font-mono text-lg">{activeReport?.url || report?.url || session.url}</p>
          </div>
          <div>
            <h2 className="text-gray-400 text-sm uppercase tracking-wider mb-2">Task</h2>
            <p className="text-lg">{activeReport?.task || report?.task || session.task}</p>
          </div>
          <div>
            <h2 className="text-gray-400 text-sm uppercase tracking-wider mb-2">Persona</h2>
            <div className="flex items-center gap-2">
              <p className="text-lg text-gremlin-purple font-semibold">
                {PERSONA_NAMES[selectedPersona] || selectedPersona}
              </p>
              {session.personas && session.personas.length > 1 && (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-gremlin-purple/20 text-purple-200 border border-gremlin-purple/40">
                  Compare View
                </span>
              )}
            </div>
            {session.personas && session.personas.length > 1 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {session.personas.map((p) => (
                  <button
                    key={p}
                    onClick={() => {
                      setSelectedPersona(p);
                      setCurrentIndex(0);
                    }}
                    className={`px-2.5 py-1 rounded text-xs font-semibold border transition-all cursor-pointer ${
                      selectedPersona === p
                        ? 'bg-gremlin-purple text-white border-gremlin-purple shadow-sm'
                        : 'bg-black/40 text-gray-400 border-gray-800 hover:border-gray-700 hover:text-white'
                    }`}
                  >
                    {PERSONA_NAMES[p]?.split(' ')[0] || p}
                  </button>
                ))}
              </div>
            )}
          </div>
          
          <div className="mt-8 p-6 bg-black/40 border border-gray-800 rounded-lg">
            <h2 className="text-gray-400 text-sm uppercase tracking-wider mb-4 text-center">
              Friction Score {session.personas && session.personas.length > 1 ? `(${PERSONA_NAMES[selectedPersona]?.split(' ')[0] || selectedPersona})` : ''}
            </h2>
            {!currentScore ? (
              <p className="text-center text-gray-500 text-sm">Generating report…</p>
            ) : (
              <>
                <div className="flex items-center justify-center gap-4">
                  <div className={`text-6xl font-black ${scoreColor}`}>{currentScore.total}</div>
                  {((report?.runs && report.runs > 1) || (currentScore.runs && currentScore.runs > 1)) && (
                    <div className="text-left bg-gray-900/90 border border-gray-700/70 rounded-lg px-3 py-1.5 shadow-sm">
                      <div className="text-sm font-extrabold text-white tracking-wide">
                        {report?.score_min ?? currentScore.score_min}–{report?.score_max ?? currentScore.score_max}
                      </div>
                      <div className="text-[11px] text-gremlin-green font-medium">
                        consistent across {report?.runs ?? currentScore.runs} runs
                      </div>
                    </div>
                  )}
                </div>
                <p className="text-center text-sm mt-1 text-gray-400">
                  {currentScore.label} friction · {currentScore.steps_taken} steps taken, about {currentScore.ideal_steps} expected
                  {activeReport?.baseline_failed || report?.baseline_failed ? ' (heuristic fallback)' : ''}
                </p>
                <p className="mt-4 text-sm text-gray-300">{activeReport?.verdict || report?.verdict}</p>

                <div className="mt-5 space-y-3">
                  {currentScore.parts?.map((p) => (
                    <div key={p.name}>
                      <div className="flex justify-between text-sm">
                        <span>{p.name}</span>
                        <span className="text-gray-400">+{p.points}</span>
                      </div>
                      <div className="h-1.5 rounded bg-gray-800">
                        <div className="h-1.5 rounded bg-red-500" style={{ width: `${Math.min(100, p.points * 5)}%` }} />
                      </div>
                      <p className="mt-1 text-xs text-gray-500">{p.why}</p>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {p.evidence.slice(0, 8).map((n) => (
                          <button
                            key={n}
                            onClick={() => jumpToStep(n)}
                            className="px-1.5 py-0.5 text-xs rounded bg-gray-800 hover:bg-gray-700 cursor-pointer"
                          >
                            step {n}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>

                {selectedPersona === 'pro_tester' && (
                  <div className="mt-4 pt-4 border-t border-gray-800/80 flex items-center justify-around text-xs">
                    <span className="text-gray-400">QA Bugs Found:</span>
                    <span className="font-bold text-gremlin-green text-sm">{activeReport?.bugs ?? report?.bugs ?? 0}</span>
                  </div>
                )}
              </>
            )}
          </div>

          {currentFindings.map((f) => (
            <div key={f.title} className="p-4 bg-black/40 border border-gray-800 rounded-lg">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-sm">{f.title}</h3>
                <div className="flex items-center gap-2">
                  {f.consistency && (
                    <span
                      className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded border ${
                        f.consistency === 'consistent'
                          ? 'bg-emerald-950/80 text-emerald-400 border-emerald-500/40'
                          : 'bg-gray-800/80 text-gray-400 border-gray-700'
                      }`}
                    >
                      {f.consistency}
                    </span>
                  )}
                  <span className="text-xs uppercase text-red-400">{f.severity}</span>
                </div>
              </div>
              <p className="mt-2 text-sm text-gray-300">{f.what_happened}</p>
              <p className="mt-1 text-xs text-gray-500">Impact: {f.impact}</p>

              {f.suggested_fix ? (
                <div className="mt-2.5 p-2.5 bg-black/70 border border-emerald-500/30 rounded font-mono text-[11px] text-gremlin-green whitespace-pre-wrap shadow-inner">
                  <div className="text-[9px] uppercase tracking-wider text-gray-400 font-sans font-bold mb-1 flex items-center justify-between">
                    <span>Suggested Fix</span>
                    {f.selector && <span className="text-gray-500 font-mono text-[9px] lowercase">{f.selector}</span>}
                  </div>
                  {f.suggested_fix}
                </div>
              ) : (
                <p className="mt-1 text-xs text-gremlin-green">Fix: {f.recommendation}</p>
              )}

              {f.screenshot && (
                <div className="mt-3 overflow-hidden rounded-lg border border-red-500/40 bg-black/80 shadow-md">
                  <div className="px-2.5 py-1 text-[10px] uppercase tracking-wider text-red-400 bg-red-950/40 border-b border-red-500/20 flex items-center justify-between font-semibold">
                    <span>Defect Highlight (Step {f.step_number || (f.evidence_steps && f.evidence_steps[0]) || 1})</span>
                    {f.bounding_box && (
                      <span className="text-gray-400 font-mono text-[9px]">
                        [{f.bounding_box.width}×{f.bounding_box.height}px]
                      </span>
                    )}
                  </div>
                  <div
                    className="cursor-pointer group relative overflow-hidden bg-gray-950/80 p-1 flex items-center justify-center"
                    onClick={() => {
                      const stepNum = f.step_number || (f.evidence_steps && f.evidence_steps[0]);
                      if (stepNum) jumpToStep(stepNum);
                    }}
                    title="Click to jump to step"
                  >
                    <img
                      src={`data:image/jpeg;base64,${f.screenshot}`}
                      alt={f.title}
                      className="max-h-48 w-full object-contain rounded transition group-hover:scale-[1.01]"
                    />
                  </div>
                </div>
              )}

              <div className="mt-2.5 flex flex-wrap gap-1">
                {f.evidence_steps.map((n) => (
                  <button
                    key={n}
                    onClick={() => jumpToStep(n)}
                    className="px-1.5 py-0.5 text-xs rounded bg-gray-800 hover:bg-gray-700"
                  >
                    step {n}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Right Side: Slideshow */}
        <div className="w-2/3 flex flex-col relative p-6 bg-black/20">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-gray-400 uppercase tracking-widest text-sm font-semibold">
              Step {totalSteps > 0 ? currentIndex + 1 : 0} of {totalSteps}
            </h2>
            <div className="flex gap-2">
              <button
                onClick={handlePrev}
                disabled={currentIndex === 0}
                className="p-2 rounded bg-gray-800 disabled:opacity-50 hover:bg-gray-700 transition"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              <button
                onClick={handleNext}
                disabled={currentIndex >= totalSteps - 1}
                className="p-2 rounded bg-gray-800 disabled:opacity-50 hover:bg-gray-700 transition"
              >
                <ChevronRight className="w-5 h-5" />
              </button>
            </div>
          </div>

          <div className="flex-1 flex flex-col min-h-0 bg-black border border-gray-800 rounded-lg overflow-hidden">
            {currentItem?.screenshot ? (
              <div className="flex-1 overflow-hidden p-2 flex items-center justify-center bg-gray-900/50">
                <img
                  src={`data:image/jpeg;base64,${currentItem.screenshot}`}
                  alt="Step screenshot"
                  className="max-h-full max-w-full object-contain"
                />
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center text-gray-600">
                No screenshot for this step
              </div>
            )}
            
            <div className="h-32 border-t border-gray-800 bg-bg-card p-4 overflow-y-auto">
              <div className="text-sm font-mono text-gray-300">
                <span className="text-gremlin-purple mr-2">&gt;</span>
                {currentItem?.thought || "No thought recorded."}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
