import { ShieldAlert, ArrowRight, BarChart3 } from 'lucide-react';
import { Badge, Button, Card } from './ui';

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
  pro_tester: { name: 'Pro Tester', icon: '🎯' },
  impatient: { name: 'Impatient User', icon: '😈' },
  confused: { name: 'Confused User', icon: '😵‍💫' },
  skeptic: { name: 'Skeptical User', icon: '🧐' },
  mobile: { name: 'Mobile User', icon: '📱' },
};

function getScoreTextColor(score: number): string {
  if (score <= 20) return 'text-severity-low-fg';
  if (score <= 45) return 'text-severity-medium-fg';
  if (score <= 70) return 'text-severity-critical-fg';
  return 'text-severity-critical-fg';
}

function getScoreBarBg(score: number): string {
  if (score <= 20) return 'bg-severity-low-fg';
  if (score <= 45) return 'bg-severity-medium-fg';
  return 'bg-severity-critical-fg';
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
    <Card className="p-6 mb-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-stone">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gremlin/20 border border-gremlin/50 flex items-center justify-center text-ink">
            <BarChart3 className="w-5 h-5 text-gremlin-dark" />
          </div>
          <div>
            <h2 className="text-base font-bold text-ink tracking-tight flex items-center gap-2">
              <span>Persona Usability Comparison</span>
              <span className="text-xs font-mono font-normal px-2.5 py-0.5 rounded-full bg-gremlin/20 border border-gremlin/40 text-ink">
                {items.length} {items.length === 1 ? 'Persona' : 'Personas'} Tested
              </span>
            </h2>
            <p className="text-xs text-muted mt-0.5">
              Side-by-side friction scores, outcomes, and top vulnerabilities across tested archetypes.
            </p>
          </div>
        </div>

        {/* Aggregate KPI chips */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="px-3 py-1.5 rounded-xl bg-canvas border border-stone text-right">
            <span className="text-[10px] uppercase font-bold text-muted block">Avg Friction</span>
            <span className={`text-sm font-mono font-extrabold ${getScoreTextColor(avgScore)}`}>
              {avgScore} <span className="text-[10px] text-muted font-normal">/ 100</span>
            </span>
          </div>
          {lowestFriction && (
            <div className="px-3 py-1.5 rounded-xl bg-severity-low-bg border border-severity-low-fg/30 text-right">
              <span className="text-[10px] uppercase font-bold text-severity-low-fg block">Best UX</span>
              <span className="text-xs font-semibold text-ink">
                {PERSONA_DETAILS[lowestFriction.persona]?.icon || '🎯'} {lowestFriction.score}
              </span>
            </div>
          )}
          {highestFriction && highestFriction.persona !== lowestFriction?.persona && (
            <div className="px-3 py-1.5 rounded-xl bg-severity-critical-bg border border-severity-critical-fg/30 text-right">
              <span className="text-[10px] uppercase font-bold text-severity-critical-fg block">Max Friction</span>
              <span className="text-xs font-semibold text-ink">
                {PERSONA_DETAILS[highestFriction.persona]?.icon || '⚠️'} {highestFriction.score}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Persona Comparison Cards Grid */}
      <div className="mt-5 grid grid-cols-1 gap-3.5">
        {items.map((item) => {
          const isSelected = selectedPersona === item.persona;
          const scoreTextColor = getScoreTextColor(item.score);
          const scoreBarBg = getScoreBarBg(item.score);
          const details = PERSONA_DETAILS[item.persona] || {
            name: item.persona_label || item.persona,
            icon: '👤',
          };

          const handleCardClick = () => {
            onSelectPersona?.(item.persona);
          };

          const outcomeVariant =
            item.outcome === 'completed'
              ? 'completed'
              : item.outcome === 'error'
              ? 'critical'
              : item.outcome === 'abandoned'
              ? 'abandoned'
              : 'medium';

          return (
            <div
              key={item.persona}
              role="button"
              tabIndex={0}
              onClick={handleCardClick}
              onKeyDown={(e) => {
                if (e.key === ' ' || e.key === 'Enter') {
                  e.preventDefault();
                  handleCardClick();
                }
              }}
              className={`p-4 rounded-xl border transition-all duration-150 cursor-pointer text-left select-none ${
                isSelected
                  ? 'bg-gremlin/10 border-2 border-gremlin shadow-subtle'
                  : 'bg-surface border-stone hover:border-muted/50 hover:bg-canvas/40'
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
                      <span className="font-bold text-ink text-sm">
                        {item.persona_label || details.name}
                      </span>
                      {isSelected && (
                        <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-gremlin/25 text-ink border border-gremlin font-bold">
                          Active View
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-muted font-mono">
                      {item.steps} {item.steps === 1 ? 'step' : 'steps'} taken
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  {/* Outcome Badge */}
                  <Badge variant={outcomeVariant}>{item.outcome}</Badge>

                  {/* Score Pill */}
                  <div className="text-right min-w-[70px]">
                    <span className={`text-lg font-black font-mono tracking-tight ${scoreTextColor}`}>
                      {item.score}
                    </span>
                    <span className="text-[11px] text-muted font-normal"> / 100</span>
                  </div>
                </div>
              </div>

              {/* Row 2: Visual Score Bar */}
              <div className="w-full h-2 rounded-full bg-stone overflow-hidden relative">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${scoreBarBg}`}
                  style={{ width: `${Math.max(4, Math.min(100, item.score))}%` }}
                />
              </div>

              {/* Row 3: Top Finding Highlight & Actions */}
              <div className="mt-3 pt-2.5 border-t border-stone flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                <div className="flex items-center gap-2 text-ink min-w-0 flex-1">
                  <ShieldAlert className="w-3.5 h-3.5 text-severity-medium-fg shrink-0" />
                  <span className="text-muted font-medium shrink-0">Top Finding:</span>
                  <span className="text-ink truncate font-medium">{item.top_finding}</span>
                </div>

                {onViewRun && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectPersona?.(item.persona);
                      onViewRun(item.persona);
                    }}
                    rightIcon={<ArrowRight className="w-3.5 h-3.5 text-gremlin-dark" />}
                    className="shrink-0 text-xs font-bold"
                  >
                    View Run
                  </Button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
