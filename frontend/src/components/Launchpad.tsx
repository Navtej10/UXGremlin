import { useState } from 'react';
import { Skull, Zap } from 'lucide-react';

interface LaunchpadProps {
  onLaunch: (data: {
    session_id?: string;
    url: string;
    task: string;
    persona: string;
    personas?: string[];
    baseline?: boolean;
    runs?: number;
  }) => void;
}

const AVAILABLE_PERSONAS = [
  {
    id: 'pro_tester',
    name: 'Professional UX Tester',
    icon: '🎯',
    desc: 'Systematically audits buttons, layout integrity, form fields & finds bugs',
  },
  {
    id: 'impatient',
    name: 'Impatient User',
    icon: '😈',
    desc: 'Rushes through pages, rage-clicks unresponsive elements, abandons on delays',
  },
  {
    id: 'confused',
    name: 'Confused User',
    icon: '😵‍💫',
    desc: 'Hesitates on icons, interprets copy literally, prefers large obvious buttons',
  },
  {
    id: 'skeptic',
    name: 'Skeptical User',
    icon: '🧐',
    desc: 'Refuses real personal data, injects synthetic info, looks for trust signals',
  },
  {
    id: 'mobile',
    name: 'Mobile User',
    icon: '📱',
    desc: 'Emulates 390x844 mobile viewport with touch gestures, auditing 44px tap targets',
  },
];

