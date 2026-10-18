
interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
  helperText?: string;
  disabled?: boolean;
  id?: string;
  className?: string;
}

export function Toggle({
  checked,
  onChange,
  label,
  helperText,
  disabled = false,
  id,
  className = '',
}: ToggleProps) {
  const toggleId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);

  return (
    <div className={`flex items-start justify-between gap-3 ${className}`}>
      {(label || helperText) && (
        <label htmlFor={toggleId} className="flex-1 cursor-pointer select-none">
          {label && <span className="block text-xs font-semibold text-ink">{label}</span>}
          {helperText && <span className="block text-xs text-muted mt-0.5 leading-relaxed">{helperText}</span>}
        </label>
      )}
      <button
        id={toggleId}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => !disabled && onChange(!checked)}
        className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus-visible:outline-2 focus-visible:outline-gremlin-dark focus-visible:outline-offset-2 disabled:opacity-40 disabled:cursor-not-allowed ${
          checked ? 'bg-gremlin-dark' : 'bg-stone'
        }`}
      >
        <span
          className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-surface shadow-subtle ring-0 transition duration-200 ease-in-out ${
            checked ? 'translate-x-5' : 'translate-x-0'
          }`}
        />
      </button>
    </div>
  );
}
