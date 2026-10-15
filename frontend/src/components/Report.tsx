import { useState } from 'react';
import { ChevronLeft, ChevronRight, RefreshCcw, ShieldAlert } from 'lucide-react';

export interface HistoryItem {
  thought: string;
  screenshot: string | null;
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

  const handlePrev = () => {
    setCurrentIndex((prev) => Math.max(0, prev - 1));
  };

  const handleNext = () => {
    setCurrentIndex((prev) => Math.min(history.length - 1, prev + 1));
  };

  // Precise outcome and friction score calculation
  const hasCompleted = history.some(item =>
    item.thought.toLowerCase().includes('completed successfully') ||
    item.thought.toLowerCase().includes('task completed')
  );
  const hasAborted = history.some(item =>
    item.thought.toLowerCase().includes('abort')
  );
  const hasError = history.some(item =>
    item.thought.toLowerCase().includes('error during') ||
    item.thought.toLowerCase().includes('fatal error') ||
    item.thought.toLowerCase().includes('action failed')
  );

  const frictionCount = history.filter(item =>
    item.thought.toLowerCase().includes('friction') ||
    item.thought.toLowerCase().includes('failed') ||
    item.thought.toLowerCase().includes('error') ||
    item.thought.toLowerCase().includes('bug')
  ).length;

  const bugsIdentified = history.filter(item =>
    item.thought.toLowerCase().includes('[ux bug]') ||
    item.thought.toLowerCase().includes('bug:') ||
    item.thought.toLowerCase().includes('bug found') ||
    item.thought.toLowerCase().includes('defect')
  ).length;

  let frictionScore: number;
  let statusText: string;
  let scoreColor: string;

  if (hasCompleted) {
    frictionScore = Math.min(65, Math.max(15, (history.length * 4) + (frictionCount * 12)));
    statusText = "Task completed successfully.";
    scoreColor = frictionScore > 50 ? "text-amber-400" : "text-gremlin-green";
  } else if (hasAborted) {
    frictionScore = 95;
    statusText = "Task aborted due to extreme friction.";
    scoreColor = "text-red-500";
  } else if (hasError) {
    frictionScore = 90;
    statusText = "Task failed due to UX blocking error.";
    scoreColor = "text-red-500";
  } else {
    frictionScore = 80;
    statusText = "Task incomplete: user hit step limit.";
    scoreColor = "text-amber-500";
  }

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
          
          <div className="mt-8 p-6 bg-black/40 border border-gray-800 rounded-lg text-center">
            <h2 className="text-gray-400 text-sm uppercase tracking-wider mb-4">Friction Score</h2>
            <div className={`text-6xl font-black ${scoreColor}`}>
              {frictionScore}
            </div>
            <p className={`text-sm mt-2 font-medium ${hasCompleted ? 'text-gray-400' : 'text-red-400'}`}>
              {statusText}
            </p>
            {session.persona === 'pro_tester' && (
              <div className="mt-4 pt-4 border-t border-gray-800/80 flex items-center justify-around text-xs">
                <span className="text-gray-400">QA Bugs Found:</span>
                <span className="font-bold text-gremlin-green text-sm">{bugsIdentified}</span>
              </div>
            )}
          </div>
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
