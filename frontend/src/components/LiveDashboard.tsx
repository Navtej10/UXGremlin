import { useEffect, useState, useRef } from 'react';
import { StopCircle, Globe, Monitor, RefreshCw } from 'lucide-react';
import { type HistoryItem } from './Report';
import { Gremlin, GremlinSpeech, type GremlinPose } from './mascot/Gremlin';
import { Badge, Button, Skeleton, TerminalPanel } from './ui';

interface LiveDashboardProps {
  session: {
    session_id?: string;
    url: string;
    task: string;
    persona: string;
    runs?: number;
  };
  onComplete: (history: HistoryItem[]) => void;
}

const PERSONA_NAMES: Record<string, string> = {
  pro_tester: '🎯 Professional UX Tester',
  impatient: '😈 Impatient User',
  confused: '😵‍💫 Confused User',
  skeptic: '🧐 Skeptical User',
  mobile: '📱 Mobile User',
};

export function LiveDashboard({ session, onComplete }: LiveDashboardProps) {
  const [thoughts, setThoughts] = useState<string[]>([]);
  const [currentScreenshot, setCurrentScreenshot] = useState<string | null>(null);
  const [isBaseline, setIsBaseline] = useState<boolean>(false);
  const [currentUrl, setCurrentUrl] = useState<string>(session.url);
  const [currentStep, setCurrentStep] = useState<number>(0);
  const [latestAction, setLatestAction] = useState<string>('Initializing browser session…');
  const [targetCoords, setTargetCoords] = useState<{ x: number; y: number; label?: string } | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);
  const [mascotPose, setMascotPose] = useState<GremlinPose>('investigating');
  const [isStreamError, setIsStreamError] = useState<boolean>(false);
  const [isStepStarting, setIsStepStarting] = useState<boolean>(false);

  // Ref to hold clean step history as fallback for Report
  const historyRef = useRef<HistoryItem[]>([]);
  const lastScreenshotRef = useRef<string | null>(null);
  const discoveryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Timer for elapsed time
  useEffect(() => {
    const timer = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const formatElapsed = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  useEffect(() => {
    const streamUrl = session.session_id
      ? `http://127.0.0.1:8000/api/stream?session_id=${encodeURIComponent(session.session_id)}`
      : 'http://127.0.0.1:8000/api/stream';
    const eventSource = new EventSource(streamUrl);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setIsStreamError(false);

        if (
          data.phase === 'baseline' ||
          (typeof data.thought === 'string' && data.thought.includes('Running baseline'))
        ) {
          setIsBaseline(true);
        } else if (
          data.step ||
          (typeof data.thought === 'string' &&
            (data.thought.includes('Starting persona') || data.thought.includes('Initializing agent')))
        ) {
          setIsBaseline(false);
        }

        if (data.url) {
          setCurrentUrl(data.url);
        }

        if (data.step) {
          setCurrentStep(data.step);
          setIsStepStarting(false);
        }

        if (data.action) {
          setLatestAction(data.action);
        }

        // Coordinates highlight if available
        if (typeof data.x === 'number' && typeof data.y === 'number') {
          setTargetCoords({ x: data.x, y: data.y, label: data.action });
        } else {
          setTargetCoords(null);
        }

        if (data.screenshot) {
          lastScreenshotRef.current = data.screenshot;
          setCurrentScreenshot(data.screenshot);
          setIsStepStarting(false);
        }

        if (data.thought) {
          setThoughts((prev) => [...prev, data.thought]);

          // Check if thought or event indicates a friction discovery
          const isFriction =
            data.friction_note ||
            data.thought.toLowerCase().includes('friction') ||
            data.thought.toLowerCase().includes('rage-click') ||
            data.thought.toLowerCase().includes('confusion') ||
            data.thought.toLowerCase().includes('backtrack');

          if (isFriction) {
            setMascotPose('discovery');
            if (discoveryTimerRef.current) clearTimeout(discoveryTimerRef.current);
            discoveryTimerRef.current = setTimeout(() => {
              setMascotPose('investigating');
            }, 2000);
          }
        }

        if (data.step) {
          historyRef.current = [
            ...historyRef.current,
            {
              step_number: data.step,
              action: data.action,
              thought: data.thought,
              screenshot: data.screenshot || lastScreenshotRef.current,
            },
          ];
        }

        if (data.done) {
          eventSource.close();
          onComplete(historyRef.current);
          return;
        }
      } catch (err) {
        console.error('Error parsing SSE event:', err);
      }
    };

    eventSource.onerror = () => {
      setIsStreamError(true);
      setMascotPose('confused');
    };

    return () => {
      eventSource.close();
      if (discoveryTimerRef.current) clearTimeout(discoveryTimerRef.current);
    };
  }, [onComplete, session.session_id]);

  return (
    <div className="h-screen w-screen flex flex-col bg-canvas text-ink overflow-hidden antialiased">
      {/* Universal Top Header Strip */}
      <header className="h-16 border-b border-stone bg-surface px-6 flex items-center justify-between shrink-0 z-20 gap-4">
        {/* Left Status & Session Context */}
        <div className="flex items-center gap-3 min-w-0">
          <Badge variant={isBaseline ? 'medium' : 'running'}>
            {isBaseline ? 'Baseline Calibration' : 'Attack in Progress'}
          </Badge>

          <div className="h-4 w-px bg-stone hidden sm:block" />

          <div className="flex items-center gap-2 min-w-0 text-xs">
            <span className="font-semibold text-ink shrink-0">
              {PERSONA_NAMES[session.persona] || session.persona}
            </span>
            <span className="text-muted font-mono text-[11px] hidden md:inline shrink-0">
              · Step {currentStep} · {formatElapsed(elapsedSeconds)}
            </span>
          </div>

          {session.runs && session.runs > 1 && (
            <span className="hidden lg:inline-block px-2 py-0.5 rounded bg-gremlin/20 text-ink text-[11px] font-mono font-semibold">
              {session.runs} Runs Consistency
            </span>
          )}
        </div>

        {/* Center Mascot & Speech Bubble */}
        <div className="hidden md:flex items-center gap-2 max-w-md min-w-0">
          <Gremlin pose={mascotPose} size="sm" animate={true} />
          <GremlinSpeech position="right" className="truncate text-xs py-1 px-3">
            <span className="truncate block font-mono text-[11px]">
              {latestAction}
            </span>
          </GremlinSpeech>
        </div>

        {/* Right Actions: Reconnect or Abort */}
        <div className="flex items-center gap-3 shrink-0">
          {isStreamError && (
            <div className="flex items-center gap-1.5 text-xs text-severity-critical-fg font-semibold animate-pulse">
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              <span>Reconnecting telemetry…</span>
            </div>
          )}

          <Button
            variant="destructive"
            size="sm"
            onClick={() => onComplete(historyRef.current)}
            leftIcon={<StopCircle className="w-4 h-4" />}
          >
            Abort Attack
          </Button>
        </div>
      </header>

      {/* Main Full-Width Split Pane Layout */}
      <div className="flex-1 flex flex-col lg:flex-row min-h-0 bg-canvas p-4 md:p-6 gap-6 overflow-hidden">
        {/* Left Pane (~60%): Live Browser View in Browser Frame */}
        <div className="flex-1 lg:flex-[0.62] flex flex-col min-h-0 bg-surface border border-stone rounded-2xl shadow-card overflow-hidden">
          {/* Browser Window Chrome / Header */}
          <div className="h-11 px-4 border-b border-stone bg-canvas/40 flex items-center justify-between shrink-0 gap-3">
            <div className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded-full bg-stone" />
              <span className="w-3 h-3 rounded-full bg-stone" />
              <span className="w-3 h-3 rounded-full bg-stone" />
            </div>

            {/* Current URL Mono Pill */}
            <div className="flex-1 max-w-lg mx-2 flex items-center gap-2 px-3 py-1 bg-surface border border-stone rounded-lg font-mono text-xs text-ink truncate shadow-subtle">
              <Globe className="w-3.5 h-3.5 text-muted shrink-0" />
              <span className="truncate select-all">{currentUrl}</span>
            </div>

            <div className="flex items-center gap-1 text-[11px] font-mono text-muted">
              <Monitor className="w-3.5 h-3.5" />
              <span>1440×900</span>
            </div>
          </div>

          {/* Viewport Canvas */}
          <div className="flex-1 min-h-0 bg-canvas/30 p-3 md:p-4 flex items-center justify-center relative overflow-hidden">
            {currentScreenshot ? (
              <div className="relative max-h-full max-w-full flex items-center justify-center">
                <img
                  src={`data:image/jpeg;base64,${currentScreenshot}`}
                  alt="Live Browser Viewport"
                  className="max-h-full max-w-full object-contain rounded-xl border border-stone shadow-subtle bg-surface"
                />

                {/* Target Coordinate Ring Indicator */}
                {targetCoords && (
                  <div
                    style={{
                      left: `${targetCoords.x}px`,
                      top: `${targetCoords.y}px`,
                    }}
                    className="absolute -translate-x-1/2 -translate-y-1/2 pointer-events-none z-10 flex flex-col items-center"
                  >
                    <span className="w-7 h-7 rounded-full border-2 border-gremlin-dark bg-gremlin/30 animate-ping" />
                    {targetCoords.label && (
                      <span className="mt-1 px-2 py-0.5 rounded bg-ink text-surface text-[10px] font-mono font-bold shadow-popover whitespace-nowrap">
                        {targetCoords.label}
                      </span>
                    )}
                  </div>
                )}
              </div>
            ) : isStepStarting ? (
              <div className="w-full h-full flex flex-col items-center justify-center gap-3 p-8">
                <Skeleton className="w-full h-4/5 rounded-2xl" />
                <span className="text-xs text-muted font-mono animate-pulse">
                  Step {currentStep} started · capturing viewport…
                </span>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center gap-3 text-muted p-8 text-center">
                <div className="w-12 h-12 rounded-2xl bg-surface border border-stone flex items-center justify-center text-muted shadow-subtle">
                  <RefreshCw className="w-6 h-6 animate-spin text-gremlin-dark" />
                </div>
                <h3 className="text-sm font-semibold text-ink">
                  Launching sandboxed Chromium browser…
                </h3>
                <p className="text-xs text-muted max-w-xs font-mono">
                  Navigating to {session.url} and establishing live viewport stream.
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Right Pane (~38%): Agent Brain Console */}
        <div className="flex-1 lg:flex-[0.38] flex flex-col min-h-0">
          <TerminalPanel
            entries={thoughts}
            title="Agent Brain Console"
            className="flex-1 min-h-0"
          />
        </div>
      </div>

      {/* Footer Strip */}
      <footer className="h-9 px-6 border-t border-stone bg-surface flex items-center justify-between text-[11px] text-muted shrink-0">
        <span>Bounded exploration: one task, one persona. Not an exhaustive test.</span>
        <span className="font-mono">Task: "{session.task}"</span>
      </footer>
    </div>
  );
}