export function Launchpad({ onLaunch }: LaunchpadProps) {
  const [url, setUrl] = useState('');
  const [task, setTask] = useState('');
  const [selectedPersonas, setSelectedPersonas] = useState<string[]>(['pro_tester']);
  const [baseline, setBaseline] = useState(true);
  const [runs, setRuns] = useState(1);

  const togglePersona = (id: string) => {
    setSelectedPersonas((prev) => {
      if (prev.includes(id)) {
        if (prev.length === 1) return prev; // Keep at least one persona
        return prev.filter((p) => p !== id);
      } else {
        return [...prev, id];
      }
    });
  };

  const handleSelectAll = () => {
    setSelectedPersonas(AVAILABLE_PERSONAS.map((p) => p.id));
  };

  const handleSelectTop3 = () => {
    setSelectedPersonas(['pro_tester', 'impatient', 'mobile']);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    console.log('Launch attack:', { url, task, personas: selectedPersonas, baseline, runs });
    try {
      const response = await fetch('http://127.0.0.1:8000/api/start-session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url,
          task,
          persona: selectedPersonas[0],
          personas: selectedPersonas,
          baseline,
          runs,
        }),
      });
      if (response.ok) {
        const data = await response.json();
        console.log('Attack launched successfully!', data);
        onLaunch({
          session_id: data.session_id,
          url,
          task,
          persona: selectedPersonas[0],
          personas: selectedPersonas,
          baseline,
          runs,
        });
      } else {
        console.error('Failed to launch attack.');
      }
    } catch (err) {
      console.error('Error launching attack:', err);
    }
  };

  const isCompareMode = selectedPersonas.length > 1;

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-xl bg-bg-card border border-gremlin-purple/30 rounded-2xl shadow-[0_0_40px_rgba(157,0,255,0.15)] overflow-hidden">
        <div className="p-8">
          <div className="flex items-center gap-3 mb-8">
            <div className="w-12 h-12 rounded-xl bg-gremlin-purple/20 flex items-center justify-center border border-gremlin-purple/50">
              <Skull className="w-7 h-7 text-gremlin-green" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-white tracking-tight">UXGremlin</h1>
              <p className="text-text-main/80 text-sm">Automated UX Sabotage Engine</p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label htmlFor="url" className="block text-sm font-medium text-text-main mb-2">Target Website URL</label>
              <input
                id="url"
                type="url"
                required
                placeholder="https://example.com"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                className="w-full px-4 py-3 bg-bg-dark border border-gray-700 rounded-lg focus:outline-none focus:border-gremlin-purple focus:ring-1 focus:ring-gremlin-purple text-white placeholder-gray-500 transition-colors"
              />
            </div>

            <div>
              <label htmlFor="task" className="block text-sm font-medium text-text-main mb-2">Target Task</label>
              <textarea
                id="task"
                required
                placeholder="e.g., Sign up for the cheapest pricing plan"
                value={task}
                onChange={(e) => setTask(e.target.value)}
                rows={3}
                className="w-full px-4 py-3 bg-bg-dark border border-gray-700 rounded-lg focus:outline-none focus:border-gremlin-purple focus:ring-1 focus:ring-gremlin-purple text-white placeholder-gray-500 transition-colors resize-none"
              />
            </div>

            {/* Persona Multi-Select */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-medium text-text-main">
                  Saboteur Personas (Multi-Select)
                </label>
                <div className="flex items-center gap-2 text-xs">
                  <button
                    type="button"
                    onClick={handleSelectTop3}
                    className="text-gremlin-purple hover:text-purple-300 transition-colors underline"
                  >
                    Top 3
                  </button>
                  <span className="text-gray-600">·</span>
                  <button
                    type="button"
                    onClick={handleSelectAll}
                    className="text-gremlin-purple hover:text-purple-300 transition-colors underline"
                  >
                    All 5
                  </button>
                </div>
              </div>

              {/* Persona Cards Grid */}
              <div className="grid grid-cols-1 gap-2">
                {AVAILABLE_PERSONAS.map((p) => {
                  const isChecked = selectedPersonas.includes(p.id);
                  return (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => togglePersona(p.id)}
                      className={`p-3 rounded-lg border text-left transition-all flex items-start justify-between gap-3 ${
                        isChecked
                          ? 'bg-purple-950/40 border-gremlin-purple text-white shadow-[0_0_15px_rgba(157,0,255,0.2)]'
                          : 'bg-bg-dark border-gray-800 text-gray-400 hover:border-gray-700 hover:text-gray-300'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <span className="text-xl shrink-0 mt-0.5">{p.icon}</span>
                        <div>
                          <div className="text-sm font-semibold text-white flex items-center gap-2">
                            {p.name}
                            {p.id === 'pro_tester' && (
                              <span className="text-[10px] px-1.5 py-0.2 rounded bg-gremlin-purple/30 text-purple-200 border border-gremlin-purple/40">
                                QA Rigor
                              </span>
                            )}
                            {p.id === 'mobile' && (
                              <span className="text-[10px] px-1.5 py-0.2 rounded bg-gremlin-green/20 text-gremlin-green border border-gremlin-green/40">
                                Touch 44px
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-gray-400 mt-0.5 leading-tight">{p.desc}</p>
                        </div>
                      </div>

                      <div
                        className={`w-5 h-5 rounded flex items-center justify-center shrink-0 mt-0.5 border transition-colors ${
                          isChecked
                            ? 'bg-gremlin-purple border-gremlin-purple text-white'
                            : 'border-gray-700 bg-bg-dark'
                        }`}
                      >
                        {isChecked && (
                          <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
                            <path
                              fillRule="evenodd"
                              d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                              clipRule="evenodd"
                            />
                          </svg>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* Compare Mode Callout */}
              {isCompareMode ? (
                <div className="mt-3 p-2.5 rounded-lg bg-purple-950/50 border border-gremlin-purple/40 flex items-center justify-between text-xs text-purple-200">
                  <span className="flex items-center gap-1.5 font-semibold text-gremlin-green">
                    <span className="w-2 h-2 rounded-full bg-gremlin-green animate-pulse" />
                    ⚡ Compare Mode Active ({selectedPersonas.length} Personas)
                  </span>
                  <span className="text-gray-400 text-[11px]">Concurrent browser contexts (cap: 3)</span>
                </div>
              ) : (
                <p className="text-xs text-gray-400 mt-2">
                  Select 2 or more personas to enable side-by-side concurrent comparison.
                </p>
              )}
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-medium text-text-main">
                  Number of Runs (Consistency Audit)
                </label>
                <span className="text-xs text-gremlin-green font-mono font-bold">
                  {runs} {runs === 1 ? 'Run (Standard)' : 'Runs (Multi-run)'}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {[1, 2, 3].map((num) => (
                  <button
                    key={num}
                    type="button"
                    onClick={() => setRuns(num)}
                    className={`py-2 px-3 rounded-lg border text-sm font-semibold transition-all flex flex-col items-center justify-center ${
                      runs === num
                        ? 'bg-gremlin-purple/20 border-gremlin-purple text-white shadow-[0_0_15px_rgba(157,0,255,0.3)]'
                        : 'bg-bg-dark border-gray-700 text-gray-400 hover:border-gray-600 hover:text-gray-200'
                    }`}
                  >
                    <span>{num} {num === 1 ? 'Run' : 'Runs'}</span>
                    <span className="text-[10px] text-gray-400 font-normal">
                      {num === 1 ? 'Single test' : num === 2 ? '2x consistency' : '3x full audit'}
                    </span>
                  </button>
                ))}
              </div>
              <p className="text-xs text-gray-400 mt-2">
                <span className="text-amber-400 font-medium">Time cost:</span>{' '}
                {runs === 1
                  ? 'Standard test duration (~1-2 min).'
                  : `${runs} sequential runs will take ~${runs}x longer to aggregate consistency.`}
              </p>
            </div>

            <div className="p-4 bg-bg-dark border border-gray-700/80 rounded-lg flex items-center justify-between">
              <div>
                <label htmlFor="baseline" className="text-sm font-semibold text-white block cursor-pointer">
                  Run Baseline Calibration
                </label>
                <p className="text-xs text-gray-400 mt-0.5">
                  Runs direct baseline agent first to calibrate expected steps (cached per task).
                </p>
              </div>
              <input
                id="baseline"
                type="checkbox"
                checked={baseline}
                onChange={(e) => setBaseline(e.target.checked)}
                className="w-5 h-5 accent-gremlin-purple rounded border-gray-700 bg-bg-dark cursor-pointer"
              />
            </div>

            <button
              type="submit"
              className="w-full py-4 mt-4 bg-gremlin-purple hover:bg-gremlin-purple/90 text-white font-bold rounded-lg shadow-[0_0_20px_rgba(157,0,255,0.4)] hover:shadow-[0_0_30px_rgba(57,255,20,0.4)] hover:text-gremlin-green transition-all flex items-center justify-center gap-2 group cursor-pointer"
            >
              <Zap className="w-5 h-5 group-hover:animate-pulse" />
              {isCompareMode ? `COMPARE ${selectedPersonas.length} PERSONAS` : 'SABOTAGE WEBSITE'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
