import { useEffect, useState, useRef } from 'react';
import { StopCircle, Maximize2, X, ShieldAlert, Monitor } from 'lucide-react';
import { type HistoryItem } from './Report';
import { Gremlin, GremlinSpeech } from './mascot/Gremlin';
import { Badge, Button } from './ui';

interface MultiLaneLiveDashboardProps {
  session: {
    session_id?: string;
    url: string;
    task: string;
    persona: string;
    personas?: string[];
    runs?: number;
  };
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
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
  pro_tester: { label: 'Pro Tester', icon: '🎯' },
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
        latestAction: 'Initializing…',
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
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
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
        } else if (
          data.step ||
          (typeof data.thought === 'string' &&
            (data.thought.includes('Starting persona') || data.thought.includes('Initializing agent')))
        ) {
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
            } else if (
              data.outcome &&
              ['abandoned', 'gave_up', 'error', 'timeout', 'system_error'].includes(data.outcome)
            ) {
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
    <div className="h-screen w-screen flex flex-col bg-canvas text-ink overflow-hidden antialiased">
      {/* Universal Top Header Bar (Only ONE mascot on the screen) */}
      <header className="h-16 border-b border-stone bg-surface px-6 flex items-center justify-between shrink-0 shadow-subtle gap-4 z-20">
        <div className="flex items-center gap-3 min-w-0">
          <Badge variant={isBaseline ? 'medium' : 'running'}>
            {isBaseline ? 'Baseline Calibration' : `Compare Mode (${personas.length} Lanes)`}
          </Badge>

          <div className="h-4 w-px bg-stone hidden sm:block" />

          <div className="text-xs text-muted truncate max-w-xs md:max-w-md hidden sm:block">
            Target: <span className="font-mono text-ink font-semibold">{session.url}</span>
          </div>

          <div className="h-4 w-px bg-stone hidden lg:block" />

          <div className="hidden lg:flex items-center gap-1.5 shrink-0">
            {personas.map((p) => {
              const lane = lanes[p];
              const isDone = lane?.status === 'completed';
              return (
                <span
                  key={p}
                  className={`text-[11px] font-mono font-semibold px-2 py-0.5 rounded-lg border flex items-center gap-1 ${
                    isDone
                      ? 'bg-severity-low-bg border-severity-low-fg/30 text-severity-low-fg'
                      : 'bg-gremlin/20 border-gremlin/40 text-ink'
                  }`}
                >
                  <span>{PERSONA_LABELS[p]?.icon || '👤'}</span>
                  <span className="hidden xl:inline">{PERSONA_LABELS[p]?.label}</span>
                  {lane?.currentStep > 0 && <span className="text-muted">#{lane.currentStep}</span>}
                </span>
              );
            })}
          </div>
        </div>

        {/* Center: ONE mascot for multi-lane */}
        <div className="hidden md:flex items-center gap-2">
          <Gremlin pose="investigating" size="sm" animate={true} />
          <GremlinSpeech position="right" className="text-xs py-1 px-3">
            <span className="font-mono text-[11px] text-muted">
              Monitoring {personas.length} parallel browsers
            </span>
          </GremlinSpeech>
        </div>

        {/* Right: Abort Button */}
        <Button
          variant="destructive"
          size="sm"
          onClick={() => onComplete(allHistoryRef.current, latestComparisonRef.current)}
          leftIcon={<StopCircle className="w-4 h-4" />}
        >
          Abort All
        </Button>
      </header>

      {/* Baseline status banner if calibrating */}
      {isBaseline && (
        <div className="bg-severity-medium-bg border-b border-severity-medium-fg/20 px-6 py-2 flex items-center gap-2 text-xs text-severity-medium-fg">
          <ShieldAlert className="w-4 h-4 animate-pulse shrink-0" />
          <span className="font-semibold uppercase tracking-wider">Baseline Calibration:</span>
          <span className="truncate">{baselineThought || 'Calibrating optimal path…'}</span>
        </div>
      )}

      {/* Main Multi-lane Live View Area */}
      <main className="flex-1 p-4 md:p-6 overflow-y-auto bg-canvas">
        <div className={`grid ${gridColsClass} gap-6 h-full min-h-[520px]`}>
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

            const isDone = lane.status === 'completed';
            const isAbandoned = lane.status === 'abandoned' || lane.status === 'gave_up';
            const isError = lane.status === 'error';
            const isTimeout = lane.status === 'timeout' || lane.status === 'system_error';

            return (
              <div
                key={pId}
                className="flex flex-col bg-surface border border-stone rounded-2xl shadow-card overflow-hidden hover:border-gremlin/50 transition-all duration-200"
              >
                {/* Lane Header */}
                <div className="h-12 border-b border-stone px-4 flex items-center justify-between bg-canvas/40 shrink-0">
                  <div className="flex items-center gap-2 truncate">
                    <span className="text-base shrink-0">{meta.icon}</span>
                    <span className="font-bold text-xs text-ink truncate">{meta.label}</span>
                  </div>

                  <div className="flex items-center gap-2">
                    {isDone ? (
                      <Badge variant="completed">Done</Badge>
                    ) : isAbandoned ? (
                      <Badge variant="abandoned">{lane.status}</Badge>
                    ) : isTimeout ? (
                      <Badge variant="medium">{lane.status}</Badge>
                    ) : isError ? (
                      <Badge variant="critical">Error</Badge>
                    ) : (
                      <Badge variant="running">Running</Badge>
                    )}

                    <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-surface border border-stone text-muted">
                      Step {lane.currentStep}
                    </span>
                  </div>
                </div>

                {/* Compact Live Browser View (Top Half of Lane) */}
                <div className="relative aspect-video bg-canvas/40 flex items-center justify-center overflow-hidden border-b border-stone group">
                  {lane.currentScreenshot ? (
                    <>
                      <img
                        src={`data:image/jpeg;base64,${lane.currentScreenshot}`}
                        alt={`${meta.label} live view`}
                        className="w-full h-full object-contain relative z-0 transition-transform duration-200 group-hover:scale-[1.01]"
                      />
                      <button
                        type="button"
                        onClick={() =>
                          setExpandedScreenshot({
                            src: `data:image/jpeg;base64,${lane.currentScreenshot}`,
                            persona: meta.label,
                          })
                        }
                        className="absolute bottom-2 right-2 p-1.5 rounded-lg bg-surface/90 hover:bg-surface text-ink border border-stone opacity-0 group-hover:opacity-100 transition-opacity shadow-subtle cursor-pointer z-20"
                        title="Expand Viewport"
                      >
                        <Maximize2 className="w-3.5 h-3.5 text-ink" />
                      </button>
                    </>
                  ) : (
                    <div className="text-muted text-xs font-mono flex flex-col items-center gap-2 p-4 text-center">
                      <Monitor className="w-6 h-6 text-gremlin-dark animate-pulse" />
                      <span>Initializing browser context…</span>
                    </div>
                  )}
                </div>

                {/* Agent Brain Feed (Bottom Half of Lane) */}
                <div className="flex-1 flex flex-col min-h-[160px] max-h-[220px] bg-surface p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[11px] font-semibold text-muted uppercase tracking-wider">
                      Brain Stream
                    </span>
                    {lane.latestAction && (
                      <span className="text-[10px] font-mono text-muted truncate max-w-[180px]">
                        {lane.latestAction}
                      </span>
                    )}
                  </div>

                  <div
                    ref={(el) => {
                      feedRefs.current[pId] = el;
                    }}
                    className="flex-1 overflow-y-auto space-y-1.5 pr-1 font-mono text-[11px] text-ink leading-relaxed"
                  >
                    {lane.thoughts.length === 0 ? (
                      <div className="text-muted italic text-[11px]">
                        Waiting for persona decisions…
                      </div>
                    ) : (
                      lane.thoughts.map((th, idx) => {
                        const isDecided = th.includes('Decided:');
                        const isFriction =
                          th.toLowerCase().includes('friction') ||
                          th.toLowerCase().includes('rage') ||
                          th.toLowerCase().includes('warning');

                        return (
                          <div
                            key={idx}
                            className={`p-1.5 rounded-lg text-[11px] ${
                              isFriction
                                ? 'bg-severity-medium-bg text-severity-medium-fg border border-severity-medium-fg/20'
                                : isDecided
                                ? 'bg-gremlin/15 text-ink font-semibold'
                                : 'text-muted'
                            }`}
                          >
                            {th}
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </main>

      {/* Expanded Screenshot Modal */}
      {expandedScreenshot && (
        <div
          className="fixed inset-0 z-50 bg-ink/60 flex flex-col items-center justify-center p-6 backdrop-blur-sm"
          onClick={() => setExpandedScreenshot(null)}
        >
          <div
            className="relative max-w-5xl max-h-[90vh] bg-surface border border-stone rounded-2xl overflow-hidden shadow-popover flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="h-12 border-b border-stone px-4 flex items-center justify-between bg-canvas/40">
              <span className="font-bold text-xs text-ink">
                {expandedScreenshot.persona} — Viewport Capture
              </span>
              <button
                type="button"
                onClick={() => setExpandedScreenshot(null)}
                className="p-1 rounded-lg hover:bg-stone/30 text-muted hover:text-ink transition cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-3 overflow-auto max-h-[calc(90vh-3rem)] bg-canvas/30">
              <img
                src={expandedScreenshot.src}
                alt="Expanded Screenshot"
                className="w-full h-auto object-contain rounded-xl border border-stone shadow-card"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
