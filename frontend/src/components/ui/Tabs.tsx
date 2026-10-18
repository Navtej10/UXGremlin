import type { ReactNode } from 'react';

export interface TabItem {
  id: string;
  label: string;
  icon?: ReactNode;
  badge?: ReactNode;
}

interface TabsProps {
  items: TabItem[];
  activeId: string;
  onChange: (id: string) => void;
  className?: string;
}

export function Tabs({ items, activeId, onChange, className = '' }: TabsProps) {
  return (
    <div
      role="tablist"
      className={`flex items-center gap-1 border-b border-stone overflow-x-auto ${className}`}
    >
      {items.map((tab) => {
        const isActive = tab.id === activeId;
        return (
          <button
            key={tab.id}
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(tab.id)}
            className={`flex items-center gap-2 px-3.5 py-2.5 text-xs font-semibold whitespace-nowrap transition-all border-b-2 -mb-[2px] cursor-pointer focus-visible:outline-2 focus-visible:outline-gremlin-dark focus-visible:outline-offset-2 ${
              isActive
                ? 'border-gremlin-dark text-ink bg-gremlin/10 rounded-t-lg'
                : 'border-transparent text-muted hover:text-ink hover:border-stone'
            }`}
          >
            {tab.icon && <span className="shrink-0">{tab.icon}</span>}
            <span>{tab.label}</span>
            {tab.badge && <span className="shrink-0">{tab.badge}</span>}
          </button>
        );
      })}
    </div>
  );
}
