import { useEffect, useState, useRef } from 'react';
import { Terminal, Activity, MonitorPlay } from 'lucide-react';

interface LiveDashboardProps {
  session: {
    url: string;
    task: string;
    persona: string;
  };
}

export function LiveDashboard({ session }: LiveDashboardProps) {
  const [thoughts, setThoughts] = useState<string[]>([]);
  const thoughtsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const eventSource = new EventSource('http://127.0.0.1:8000/api/stream');
    
    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.thought) {
        setThoughts((prev) => [...prev, data.thought]);
      }
    };

    return () => {
      eventSource.close();
    };
  }, []);

  useEffect(() => {
    thoughtsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [thoughts]);

  return (
    <div className="h-screen w-screen flex flex-col bg-bg-dark overflow-hidden">
      {/* Top Bar */}
      <div className="h-14 border-b border-gray-800 flex items-center justify-between px-6 bg-bg-card shrink-0">
        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-2 text-gremlin-green">
            <Activity className="w-4 h-4 animate-pulse" />
            <span className="font-bold">ATTACK IN PROGRESS</span>
          </div>
          <div className="h-4 w-px bg-gray-700"></div>
          <div className="text-gray-400">Target: <span className="text-white">{session.url}</span></div>
          <div className="text-gray-400">Task: <span className="text-white">{session.task}</span></div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex min-h-0">
        {/* Left Pane - Browser View (65%) */}
        <div className="flex-[0.65] border-r border-gray-800 p-4 flex flex-col relative bg-black/20">
          <div className="flex items-center gap-2 mb-4 text-gray-400 text-sm uppercase tracking-wider font-semibold">
            <MonitorPlay className="w-4 h-4" />
            Live Browser View
          </div>
          
          <div className="flex-1 border border-gray-800 rounded-lg bg-black flex items-center justify-center overflow-hidden">
            <div className="text-gray-600 animate-pulse text-sm">
              Waiting for browser stream...
            </div>
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
                  <span className={thought.startsWith('Decided:') ? 'text-gremlin-green font-semibold' : ''}>
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
