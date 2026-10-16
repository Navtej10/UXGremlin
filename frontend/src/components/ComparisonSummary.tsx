import { ShieldAlert, CheckCircle2, XCircle, AlertTriangle, ArrowRight, BarChart3 } from 'lucide-react';

export interface ComparisonItem {
  persona: string;
  persona_label?: string;
  score: number;
  outcome: string;
  steps: number;
  top_finding: string;
}

interface ComparisonSummaryProps {
  comparison?: Record<string, ComparisonItem>;
  comparisonSummary?: ComparisonItem[];
  selectedPersona?: string;
  onSelectPersona?: (personaId: string) => void;
  onViewRun?: (personaId: string) => void;
  fallbackItem?: ComparisonItem;
}

const PERSONA_DETAILS: Record<string, { name: string; icon: string }> = {
  pro_tester: { name: 'Professional UX Tester', icon: '🎯' },
  impatient: { name: 'Impatient User', icon: '😈' },
  confused: { name: 'Confused User', icon: '😵‍💫' },
  skeptic: { name: 'Skeptical User', icon: '🧐' },
  mobile: { name: 'Mobile User', icon: '📱' },
};

const OUTCOME_STYLES: Record<string, { label: string; bg: string; text: string; border: string }> = {
  completed: {
    label: 'Completed',
    bg: 'bg-emerald-950/70',
    text: 'text-emerald-400',
    border: 'border-emerald-500/40',
  },
  abandoned: {
    label: 'Abandoned',
    bg: 'bg-amber-950/70',
    text: 'text-amber-400',
    border: 'border-amber-500/40',
  },
  gave_up: {
    label: 'Gave Up',
    bg: 'bg-rose-950/70',
    text: 'text-rose-400',
    border: 'border-rose-500/40',
  },
  max_steps_reached: {
    label: 'Max Steps',
    bg: 'bg-amber-950/70',
    text: 'text-amber-400',
    border: 'border-amber-500/40',
  },
  error: {
    label: 'Error',
    bg: 'bg-rose-950/70',
    text: 'text-rose-400',
    border: 'border-rose-500/40',
  },
  timeout: {
    label: 'Timeout',
    bg: 'bg-amber-950/70',
    text: 'text-amber-400',
    border: 'border-amber-500/40',
  },
  system_error: {
    label: 'Interrupted',
    bg: 'bg-amber-950/70',
    text: 'text-amber-400',
    border: 'border-amber-500/40',
  },
};

function getScoreColor(score: number): { text: string; bg: string; border: string } {
  if (score <= 20) return { text: 'text-gremlin-green', bg: 'bg-emerald-500', border: 'border-emerald-500/40' };
  if (score <= 45) return { text: 'text-amber-400', bg: 'bg-amber-400', border: 'border-amber-500/40' };
  if (score <= 70) return { text: 'text-orange-400', bg: 'bg-orange-500', border: 'border-orange-500/40' };
  return { text: 'text-rose-500', bg: 'bg-rose-500', border: 'border-rose-500/40' };
}

