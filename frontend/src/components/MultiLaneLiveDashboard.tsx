import { useEffect, useState, useRef } from 'react';
import { Terminal, Activity, MonitorPlay, Maximize2, X, ShieldAlert, CheckCircle2 } from 'lucide-react';
import { type HistoryItem } from './Report';

interface MultiLaneLiveDashboardProps {
  session: {
    session_id?: string;
    url: string;
    task: string;
    persona: string;
    personas?: string[];
    runs?: number;
  };
  onComplete: (history: HistoryItem[], comparison?: any) => void;
}

interface PersonaLaneState {
  personaId: string;
  thoughts: string[];
  currentScreenshot: string | null;
  status: 'pending' | 'running' | 'completed' | 'abandoned' | 'gave_up' | 'error' | 'timeout' | 'system_error';
  currentStep: number;
  latestAction: string;
  history: HistoryItem[];
}

const PERSONA_LABELS: Record<string, { label: string; icon: string }> = {
  pro_tester: { label: 'Professional UX Tester', icon: '🎯' },
  impatient: { label: 'Impatient User', icon: '😈' },
  confused: { label: 'Confused User', icon: '😵‍💫' },
  skeptic: { label: 'Skeptical User', icon: '🧐' },
  mobile: { label: 'Mobile User', icon: '📱' },
};

