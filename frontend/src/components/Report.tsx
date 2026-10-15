import { useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight, RefreshCcw, ShieldAlert } from 'lucide-react';

export interface HistoryItem {
  thought: string;
  screenshot: string | null;
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
}

interface SabotageReport {
  score: { total: number; label: string; parts: ScorePart[]; steps_taken: number; ideal_steps: number };
  verdict: string;
  findings: Finding[];
  bugs?: number;
}

interface ReportProps {
  session: {
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
};

export function Report({ session, history, onRestart }: ReportProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [report, setReport] = useState<SabotageReport | null>(null);

  useEffect(() => {
    let cancelled = false;
    let tries = 0;
    const load = async () => {
      try {
        const res = await fetch('http://127.0.0.1:8000/api/report');
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
  }, []);

  const jumpToStep = (n: number) => {
    const prefix = `Step ${n} · `;
    const exec = history.findIndex((h) => h.thought.startsWith(`${prefix}Executing`));
    const any = history.findIndex((h) => h.thought.startsWith(prefix));
    const i = exec >= 0 ? exec : any;
    if (i >= 0) setCurrentIndex(i);
  };

  const total = report?.score.total ?? 0;
  const scoreColor = total < 25 ? 'text-gremlin-green' : total < 50 ? 'text-amber-400' : 'text-red-500';

  const handlePrev = () => {
    setCurrentIndex((prev) => Math.max(0, prev - 1));
  };

  const handleNext = () => {
    setCurrentIndex((prev) => Math.min(history.length - 1, prev + 1));
  };

  const currentItem = history[currentIndex];

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
          <div>
            <h2 className="text-gray-400 text-sm uppercase tracking-wider mb-2">Target</h2>
            <p className="font-mono text-lg">{session.url}</p>
          </div>
          <div>
            <h2 className="text-gray-400 text-sm uppercase tracking-wider mb-2">Task</h2>
            <p className="text-lg">{session.task}</p>
          </div>
          <div>
            <h2 className="text-gray-400 text-sm uppercase tracking-wider mb-2">Persona</h2>
            <p className="text-lg text-gremlin-purple font-semibold">
              {PERSONA_NAMES[session.persona] || session.persona}
            </p>
          </div>
          
          <div className="mt-8 p-6 bg-black/40 border border-gray-800 rounded-lg">
            <h2 className="text-gray-400 text-sm uppercase tracking-wider mb-4 text-center">Friction Score</h2>
            {!report ? (
              <p className="text-center text-gray-500 text-sm">Generating report…</p>
            ) : (
              <>
                <div className={`text-6xl font-black text-center ${scoreColor}`}>{report.score.total}</div>
                <p className="text-center text-sm mt-1 text-gray-400">
                  {report.score.label} friction · {report.score.steps_taken} steps taken, about {report.score.ideal_steps} expected
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
                <span className="text-xs uppercase text-red-400">{f.severity}</span>
              </div>
              <p className="mt-2 text-sm text-gray-300">{f.what_happened}</p>
              <p className="mt-1 text-xs text-gray-500">Impact: {f.impact}</p>
              <p className="mt-1 text-xs text-gremlin-green">Fix: {f.recommendation}</p>
              <div className="mt-2 flex flex-wrap gap-1">
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
              Step {currentIndex + 1} of {history.length}
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
                disabled={currentIndex === history.length - 1}
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