export function ComparisonSummary({
  comparison,
  comparisonSummary,
  selectedPersona,
  onSelectPersona,
  onViewRun,
  fallbackItem,
}: ComparisonSummaryProps) {
  // Normalize comparison items
  let items: ComparisonItem[] =
    comparisonSummary && comparisonSummary.length > 0
      ? comparisonSummary
      : comparison
      ? Object.values(comparison)
      : [];

  if (items.length === 0 && fallbackItem) {
    items = [fallbackItem];
  }

  if (items.length === 0) {
    return null;
  }

  // Calculate highest & lowest friction personas
  const sortedByScore = [...items].sort((a, b) => a.score - b.score);
  const lowestFriction = sortedByScore[0];
  const highestFriction = sortedByScore[sortedByScore.length - 1];
  const avgScore = Math.round(items.reduce((acc, curr) => acc + curr.score, 0) / items.length);

  return (
    <div className="w-full bg-bg-card/90 border border-gremlin-purple/30 rounded-2xl p-6 shadow-[0_0_30px_rgba(157,0,255,0.12)] mb-6 transition-all">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-gray-800">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gremlin-purple/20 border border-gremlin-purple/40 flex items-center justify-center text-gremlin-green">
            <BarChart3 className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-white tracking-tight flex items-center gap-2">
              Persona Usability Comparison
              <span className="text-xs font-mono font-normal px-2.5 py-0.5 rounded-full bg-gremlin-purple/20 border border-gremlin-purple/40 text-purple-300">
                {items.length} {items.length === 1 ? 'Persona' : 'Personas'} Tested
              </span>
            </h2>
            <p className="text-xs text-text-main/70 mt-0.5">
              Side-by-side friction scores, outcomes, and top vulnerabilities across tested archetypes. Click a persona to inspect details.
            </p>
          </div>
        </div>

        {/* Aggregate KPI chips */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="px-3 py-1.5 rounded-lg bg-black/40 border border-gray-800 text-right">
            <span className="text-[10px] uppercase font-bold text-gray-400 block">Avg Friction</span>
            <span className={`text-sm font-mono font-extrabold ${getScoreColor(avgScore).text}`}>
              {avgScore} <span className="text-[10px] text-gray-500 font-normal">/ 100</span>
            </span>
          </div>
          {lowestFriction && (
            <div className="px-3 py-1.5 rounded-lg bg-emerald-950/30 border border-emerald-500/30 text-right">
              <span className="text-[10px] uppercase font-bold text-emerald-400 block">Best UX</span>
              <span className="text-xs font-semibold text-white">
                {PERSONA_DETAILS[lowestFriction.persona]?.icon || '🎯'} {lowestFriction.score}
              </span>
            </div>
          )}
          {highestFriction && highestFriction.persona !== lowestFriction?.persona && (
            <div className="px-3 py-1.5 rounded-lg bg-rose-950/30 border border-rose-500/30 text-right">
              <span className="text-[10px] uppercase font-bold text-rose-400 block">Max Friction</span>
              <span className="text-xs font-semibold text-white">
                {PERSONA_DETAILS[highestFriction.persona]?.icon || '⚠️'} {highestFriction.score}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Persona Comparison Bars */}
      <div className="mt-5 space-y-3.5">
        {items.map((item) => {
          const isSelected = selectedPersona === item.persona;
          const scoreColors = getScoreColor(item.score);
          const outcomeStyle = OUTCOME_STYLES[item.outcome] || OUTCOME_STYLES.completed;
          const details = PERSONA_DETAILS[item.persona] || {
            name: item.persona_label || item.persona,
            icon: '👤',
          };

          const handleCardClick = () => {
            onSelectPersona?.(item.persona);
          };

          return (
            <div
              key={item.persona}
              onClick={handleCardClick}
              className={`p-4 rounded-xl border transition-all cursor-pointer group ${
                isSelected
                  ? 'bg-purple-950/30 border-gremlin-purple shadow-[0_0_20px_rgba(157,0,255,0.25)]'
                  : 'bg-black/40 border-gray-800 hover:border-gray-700 hover:bg-black/60'
              }`}
            >
              {/* Row 1: Persona Info & Metrics */}
              <div className="flex flex-wrap items-center justify-between gap-3 mb-2.5">
                <div className="flex items-center gap-2.5">
                  <span className="text-xl" role="img" aria-label={details.name}>
                    {details.icon}
                  </span>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-white text-sm group-hover:text-gremlin-green transition-colors">
                        {item.persona_label || details.name}
                      </span>
                      {isSelected && (
                        <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-gremlin-purple/30 text-purple-200 border border-gremlin-purple/50">
                          Active View
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-gray-500 font-mono">
                      {item.steps} {item.steps === 1 ? 'step' : 'steps'} taken
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  {/* Outcome Badge */}
                  <span
                    className={`text-xs uppercase font-bold px-2.5 py-1 rounded-md border flex items-center gap-1.5 ${outcomeStyle.bg} ${outcomeStyle.text} ${outcomeStyle.border}`}
                  >
                    {item.outcome === 'completed' ? (
                      <CheckCircle2 className="w-3.5 h-3.5" />
                    ) : item.outcome === 'error' ? (
                      <AlertTriangle className="w-3.5 h-3.5" />
                    ) : (
                      <XCircle className="w-3.5 h-3.5" />
                    )}
                    {outcomeStyle.label}
                  </span>

                  {/* Score Pill */}
                  <div className="text-right min-w-[70px]">
                    <span className={`text-lg font-black font-mono tracking-tight ${scoreColors.text}`}>
                      {item.score}
                    </span>
                    <span className="text-[11px] text-gray-500 font-normal"> / 100</span>
                  </div>
                </div>
              </div>

              {/* Row 2: Visual Score Bar */}
              <div className="w-full h-2.5 rounded-full bg-gray-900 border border-gray-800 overflow-hidden relative">
                <div
                  className={`h-full rounded-full transition-all duration-700 ${scoreColors.bg}`}
                  style={{ width: `${Math.max(4, Math.min(100, item.score))}%` }}
                />
              </div>

              {/* Row 3: Top Finding Highlight & Actions */}
              <div className="mt-3 pt-2.5 border-t border-gray-800/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                <div className="flex items-center gap-2 text-gray-300 min-w-0 flex-1">
                  <ShieldAlert className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                  <span className="text-gray-400 font-medium shrink-0">Top Finding:</span>
                  <span className="text-text-main truncate italic">{item.top_finding}</span>
                </div>

                {onViewRun && (
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectPersona?.(item.persona);
                        onViewRun(item.persona);
                      }}
                      className="px-3.5 py-1 rounded-lg bg-gremlin-purple/30 hover:bg-gremlin-purple/50 text-purple-200 hover:text-white font-bold text-[11px] border border-gremlin-purple/50 shadow-sm transition-all cursor-pointer flex items-center gap-1.5"
                      title="View step-by-step browser run"
                    >
                      <span>View Run</span>
                      <ArrowRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform text-gremlin-green" />
                    </button>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