export function MultiLaneLiveDashboard({ session, onComplete }: MultiLaneLiveDashboardProps) {
  const personas = session.personas && session.personas.length > 0 ? session.personas : [session.persona];

  // Initialize per-persona lane state
  const [lanes, setLanes] = useState<Record<string, PersonaLaneState>>(() => {
    const initial: Record<string, PersonaLaneState> = {};
    personas.forEach((p) => {
      initial[p] = {
        personaId: p,
        thoughts: [],
        currentScreenshot: null,
        status: 'running',
        currentStep: 0,
        latestAction: 'Initializing...',
        history: [],
      };
    });
    return initial;
  });

  const [isBaseline, setIsBaseline] = useState<boolean>(false);
  const [baselineThought, setBaselineThought] = useState<string>('');
  const [expandedScreenshot, setExpandedScreenshot] = useState<{ src: string; persona: string } | null>(null);

  // Auto-scroll refs per persona
  const feedRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const allHistoryRef = useRef<HistoryItem[]>([]);
  const latestComparisonRef = useRef<any>(null);

  useEffect(() => {
    const streamUrl = session.session_id
      ? `http://127.0.0.1:8000/api/stream?session_id=${encodeURIComponent(session.session_id)}`
      : 'http://127.0.0.1:8000/api/stream';

    const eventSource = new EventSource(streamUrl);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Track baseline status
        if (data.phase === 'baseline' || (typeof data.thought === 'string' && data.thought.includes('Baseline'))) {
          setIsBaseline(true);
          if (data.thought) setBaselineThought(data.thought);
        } else if (data.step || (typeof data.thought === 'string' && (data.thought.includes('Starting persona') || data.thought.includes('Initializing agent')))) {
          setIsBaseline(false);
        }

        // Save comparison object if present
        if (data.comparison) {
          latestComparisonRef.current = data.comparison;
        }

        // Tagged persona events
        const pId = data.persona_id || data.persona;

        if (pId) {
          setLanes((prev) => {
            const lane = prev[pId] || {
              personaId: pId,
              thoughts: [],
              currentScreenshot: null,
              status: 'running',
              currentStep: 0,
              latestAction: '',
              history: [],
            };

            const updatedThoughts = data.thought ? [...lane.thoughts, data.thought] : lane.thoughts;
            const updatedScreenshot = data.screenshot || lane.currentScreenshot;
            const updatedStep = data.step ? data.step : lane.currentStep;
            const updatedAction = data.action ? `${data.action} ${data.target || ''}`.trim() : lane.latestAction;

            let updatedStatus = lane.status;
            if (data.persona_done || data.outcome === 'completed') {
              updatedStatus = 'completed';
            } else if (data.outcome && ['abandoned', 'gave_up', 'error', 'timeout', 'system_error'].includes(data.outcome)) {
              updatedStatus = data.outcome;
            }

            let updatedHistory = lane.history;
            if (data.step) {
              const histItem: HistoryItem = {
                step_number: data.step,
                action: data.action,
                thought: data.thought || '',
                screenshot: data.screenshot || lane.currentScreenshot,
              };
              updatedHistory = [...lane.history, histItem];
              allHistoryRef.current.push(histItem);
            }

            return {
              ...prev,
              [pId]: {
                ...lane,
                thoughts: updatedThoughts,
                currentScreenshot: updatedScreenshot,
                currentStep: updatedStep,
                latestAction: updatedAction,
                status: updatedStatus,
                history: updatedHistory,
              },
            };
          });
        } else if (data.thought && !pId) {
          // Broadcast general thought to all running lanes
          setLanes((prev) => {
            const next = { ...prev };
            Object.keys(next).forEach((key) => {
              next[key] = {
                ...next[key],
                thoughts: [...next[key].thoughts, data.thought],
              };
            });
            return next;
          });
        }

        // Global session completion
        if (data.done) {
          eventSource.close();
          onComplete(allHistoryRef.current, data.comparison || latestComparisonRef.current);
        }
      } catch (err) {
        console.error('Error parsing SSE event:', err);
      }
    };

    eventSource.onerror = (err) => {
      console.warn('EventSource warning:', err);
    };

    return () => {
      eventSource.close();
    };
  }, [session.session_id, onComplete]);

  // Scroll individual lane feeds to bottom
  useEffect(() => {
    Object.keys(lanes).forEach((pId) => {
      const el = feedRefs.current[pId];
      if (el) {
        el.scrollTop = el.scrollHeight;
      }
    });
  }, [lanes]);

  // Determine grid column layout based on persona count
  const gridColsClass =
    personas.length === 1
      ? 'grid-cols-1 max-w-4xl mx-auto'
      : personas.length === 2
      ? 'grid-cols-1 md:grid-cols-2'
      : personas.length === 3
      ? 'grid-cols-1 md:grid-cols-3'
      : 'grid-cols-1 md:grid-cols-2 xl:grid-cols-4';

  return (
    <div className="h-screen w-screen flex flex-col bg-bg-dark overflow-hidden text-white">
      {/* Top Header Bar */}
      <header className="h-14 border-b border-gray-800 flex items-center justify-between px-6 bg-bg-card shrink-0 shadow-md">
        <div className="flex items-center gap-4 text-sm overflow-x-auto py-1">
          {isBaseline ? (
            <div className="flex items-center gap-2 text-amber-400 shrink-0">
              <Activity className="w-4 h-4 animate-spin" />
              <span className="font-bold tracking-wide">CALIBRATING BASELINE</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-gremlin-green shrink-0">
              <Activity className="w-4 h-4 animate-pulse" />
              <span className="font-bold tracking-wide">COMPARE MODE ATTACK</span>
            </div>
          )}

          <div className="h-4 w-px bg-gray-700 shrink-0" />
          <div className="text-gray-400 text-xs shrink-0">
            Target: <span className="text-white font-mono font-medium">{session.url}</span>
          </div>

          <div className="h-4 w-px bg-gray-700 shrink-0" />
          <div className="text-gray-400 text-xs truncate max-w-xs shrink-0">
            Task: <span className="text-white font-medium">{session.task}</span>
          </div>

          <div className="h-4 w-px bg-gray-700 shrink-0" />
          <div className="flex items-center gap-1.5 shrink-0">
            <span className="text-xs text-gray-400">Lanes ({personas.length}):</span>
            {personas.map((p) => {
              const lane = lanes[p];
              const isDone = lane?.status === 'completed';
              return (
                <span
                  key={p}
                  className={`text-[11px] font-mono font-bold px-2 py-0.5 rounded border flex items-center gap-1 ${
                    isDone
                      ? 'bg-emerald-950/60 border-emerald-500/40 text-emerald-400'
                      : 'bg-gremlin-purple/20 border-gremlin-purple/40 text-purple-200'
                  }`}
                >
                  <span>{PERSONA_LABELS[p]?.icon || '👤'}</span>
                  <span className="hidden sm:inline">{PERSONA_LABELS[p]?.label?.split(' ')[0] || p}</span>
                  {lane?.currentStep > 0 && <span className="text-gray-400 font-normal">#{lane.currentStep}</span>}
                </span>
              );
            })}
          </div>
        </div>

        <button
          onClick={() => onComplete(allHistoryRef.current, latestComparisonRef.current)}
          className="px-3.5 py-1.5 bg-red-950/60 hover:bg-red-900 text-red-300 text-xs font-bold rounded-lg uppercase tracking-wider transition-all border border-red-800/60 shrink-0 ml-4 hover:shadow-[0_0_15px_rgba(239,68,68,0.3)]"
        >
          Abort All
        </button>
      </header>

      {/* Baseline status banner if calibrating */}
      {isBaseline && (
        <div className="bg-amber-950/40 border-b border-amber-500/30 px-6 py-2 flex items-center gap-2 text-xs text-amber-300">
          <ShieldAlert className="w-4 h-4 animate-pulse shrink-0" />
          <span className="font-semibold uppercase tracking-wider">Baseline Calibration:</span>
          <span className="text-amber-200/90 truncate">{baselineThought || 'Calibrating optimal path...'}</span>
        </div>
      )}

      {/* Main Multi-lane Live View Area */}
      <main className="flex-1 p-4 overflow-y-auto bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-gray-900 via-bg-dark to-black">
        <div className={`grid ${gridColsClass} gap-4 h-full min-h-[500px]`}>
          {personas.map((pId) => {
            const lane = lanes[pId] || {
              personaId: pId,
              thoughts: [],
              currentScreenshot: null,
              status: 'running',
              currentStep: 0,
              latestAction: '',
              history: [],
            };
            const meta = PERSONA_LABELS[pId] || { label: pId, icon: '👤' };

            return (
              <div
                key={pId}
                className="flex flex-col bg-bg-card/80 border border-gray-800 hover:border-gremlin-purple/40 rounded-xl overflow-hidden shadow-xl transition-all duration-300"
              >
                {/* Lane Header */}
                <div className="h-12 border-b border-gray-800/80 px-4 flex items-center justify-between bg-black/40">
                  <div className="flex items-center gap-2 truncate">
                    <span className="text-lg">{meta.icon}</span>
                    <span className="font-bold text-sm text-white truncate">{meta.label}</span>
                  </div>

                  <div className="flex items-center gap-2">
                    {lane.status === 'completed' ? (
                      <span className="text-[10px] uppercase font-bold font-mono px-2 py-0.5 rounded bg-emerald-950 border border-emerald-500/50 text-emerald-400 flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3" /> Done
                      </span>
                    ) : lane.status === 'abandoned' || lane.status === 'gave_up' ? (
                      <span className="text-[10px] uppercase font-bold font-mono px-2 py-0.5 rounded bg-rose-950 border border-rose-500/50 text-rose-400">
                        {lane.status}
                      </span>
                    ) : lane.status === 'timeout' || lane.status === 'system_error' ? (
                      <span className="text-[10px] uppercase font-bold font-mono px-2 py-0.5 rounded bg-amber-950 border border-amber-500/50 text-amber-400">
                        {lane.status === 'timeout' ? 'timeout' : 'interrupted'}
                      </span>
                    ) : lane.status === 'error' ? (
                      <span className="text-[10px] uppercase font-bold font-mono px-2 py-0.5 rounded bg-rose-950 border border-rose-500/50 text-rose-400">
                        error
                      </span>
                    ) : (
                      <span className="text-[10px] uppercase font-bold font-mono px-2 py-0.5 rounded bg-gremlin-purple/20 border border-gremlin-purple/40 text-gremlin-green flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-gremlin-green animate-ping" />
                        Running
                      </span>
                    )}

                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-gray-900 border border-gray-700 text-gray-300">
                      Step {lane.currentStep}
                    </span>
                  </div>
                </div>

                {/* Compact Live Browser View (Top Half of Lane) */}
                <div className="relative aspect-video bg-black flex items-center justify-center overflow-hidden border-b border-gray-800 group">
                  {/* CRT scanline effect */}
                  <div className="absolute inset-0 bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.25)_50%),linear-gradient(90deg,rgba(255,0,0,0.06),rgba(0,255,0,0.02),rgba(0,0,255,0.06))] bg-[length:100%_4px,3px_100%] z-10 pointer-events-none opacity-25" />

                  {lane.currentScreenshot ? (
                    <>
                      <img
                        src={`data:image/jpeg;base64,${lane.currentScreenshot}`}
                        alt={`${meta.label} live view`}
                        className="w-full h-full object-contain relative z-0 transition-transform duration-300 group-hover:scale-[1.02]"
                      />
                      <button
                        onClick={() =>
                          setExpandedScreenshot({
                            src: `data:image/jpeg;base64,${lane.currentScreenshot}`,
                            persona: meta.label,
                          })
                        }
                        className="absolute bottom-2 right-2 p-1.5 rounded-lg bg-black/70 hover:bg-black text-gray-300 hover:text-white border border-gray-700 opacity-0 group-hover:opacity-100 transition-opacity z-20"
                        title="Expand View"
                      >
                        <Maximize2 className="w-3.5 h-3.5" />
                      </button>
                    </>
                  ) : (
                    <div className="text-gray-500 text-xs font-mono flex flex-col items-center gap-2 p-4 text-center">
                      <MonitorPlay className="w-6 h-6 text-gremlin-purple animate-pulse" />
                      <span>Initializing browser context...</span>
                    </div>
                  )}
                </div>

                {/* Agent Brain Feed (Bottom Half of Lane) */}
                <div className="flex-1 flex flex-col min-h-[170px] max-h-[220px] bg-black/60 p-3">
                  <div className="flex items-center gap-1.5 mb-2 text-[11px] uppercase tracking-wider text-gremlin-purple font-semibold">
                    <Terminal className="w-3.5 h-3.5" />
                    <span>Agent Brain Feed</span>
                  </div>

                  <div
                    ref={(el) => {
                      feedRefs.current[pId] = el;
                    }}
                    className="flex-1 overflow-y-auto space-y-2 pr-1 font-mono text-[11px] text-gray-300 leading-tight scrollbar-thin scrollbar-thumb-gray-800"
                  >
                    {lane.thoughts.length === 0 ? (
                      <div className="text-gray-600 italic">Waiting for persona decisions...</div>
                    ) : (
                      lane.thoughts.map((th, idx) => {
                        const isDecided = th.includes('Decided:');
                        const isFriction = th.includes('Friction') || th.includes('RAGE') || th.includes('Warning');

                        return (
                          <div
                            key={idx}
                            className={`p-1 rounded ${
                              isFriction
                                ? 'bg-amber-950/40 text-amber-300 border border-amber-500/20'
                                : isDecided
                                ? 'text-gremlin-green font-medium'
                                : 'text-gray-300'
                            }`}
                          >
                            {th}
                          </div>
                        );
                      })
                    )}
                  </div>

                  {/* Lane Footer */}
                  {lane.latestAction && (
                    <div className="mt-2 pt-2 border-t border-gray-800 flex items-center justify-between text-[10px] text-gray-400">
                      <span className="truncate">Action: {lane.latestAction}</span>
                      <span className="font-mono text-gremlin-purple shrink-0">#{lane.currentStep}</span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </main>

      {/* Expanded Screenshot Modal */}
      {expandedScreenshot && (
        <div
          className="fixed inset-0 z-50 bg-black/90 flex flex-col items-center justify-center p-6 backdrop-blur-sm"
          onClick={() => setExpandedScreenshot(null)}
        >
          <div
            className="relative max-w-5xl max-h-[90vh] bg-bg-card border border-gremlin-purple/50 rounded-2xl overflow-hidden shadow-2xl flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="h-12 border-b border-gray-800 px-4 flex items-center justify-between bg-black/60">
              <span className="font-bold text-sm text-white">{expandedScreenshot.persona} - Live Screenshot</span>
              <button
                onClick={() => setExpandedScreenshot(null)}
                className="p-1 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-2 overflow-auto max-h-[calc(90vh-3rem)]">
              <img src={expandedScreenshot.src} alt="Expanded Screenshot" className="w-full h-auto object-contain rounded-lg" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
