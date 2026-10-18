import type { HTMLAttributes, ReactNode, ComponentType } from 'react';
import {
  AlertTriangle,
  AlertCircle,
  CheckCircle2,
  Check,
  XCircle,
  Sparkles,
  Activity,
} from 'lucide-react';

export type BadgeVariant =
  | 'critical'
  | 'high'
  | 'medium'
  | 'low'
  | 'passed'
  | 'running'
  | 'completed'
  | 'abandoned'
  | 'ai-lilac';

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  customIcon?: ReactNode;
  hideIcon?: boolean;
}

const BADGE_CONFIG: Record<
  BadgeVariant,
  {
    bg: string;
    text: string;
    border: string;
    icon: ComponentType<{ className?: string }>;
    defaultLabel: string;
  }
> = {
  critical: {
    bg: 'bg-severity-critical-bg',
    text: 'text-severity-critical-fg',
    border: 'border-severity-critical-fg/20',
    icon: AlertCircle,
    defaultLabel: 'Critical',
  },
  high: {
    bg: 'bg-severity-high-bg',
    text: 'text-severity-high-fg',
    border: 'border-severity-high-fg/20',
    icon: AlertTriangle,
    defaultLabel: 'High',
  },
  medium: {
    bg: 'bg-severity-medium-bg',
    text: 'text-severity-medium-fg',
    border: 'border-severity-medium-fg/20',
    icon: AlertCircle,
    defaultLabel: 'Medium',
  },
  low: {
    bg: 'bg-severity-low-bg',
    text: 'text-severity-low-fg',
    border: 'border-severity-low-fg/20',
    icon: CheckCircle2,
    defaultLabel: 'Low',
  },
  passed: {
    bg: 'bg-severity-low-bg',
    text: 'text-severity-low-fg',
    border: 'border-severity-low-fg/20',
    icon: Check,
    defaultLabel: 'Passed',
  },
  running: {
    bg: 'bg-gremlin/20',
    text: 'text-ink',
    border: 'border-gremlin/50',
    icon: Activity,
    defaultLabel: 'Running',
  },
  completed: {
    bg: 'bg-severity-low-bg',
    text: 'text-severity-low-fg',
    border: 'border-severity-low-fg/20',
    icon: CheckCircle2,
    defaultLabel: 'Completed',
  },
  abandoned: {
    bg: 'bg-severity-critical-bg',
    text: 'text-severity-critical-fg',
    border: 'border-severity-critical-fg/20',
    icon: XCircle,
    defaultLabel: 'Abandoned',
  },
  'ai-lilac': {
    bg: 'bg-lilac',
    text: 'text-lilac-text',
    border: 'border-lilac-text/25',
    icon: Sparkles,
    defaultLabel: 'AI Reasoning',
  },
};

export function Badge({
  variant = 'medium',
  customIcon,
  hideIcon = false,
  className = '',
  children,
  ...props
}: BadgeProps) {
  const config = BADGE_CONFIG[variant] || BADGE_CONFIG.medium;
  const IconComponent = config.icon;

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold border ${config.bg} ${config.text} ${config.border} shrink-0 select-none ${className}`}
      {...props}
    >
      {!hideIcon && (
        <span className="shrink-0">
          {customIcon ? (
            customIcon
          ) : variant === 'running' ? (
            <span className="w-1.5 h-1.5 rounded-full bg-gremlin-dark animate-pulse" />
          ) : (
            <IconComponent className="w-3.5 h-3.5" />
          )}
        </span>
      )}
      <span>{children || config.defaultLabel}</span>
    </span>
  );
}
