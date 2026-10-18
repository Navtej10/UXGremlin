import { useRef, useEffect, useState } from 'react';
import { ArrowDown, AlertTriangle, AlertCircle, RotateCcw, Brain, Terminal as TerminalIcon } from 'lucide-react';

export interface TerminalEntry {
  id?: string | number;
  text: string;
  step?: number;
  action?: string;
  friction_note?: string;
  phase?: 'Observe' | 'Understand' | 'Decide' | 'Act';
}

interface TerminalPanelProps {
  entries: (string | TerminalEntry)[];
  title?: string;
  className?: string;
  maxHeight?: string;
}

export function TerminalPanel({
  entries,
  title = 'Agent Brain Console',
  className = '',
}: TerminalPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);
  const [isAtBottom, setIsAtBottom] = useState(true);

  // Check scroll position to reveal "Jump to latest"
  const handleScroll = () => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const atBottom = scrollHeight - scrollTop - clientHeight < 40;
    setIsAtBottom(atBottom);
    setShowJumpToLatest(!atBottom && entries.length > 3);
  };

  const scrollToBottom = () => {
    if (containerRef.current) {
      containerRef.current.scrollTo({
        top: containerRef.current.scrollHeight,
        behavior: 'smooth',
      });
      setShowJumpToLatest(false);
      setIsAtBottom(true);
    }
  };

  // Auto-scroll when new entries arrive if user was already at bottom
  useEffect(() => {
    if (isAtBottom && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [entries, isAtBottom]);

  // Helper to categorize log row
  const renderRow = (item: string | TerminalEntry, index: number) => {
    const text = typeof item === 'string' ? item : item.text;
    const frictionNote = typeof item === 'object' ? item.friction_note : undefined;
    const action = typeof item === 'object' ? item.action : undefined;

    // Detect loop phase
    let phase: 'Observe' | 'Understand' | 'Decide' | 'Act' | null = null;
    let cleanText = text;

    if (text.startsWith('[Observe]') || text.includes('Observing') || text.includes('captured state')) {
      phase = 'Observe';
      cleanText = text.replace(/^\[Observe\]\s*/, '');
    } else if (text.startsWith('[Understand]') || text.includes('Analyzing') || text.includes('assessing')) {
      phase = 'Understand';
      cleanText = text.replace(/^\[Understand\]\s*/, '');
    } else if (text.startsWith('[Decide]') || text.includes('Decided') || text.includes('Planning')) {
      phase = 'Decide';
      cleanText = text.replace(/^\[Decide\]\s*/, '');
    } else if (text.startsWith('[Act]') || text.includes('Executing') || text.includes('Clicking') || text.includes('Typing')) {
      phase = 'Act';
      cleanText = text.replace(/^\[Act\]\s*/, '');
    }

    // Detect callout types
    const isRageClick = text.toLowerCase().includes('rage-click') || text.toLowerCase().includes('rage click');
    const isBacktrack = text.toLowerCase().includes('backtrack') || text.toLowerCase().includes('returned to previous');
    const isFriction = frictionNote || isRageClick || isBacktrack || text.toLowerCase().includes('confusion') || text.toLowerCase().includes('friction:');
    const isAiReasoning = text.toLowerCase().includes('inner monologue') || text.toLowerCase().includes('reasoning:') || text.toLowerCase().includes('thought:');

    return (
      <div key={index} className="flex flex-col gap-1 text-xs font-mono leading-relaxed group">
        {/* Main Log Line */}
        <div className="flex items-start gap-2 py-0.5">
          {phase && (
            <span
              className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded shrink-0 select-none ${
                phase === 'Observe'
                  ? 'bg-stone/50 text-ink'
                  : phase === 'Understand'
                  ? 'bg-lilac text-lilac-text'
                  : phase === 'Decide'
                  ? 'bg-gremlin/30 text-ink'
                  : 'bg-gremlin text-ink font-extrabold'
              }`}
            >
              {phase}
            </span>
          )}

          <div className="flex-1 break-words text-ink">
            {isAiReasoning ? (
              <div className="p-2.5 rounded-xl bg-lilac/70 border border-lilac-text/20 text-lilac-text flex items-start gap-2 my-1">
                <Brain className="w-3.5 h-3.5 shrink-0 mt-0.5 text-lilac-text" />
                <span className="flex-1">{cleanText}</span>
              </div>
            ) : (
              <span>{cleanText}</span>
            )}
          </div>
        </div>

        {/* Action Chip if present */}
        {action && (
          <div className="pl-6 flex items-center gap-1.5 text-[11px] text-muted">
            <span className="font-bold text-gremlin-dark">&gt;</span>
            <span className="bg-canvas border border-stone px-2 py-0.5 rounded text-ink font-semibold">
              {action}
            </span>
          </div>
        )}

        {/* Friction / Rage Click / Backtrack Callout */}
        {isFriction && (
          <div
            className={`ml-4 mr-1 p-2 rounded-xl text-xs flex items-start gap-2 my-1 border shadow-subtle ${
              isRageClick
                ? 'bg-severity-critical-bg text-severity-critical-fg border-severity-critical-fg/30'
                : isBacktrack
                ? 'bg-severity-medium-bg text-severity-medium-fg border-severity-medium-fg/30'
                : 'bg-severity-medium-bg text-severity-medium-fg border-severity-medium-fg/30'
            }`}
          >
            {isRageClick ? (
              <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
            ) : isBacktrack ? (
              <RotateCcw className="w-3.5 h-3.5 shrink-0 mt-0.5" />
            ) : (
              <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
            )}
            <div className="flex-1">
              <span className="font-bold uppercase tracking-wider text-[10px] block mb-0.5">
                {isRageClick ? 'Rage Click Detected' : isBacktrack ? 'Navigation Backtrack' : 'Friction Event'}
              </span>
              <span>{frictionNote || cleanText}</span>
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div
      className={`relative flex flex-col bg-surface border border-stone rounded-2xl shadow-card overflow-hidden ${className}`}
    >
      {/* Terminal Top Bar */}
      <div className="h-10 px-4 border-b border-stone bg-canvas/40 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <TerminalIcon className="w-4 h-4 text-muted" />
          <span className="text-xs font-semibold text-ink">{title}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-stone" />
          <span className="w-2.5 h-2.5 rounded-full bg-stone" />
          <span className="w-2.5 h-2.5 rounded-full bg-stone" />
        </div>
      </div>

      {/* Terminal Content Area */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        role="log"
        aria-live="polite"
        className="flex-1 p-4 overflow-y-auto space-y-2 select-text"
      >
        {entries.length === 0 ? (
          <div className="text-muted text-xs font-mono py-8 text-center italic">
            Waiting for agent telemetry stream…
          </div>
        ) : (
          entries.map((entry, idx) => renderRow(entry, idx))
        )}
      </div>

      {/* Jump to Latest Pill */}
      {showJumpToLatest && (
        <button
          type="button"
          onClick={scrollToBottom}
          className="absolute bottom-3 left-1/2 -translate-x-1/2 flex items-center gap-1.5 px-3 py-1 bg-surface border border-gremlin-dark text-ink font-mono text-xs font-bold rounded-full shadow-popover hover:bg-gremlin/20 transition cursor-pointer z-10"
        >
          <ArrowDown className="w-3 h-3 text-gremlin-dark" />
          <span>Jump to latest</span>
        </button>
      )}
    </div>
  );
}
