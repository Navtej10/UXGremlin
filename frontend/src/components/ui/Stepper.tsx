import { Minus, Plus } from 'lucide-react';

interface StepperProps {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  label?: string;
  helperText?: string;
  disabled?: boolean;
  className?: string;
}

export function Stepper({
  value,
  onChange,
  min = 1,
  max = 10,
  label,
  helperText,
  disabled = false,
  className = '',
}: StepperProps) {
  const handleDecrement = () => {
    if (value > min) onChange(value - 1);
  };

  const handleIncrement = () => {
    if (value < max) onChange(value + 1);
  };

  return (
    <div className={`flex items-center justify-between gap-3 ${className}`}>
      {(label || helperText) && (
        <div className="flex-1">
          {label && <span className="block text-xs font-semibold text-ink">{label}</span>}
          {helperText && <span className="block text-xs text-muted mt-0.5 leading-relaxed">{helperText}</span>}
        </div>
      )}
      <div className="flex items-center border border-stone rounded-xl bg-surface p-0.5 shadow-subtle shrink-0">
        <button
          type="button"
          onClick={handleDecrement}
          disabled={disabled || value <= min}
          aria-label="Decrease"
          className="p-1.5 rounded-lg text-ink hover:bg-stone/30 disabled:opacity-30 disabled:cursor-not-allowed transition cursor-pointer"
        >
          <Minus className="w-3.5 h-3.5" />
        </button>
        <span className="w-9 text-center font-mono text-xs font-bold text-ink select-none">
          {value}
        </span>
        <button
          type="button"
          onClick={handleIncrement}
          disabled={disabled || value >= max}
          aria-label="Increase"
          className="p-1.5 rounded-lg text-ink hover:bg-stone/30 disabled:opacity-30 disabled:cursor-not-allowed transition cursor-pointer"
        >
          <Plus className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
