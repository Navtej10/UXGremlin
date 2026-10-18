
interface StepChipProps {
  step: number;
  active?: boolean;
  hasFriction?: boolean;
  severity?: 'critical' | 'high' | 'medium' | 'low';
  onClick?: () => void;
  className?: string;
}

export function StepChip({
  step,
  active = false,
  hasFriction = false,
  severity = 'medium',
  onClick,
  className = '',
}: StepChipProps) {
  const dotColorClass =
    severity === 'critical' || severity === 'high'
      ? 'bg-severity-critical-fg'
      : severity === 'low'
      ? 'bg-severity-low-fg'
      : 'bg-severity-medium-fg';

  return (
    <button
      type="button"
      onClick={onClick}
      className={`relative inline-flex items-center justify-center px-3 py-1 rounded-lg font-mono text-xs font-bold transition-all select-none cursor-pointer focus-visible:outline-2 focus-visible:outline-gremlin-dark focus-visible:outline-offset-2 ${
        active
          ? 'bg-gremlin text-ink border border-gremlin-dark shadow-subtle'
          : 'bg-surface text-muted hover:text-ink border border-stone hover:border-muted/50'
      } ${className}`}
    >
      <span>step {step}</span>
      {hasFriction && (
        <span
          className={`absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full border-2 border-surface ${dotColorClass}`}
          title="Friction detected at this step"
        />
      )}
    </button>
  );
}
