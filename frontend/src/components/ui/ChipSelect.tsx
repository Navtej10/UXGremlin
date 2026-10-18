import type { ReactNode } from 'react';

interface ChipSelectProps {
  label?: string;
  selected?: boolean;
  onClick?: () => void;
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function ChipSelect({
  label,
  selected = false,
  onClick,
  icon,
  children,
  className = '',
}: ChipSelectProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all select-none cursor-pointer focus-visible:outline-2 focus-visible:outline-gremlin-dark focus-visible:outline-offset-2 ${
        selected
          ? 'bg-gremlin/25 text-ink border-2 border-gremlin font-semibold shadow-subtle'
          : 'bg-surface text-ink border border-stone hover:border-muted/50 hover:bg-stone/20'
      } ${className}`}
    >
      {icon && <span className="shrink-0">{icon}</span>}
      {label && <span className="text-muted font-normal mr-1">{label}</span>}
      <span>{children}</span>
    </button>
  );
}
