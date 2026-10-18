import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes, type ReactNode } from 'react';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  helperText?: string;
  error?: string;
  mono?: boolean;
  leftIcon?: ReactNode;
  rightElement?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      label,
      helperText,
      error,
      mono = false,
      leftIcon,
      rightElement,
      className = '',
      id,
      ...props
    },
    ref
  ) => {
    const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);

    return (
      <div className="w-full flex flex-col gap-1.5 text-left">
        {label && (
          <label htmlFor={inputId} className="text-xs font-semibold text-ink flex items-center justify-between">
            <span>{label}</span>
          </label>
        )}
        <div className="relative flex items-center">
          {leftIcon && (
            <span className="absolute left-3 text-muted pointer-events-none flex items-center shrink-0">
              {leftIcon}
            </span>
          )}
          <input
            id={inputId}
            ref={ref}
            className={`w-full bg-surface text-ink border rounded-xl py-2 text-sm transition-colors placeholder:text-muted/60 focus-visible:outline-2 focus-visible:outline-gremlin-dark focus-visible:outline-offset-1 disabled:opacity-50 disabled:bg-stone/20 ${
              leftIcon ? 'pl-9' : 'pl-3.5'
            } ${rightElement ? 'pr-12' : 'pr-3.5'} ${
              mono ? 'font-mono text-xs' : ''
            } ${error ? 'border-severity-critical-fg' : 'border-stone hover:border-muted/50'} ${className}`}
            {...props}
          />
          {rightElement && (
            <div className="absolute right-2 flex items-center">
              {rightElement}
            </div>
          )}
        </div>
        {error ? (
          <p className="text-xs text-severity-critical-fg font-medium">{error}</p>
        ) : helperText ? (
          <p className="text-xs text-muted leading-relaxed">{helperText}</p>
        ) : null}
      </div>
    );
  }
);

Input.displayName = 'Input';

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  helperText?: string;
  error?: string;
  mono?: boolean;
  bottomRightHint?: ReactNode;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  (
    {
      label,
      helperText,
      error,
      mono = false,
      bottomRightHint,
      className = '',
      id,
      ...props
    },
    ref
  ) => {
    const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);

    return (
      <div className="w-full flex flex-col gap-1.5 text-left">
        {label && (
          <label htmlFor={inputId} className="text-xs font-semibold text-ink flex items-center justify-between">
            <span>{label}</span>
          </label>
        )}
        <div className="relative">
          <textarea
            id={inputId}
            ref={ref}
            className={`w-full bg-surface text-ink border rounded-xl p-3 text-sm transition-colors placeholder:text-muted/60 focus-visible:outline-2 focus-visible:outline-gremlin-dark focus-visible:outline-offset-1 disabled:opacity-50 disabled:bg-stone/20 ${
              mono ? 'font-mono text-xs' : ''
            } ${error ? 'border-severity-critical-fg' : 'border-stone hover:border-muted/50'} ${className}`}
            {...props}
          />
          {bottomRightHint && (
            <div className="absolute bottom-2.5 right-3 text-[11px] font-mono text-muted select-none pointer-events-none">
              {bottomRightHint}
            </div>
          )}
        </div>
        {error ? (
          <p className="text-xs text-severity-critical-fg font-medium">{error}</p>
        ) : helperText ? (
          <p className="text-xs text-muted leading-relaxed">{helperText}</p>
        ) : null}
      </div>
    );
  }
);

Textarea.displayName = 'Textarea';
