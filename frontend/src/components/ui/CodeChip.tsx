import { useState, type MouseEvent } from 'react';
import { Copy, Check } from 'lucide-react';

interface CodeChipProps {
  code: string;
  copyable?: boolean;
  prefix?: string;
  className?: string;
}

export function CodeChip({
  code,
  copyable = true,
  prefix,
  className = '',
}: CodeChipProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async (e: MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  };

  return (
    <div
      className={`inline-flex items-center gap-2 px-2.5 py-1 bg-canvas border border-stone rounded-lg font-mono text-xs text-ink select-all ${className}`}
    >
      {prefix && (
        <span className="text-[10px] uppercase font-bold tracking-wider text-muted select-none">
          {prefix}:
        </span>
      )}
      <span className="truncate max-w-xs md:max-w-md">{code}</span>
      {copyable && (
        <button
          type="button"
          onClick={handleCopy}
          aria-label={copied ? 'Copied' : 'Copy code'}
          className="text-muted hover:text-ink transition p-0.5 rounded cursor-pointer"
          title="Copy"
        >
          {copied ? (
            <Check className="w-3.5 h-3.5 text-severity-low-fg" />
          ) : (
            <Copy className="w-3.5 h-3.5" />
          )}
        </button>
      )}
    </div>
  );
}
