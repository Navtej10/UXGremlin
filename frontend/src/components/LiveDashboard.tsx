import { useEffect, useState, useRef } from 'react';
import { Terminal, Activity, MonitorPlay } from 'lucide-react';

import { type HistoryItem } from './Report';

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

export function LiveDashboard({ session, onComplete }: LiveDashboardProps) {
  const [thoughts, setThoughts] = useState<string[]>([]);
  const [currentScreenshot, setCurrentScreenshot] = useState<string | null>(null);
  const [isBaseline, setIsBaseline] = useState<boolean>(false);
  const thoughtsEndRef = useRef<HTMLDivElement>(null);

  // Ref to hold clean step history as fallback for Report
  const historyRef = useRef<HistoryItem[]>([]);
  const lastScreenshotRef = useRef<string | null>(null);

  useEffect(() => {
    const streamUrl = session.session_id
      ? `http://127.0.0.1:8000/api/stream?session_id=${encodeURIComponent(session.session_id)}`
      : 'http://127.0.0.1:8000/api/stream';
    const eventSource = new EventSource(streamUrl);

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.phase === 'baseline' || (typeof data.thought === 'string' && data.thought.includes('Running baseline'))) {
        setIsBaseline(true);
      } else if (data.step || (typeof data.thought === 'string' && (data.thought.includes('Starting persona') || data.thought.includes('Initializing agent')))) {
        setIsBaseline(false);
      }

      if (data.screenshot) {
        lastScreenshotRef.current = data.screenshot;
        setCurrentScreenshot(data.screenshot);
      }

      if (data.thought) {
        setThoughts((prev) => [...prev, data.thought]);
      }

      if (data.step) {
        historyRef.current = [
          ...historyRef.current,
          {
            step_number: data.step,
            action: data.action,
            thought: data.thought,
            screenshot: data.screenshot || lastScreenshotRef.current,
          }
        ];
      }

      if (data.done) {
        eventSource.close();
        onComplete(historyRef.current);
        return;
      }
    };

    return () => {
      eventSource.close();
    };
  }, [onComplete, session.session_id]);

  useEffect(() => {
    thoughtsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [thoughts]);

  return (
    <div className="h-screen w-screen flex flex-col bg-bg-dark overflow-hidden">
      {/* Top Bar */}
      <div className="h-14 border-b border-gray-800 flex items-center justify-between px-6 bg-bg-card shrink-0">
        <div className="flex items-center gap-4 text-sm">
          {isBaseline ? (
            <div className="flex items-center gap-2 text-amber-400">
              <Activity className="w-4 h-4 animate-spin" />
              <span className="font-bold">CALIBRATING BASELINE</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-gremlin-green">
              <Activity className="w-4 h-4 animate-pulse" />
              <span className="font-bold">ATTACK IN PROGRESS</span>
            </div>
          )}
          <div className="h-4 w-px bg-gray-700"></div>
          <div className="text-gray-400">Target: <span className="text-white">{session.url}</span></div>
          <div className="text-gray-400">Task: <span className="text-white">{session.task}</span></div>
          <div className="text-gray-400">Persona: <span className="text-gremlin-purple font-semibold">
            {session.persona === 'pro_tester' ? '🎯 Professional UX Tester' :
             session.persona === 'impatient' ? '😈 Impatient User' :
             session.persona === 'confused' ? '😵‍💫 Confused User' :
             session.persona === 'skeptic' ? '🧐 Skeptical User' :
             session.persona === 'mobile' ? '📱 Mobile User' : session.persona}
          </span></div>
          {session.runs && session.runs > 1 && (
            <>
              <div className="h-4 w-px bg-gray-700"></div>
              <div className="text-gray-400">Audit: <span className="text-gremlin-green font-mono font-semibold">{session.runs} Runs</span></div>
            </>
          )}
        </div>
        <button
          onClick={() => onComplete(historyRef.current)}
          className="px-3 py-1.5 bg-red-900/50 hover:bg-red-900/80 text-red-300 text-xs font-bold rounded uppercase tracking-wider transition-colors border border-red-800/50"
        >
          Abort Attack
        </button>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex min-h-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-gray-900 via-bg-dark to-black">
        {/* Left Pane - Browser View (65%) */}
        <div className="flex-[0.65] border-r border-gray-800 p-6 flex flex-col relative bg-black/40">
          <div className="flex items-center gap-2 mb-4 text-gremlin-green text-sm uppercase tracking-wider font-semibold drop-shadow-[0_0_8px_rgba(57,255,20,0.5)]">
            <MonitorPlay className="w-4 h-4" />
            Live Browser View
          </div>

          <div className="flex-1 border border-gray-700/50 rounded-lg bg-black flex items-center justify-center overflow-hidden shadow-2xl relative">
            {/* Subtle scanline effect */}
            <div className="absolute inset-0 bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.25)_50%),linear-gradient(90deg,rgba(255,0,0,0.06),rgba(0,255,0,0.02),rgba(0,0,255,0.06))] bg-[length:100%_4px,3px_100%] z-10 pointer-events-none opacity-20"></div>

            {currentScreenshot ? (
              <img src={`data:image/jpeg;base64,${currentScreenshot}`} alt="Live Browser View" className="w-full h-full object-contain relative z-0" />
            ) : (
              <div className="text-gray-500 animate-pulse text-sm font-mono flex flex-col items-center gap-3">
                <Activity className="w-6 h-6 text-gremlin-purple" />
                Establishing connection to target...
              </div>
            )}
          </div>
        </div>

        {/* Right Pane - Agent Brain (35%) */}
        <div className="flex-[0.35] p-4 flex flex-col bg-bg-card">
          <div className="flex items-center gap-2 mb-4 text-gremlin-purple text-sm uppercase tracking-wider font-semibold">
            <Terminal className="w-4 h-4" />
            Agent Brain Feed
          </div>

          <div className="flex-1 bg-black/40 border border-gremlin-purple/20 rounded-lg p-4 overflow-y-auto font-mono text-sm space-y-3 shadow-inner">
            {thoughts.length === 0 ? (
              <div className="text-gray-600 italic">Initializing agent logic...</div>
            ) : (
              thoughts.map((thought, index) => (
                <div key={index} className="flex gap-3 text-gray-300">
                  <span className="text-gremlin-purple opacity-70 shrink-0">[{new Date().toLocaleTimeString()}]</span>
                  <span className={thought.includes('Decided:') ? 'text-gremlin-green font-semibold' : ''}>
                    {thought}
                  </span>
                </div>
              ))
            )}
            <div ref={thoughtsEndRef} />
          </div>
        </div>
      </div>
    </div>
  );
}
