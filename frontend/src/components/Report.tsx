import { useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight, RefreshCcw, ShieldAlert } from 'lucide-react';

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

interface Finding {
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
}

interface SabotageReport {
  session_id?: string;
  url?: string;
  task?: string;
  persona?: string;
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

interface ReportProps {
  session: {
    session_id?: string;
    url: string;
    task: string;
    persona: string;
  };
  history: HistoryItem[];
  onRestart: () => void;
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

export function Report({ session, history, onRestart }: ReportProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [report, setReport] = useState<SabotageReport | null>(null);

  useEffect(() => {
    let cancelled = false;
    let tries = 0;
    const reportUrl = session.session_id
      ? `http://127.0.0.1:8000/api/report?session_id=${encodeURIComponent(session.session_id)}`
      : 'http://127.0.0.1:8000/api/report';

    const load = async () => {
      try {
        const res = await fetch(reportUrl);
        const data = await res.json();
        if (data?.score) {
          if (!cancelled) setReport(data as SabotageReport);
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
  }, [session.session_id]);

  // ONE source of truth: the backend's saved action list
  const slideshowItems: (ActionItem | HistoryItem)[] =
    report?.actions && report.actions.length > 0 ? report.actions : history;
  const totalSteps = slideshowItems.length;

  const jumpToStep = (n: number) => {
    if (report?.actions && report.actions.length > 0) {
      const idx = report.actions.findIndex((a) => a.step_number === n);
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

  const total = report?.score.total ?? 0;
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

  return (
    <div className="h-screen w-screen flex flex-col bg-bg-dark text-white">
      {/* Header */}
      <div className="h-16 border-b border-gray-800 flex items-center justify-between px-6 bg-bg-card">
        <div className="flex items-center gap-3">
          <ShieldAlert className="text-gremlin-purple w-6 h-6" />
          <h1 className="text-xl font-bold uppercase tracking-widest text-transparent bg-clip-text bg-gradient-to-r from-gremlin-purple to-gremlin-green">
            Sabotage Report
          </h1>
        </div>
        <button
          onClick={onRestart}
          className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 text-sm font-semibold rounded transition-colors"
        >
          <RefreshCcw className="w-4 h-4" />
          New Attack
        </button>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* Left Side: Summary */}
        <div className="w-1/3 border-r border-gray-800 p-8 flex flex-col gap-6 overflow-y-auto">
          {report?.outcome && (
            <div
              className={`p-4 rounded-xl border ${
                OUTCOME_CONFIG[report.outcome]?.bg ?? 'bg-gray-800/60'
              } ${
                OUTCOME_CONFIG[report.outcome]?.border ?? 'border-gray-700'
              } shadow-lg flex flex-col gap-2.5`}
            >
              <div className="flex items-center justify-between">
                <span className="text-[11px] uppercase tracking-wider text-gray-400 font-bold">
                  Task Outcome
                </span>
                {report.claimed_outcome &&
                  report.verified_outcome &&
                  report.claimed_outcome !== report.verified_outcome && (
                    <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-black/60 text-amber-300 border border-amber-500/30">
                      Claimed: {report.claimed_outcome} · Verified: {report.verified_outcome}
                    </span>
                  )}
              </div>
              <div className="flex items-center gap-2.5">
                <span
                  className={`w-3 h-3 rounded-full ${
                    OUTCOME_CONFIG[report.outcome]?.dot ?? 'bg-gray-400'
                  } animate-pulse`}
                />
                <span
                  className={`text-lg font-extrabold tracking-wide uppercase ${
                    OUTCOME_CONFIG[report.outcome]?.text ?? 'text-white'
                  }`}
                >
                  {OUTCOME_CONFIG[report.outcome]?.label ?? report.outcome}
                </span>
              </div>
              {report.outcome_reason && (
                <p className="text-xs text-gray-300 leading-relaxed pl-3 border-l-2 border-white/20 mt-0.5">
                  {report.outcome_reason}
                </p>
              )}
            </div>
          )}

          {report?.baseline_failed && (
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
            <p className="font-mono text-lg">{report?.url || session.url}</p>
          </div>
          <div>
            <h2 className="text-gray-400 text-sm uppercase tracking-wider mb-2">Task</h2>
            <p className="text-lg">{report?.task || session.task}</p>
          </div>
          <div>
            <h2 className="text-gray-400 text-sm uppercase tracking-wider mb-2">Persona</h2>
            <p className="text-lg text-gremlin-purple font-semibold">
              {PERSONA_NAMES[report?.persona || session.persona] || report?.persona || session.persona}
            </p>
          </div>
          
          <div className="mt-8 p-6 bg-black/40 border border-gray-800 rounded-lg">
            <h2 className="text-gray-400 text-sm uppercase tracking-wider mb-4 text-center">Friction Score</h2>
            {!report ? (
              <p className="text-center text-gray-500 text-sm">Generating report…</p>
            ) : (
              <>
                <div className="flex items-center justify-center gap-4">
                  <div className={`text-6xl font-black ${scoreColor}`}>{report.score.total}</div>
                  {((report.runs && report.runs > 1) || (report.score.runs && report.score.runs > 1)) && (
                    <div className="text-left bg-gray-900/90 border border-gray-700/70 rounded-lg px-3 py-1.5 shadow-sm">
                      <div className="text-sm font-extrabold text-white tracking-wide">
                        {report.score_min ?? report.score.score_min}–{report.score_max ?? report.score.score_max}
                      </div>
                      <div className="text-[11px] text-gremlin-green font-medium">
                        consistent across {report.runs ?? report.score.runs} runs
                      </div>
                    </div>
                  )}
                </div>
                <p className="text-center text-sm mt-1 text-gray-400">
                  {report.score.label} friction · {report.score.steps_taken} steps taken, about {report.score.ideal_steps} expected
                  {report.baseline_failed ? ' (heuristic fallback)' : ''}
                </p>
                <p className="mt-4 text-sm text-gray-300">{report.verdict}</p>

                <div className="mt-5 space-y-3">
                  {report.score.parts.map((p) => (
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
                            className="px-1.5 py-0.5 text-xs rounded bg-gray-800 hover:bg-gray-700"
                          >
                            step {n}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>

                {session.persona === 'pro_tester' && (
                  <div className="mt-4 pt-4 border-t border-gray-800/80 flex items-center justify-around text-xs">
                    <span className="text-gray-400">QA Bugs Found:</span>
                    <span className="font-bold text-gremlin-green text-sm">{report.bugs ?? 0}</span>
                  </div>
                )}
              </>
            )}
          </div>

          {report?.findings.map((f) => (
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
