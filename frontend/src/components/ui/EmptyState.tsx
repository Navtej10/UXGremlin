import React from 'react';

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description: string;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className = '',
}: EmptyStateProps) {
  return (
    <div
      className={`p-8 md:p-12 text-center bg-surface border border-stone rounded-2xl flex flex-col items-center justify-center gap-3 shadow-card ${className}`}
    >
      {icon && <div className="mb-1 text-muted">{icon}</div>}
      <h4 className="text-base font-bold text-ink">{title}</h4>
      <p className="text-xs text-muted max-w-md leading-relaxed">{description}</p>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
