import { useState } from 'react';
import {
  TrendingDown,
  TrendingUp,
  Minus,
  CheckCircle2,
  AlertTriangle,
  History,
  ArrowRight,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { Badge, Card } from './ui';

export interface DeltaFinding {
  title: string;
  severity: 'critical' | 'high' | 'medium';
  what_happened?: string;
  impact?: string;
  recommendation?: string;
  suggested_fix?: string;
  discovered_by?: string;
  screenshot?: string | null;
}

export interface ReportDelta {
  previous_session_id?: string;
  previous_score: number;
  new_score: number;
  score_delta: number;
  previous_outcome: string;
  new_outcome: string;
  resolved_findings: DeltaFinding[];
  new_findings: DeltaFinding[];
  persistent_findings: DeltaFinding[];
}

interface BeforeAfterPanelProps {
  delta: ReportDelta;
}

export function BeforeAfterPanel({ delta }: BeforeAfterPanelProps) {
  const [activeTab, setActiveTab] = useState<'resolved' | 'new' | 'persistent'>('resolved');
  const [isCollapsed, setIsCollapsed] = useState(false);

  const isImproved = delta.score_delta < 0;
  const isRegressed = delta.score_delta > 0;

  const resolvedCount = delta.resolved_findings?.length ?? 0;
  const newCount = delta.new_findings?.length ?? 0;
  const persistentCount = delta.persistent_findings?.length ?? 0;

  return (
    <Card className="overflow-hidden shadow-card">
      {/* Header bar */}
      <div className="px-6 py-4 bg-canvas/40 border-b border-stone flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-gremlin/20 border border-gremlin/50 flex items-center justify-center">
            <History className="w-4 h-4 text-gremlin-dark" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xs font-bold uppercase tracking-wider text-ink">
                Re-Test Usability Comparison
              </h2>
              {delta.previous_session_id && (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-surface text-muted border border-stone">
                  vs {delta.previous_session_id.slice(0, 8)}
                </span>
              )}
            </div>
            <p className="text-xs text-muted">
              Automated regression delta against previous audit session
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Score Delta Badge */}
          {isImproved ? (
            <Badge
              variant="passed"
              customIcon={<TrendingDown className="w-3.5 h-3.5" />}
            >
              {Math.abs(delta.score_delta)} pts lower friction (Improved!)
            </Badge>
          ) : isRegressed ? (
            <Badge
              variant="critical"
              customIcon={<TrendingUp className="w-3.5 h-3.5" />}
            >
              +{delta.score_delta} pts more friction (Regressed)
            </Badge>
          ) : (
            <Badge
              variant="medium"
              customIcon={<Minus className="w-3.5 h-3.5" />}
            >
              0 pts delta (Unchanged)
            </Badge>
          )}

          <button
            type="button"
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="p-1.5 rounded-lg bg-surface hover:bg-stone/30 text-muted hover:text-ink border border-stone transition cursor-pointer"
            title={isCollapsed ? 'Expand delta panel' : 'Collapse delta panel'}
          >
            {isCollapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {!isCollapsed && (
        <div className="p-6 space-y-6">
          {/* Top Comparison Metrics Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Score Delta Card */}
            <div className="bg-canvas border border-stone rounded-xl p-4 flex items-center justify-between">
              <div>
                <span className="text-[11px] font-bold uppercase tracking-wider text-muted block mb-1">
                  Friction Score Delta
                </span>
                <div className="flex items-center gap-3">
                  <span className="text-2xl font-black text-muted font-mono">
                    {delta.previous_score}
                  </span>
                  <ArrowRight className="w-4 h-4 text-muted" />
                  <span
                    className={`text-3xl font-black font-mono ${
                      delta.new_score <= 20
                        ? 'text-severity-low-fg'
                        : delta.new_score <= 45
                        ? 'text-severity-medium-fg'
                        : 'text-severity-critical-fg'
                    }`}
                  >
                    {delta.new_score}
                  </span>
                  <span className="text-xs text-muted font-mono">/ 100</span>
                </div>
              </div>
              <div className="text-right">
                <span className="text-[10px] text-muted uppercase font-semibold block">
                  Net Impact
                </span>
                <span
                  className={`text-sm font-extrabold ${
                    isImproved
                      ? 'text-severity-low-fg'
                      : isRegressed
                      ? 'text-severity-critical-fg'
                      : 'text-muted'
                  }`}
                >
                  {isImproved
                    ? `${Math.abs(delta.score_delta)} pts lower friction`
                    : isRegressed
                    ? `${delta.score_delta} pts more friction`
                    : 'Identical friction score'}
                </span>
              </div>
            </div>

            {/* Outcome Comparison Card */}
            <div className="bg-canvas border border-stone rounded-xl p-4 flex items-center justify-between">
              <div>
                <span className="text-[11px] font-bold uppercase tracking-wider text-muted block mb-1">
                  Task Completion Status
                </span>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono uppercase px-2 py-0.5 rounded bg-surface border border-stone text-muted">
                    {delta.previous_outcome}
                  </span>
                  <ArrowRight className="w-3.5 h-3.5 text-muted" />
                  <Badge
                    variant={delta.new_outcome === 'completed' ? 'completed' : 'critical'}
                  >
                    {delta.new_outcome}
                  </Badge>
                </div>
              </div>

              <div className="flex items-center gap-1.5 text-xs text-muted font-medium">
                {delta.previous_outcome !== 'completed' && delta.new_outcome === 'completed' ? (
                  <span className="flex items-center gap-1 text-severity-low-fg font-semibold">
                    <ShieldCheck className="w-4 h-4" /> Blockers Solved
                  </span>
                ) : (
                  <span>Outcome verified</span>
                )}
              </div>
            </div>
          </div>

          {/* Findings Filter Tabs */}
          <div className="border-t border-stone pt-4">
            <div className="flex items-center gap-2 mb-4">
              <button
                type="button"
                onClick={() => setActiveTab('resolved')}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold border transition-all cursor-pointer ${
                  activeTab === 'resolved'
                    ? 'bg-severity-low-bg border-severity-low-fg/40 text-severity-low-fg shadow-subtle'
                    : 'bg-surface border-stone text-muted hover:text-ink hover:border-muted/50'
                }`}
              >
                <CheckCircle2 className="w-3.5 h-3.5 text-severity-low-fg" />
                <span>Resolved Findings</span>
                <span className="px-1.5 py-0.5 rounded-full text-[10px] font-mono bg-surface border border-stone text-ink">
                  {resolvedCount}
                </span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab('new')}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold border transition-all cursor-pointer ${
                  activeTab === 'new'
                    ? 'bg-severity-critical-bg border-severity-critical-fg/40 text-severity-critical-fg shadow-subtle'
                    : 'bg-surface border-stone text-muted hover:text-ink hover:border-muted/50'
                }`}
              >
                <AlertTriangle className="w-3.5 h-3.5 text-severity-critical-fg" />
                <span>New Findings</span>
                <span className="px-1.5 py-0.5 rounded-full text-[10px] font-mono bg-surface border border-stone text-ink">
                  {newCount}
                </span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab('persistent')}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold border transition-all cursor-pointer ${
                  activeTab === 'persistent'
                    ? 'bg-severity-medium-bg border-severity-medium-fg/40 text-severity-medium-fg shadow-subtle'
                    : 'bg-surface border-stone text-muted hover:text-ink hover:border-muted/50'
                }`}
              >
                <History className="w-3.5 h-3.5 text-severity-medium-fg" />
                <span>Persistent Findings</span>
                <span className="px-1.5 py-0.5 rounded-full text-[10px] font-mono bg-surface border border-stone text-ink">
                  {persistentCount}
                </span>
              </button>
            </div>

            {/* Findings List per Active Tab */}
            <div className="space-y-3">
              {activeTab === 'resolved' && (
                resolvedCount === 0 ? (
                  <p className="text-xs text-muted italic py-2">
                    No findings were completely resolved compared to the previous test run.
                  </p>
                ) : (
                  delta.resolved_findings.map((f, idx) => (
                    <div
                      key={idx}
                      className="p-4 bg-severity-low-bg/40 border border-severity-low-fg/30 rounded-xl flex items-start justify-between gap-4"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <CheckCircle2 className="w-4 h-4 text-severity-low-fg shrink-0" />
                          <span className="text-xs font-bold text-ink line-through">
                            {f.title}
                          </span>
                          <Badge variant="passed">RESOLVED</Badge>
                        </div>
                        {f.what_happened && (
                          <p className="text-xs text-muted pl-6">{f.what_happened}</p>
                        )}
                      </div>
                      <Badge variant={f.severity}>{f.severity}</Badge>
                    </div>
                  ))
                )
              )}

              {activeTab === 'new' && (
                newCount === 0 ? (
                  <p className="text-xs text-muted italic py-2">
                    No new usability issues or defects were detected in this re-test.
                  </p>
                ) : (
                  delta.new_findings.map((f, idx) => (
                    <div
                      key={idx}
                      className="p-4 bg-severity-critical-bg/40 border border-severity-critical-fg/30 rounded-xl flex items-start justify-between gap-4"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <AlertTriangle className="w-4 h-4 text-severity-critical-fg shrink-0" />
                          <span className="text-xs font-bold text-ink">
                            {f.title}
                          </span>
                          <Badge variant="critical">NEW</Badge>
                        </div>
                        {f.what_happened && (
                          <p className="text-xs text-ink/80 pl-6">{f.what_happened}</p>
                        )}
                        {f.recommendation && (
                          <p className="text-xs text-gremlin-dark font-medium pl-6">
                            Fix: {f.recommendation}
                          </p>
                        )}
                      </div>
                      <Badge variant={f.severity}>{f.severity}</Badge>
                    </div>
                  ))
                )
              )}

              {activeTab === 'persistent' && (
                persistentCount === 0 ? (
                  <p className="text-xs text-muted italic py-2">
                    None of the previous findings persisted into this re-test.
                  </p>
                ) : (
                  delta.persistent_findings.map((f, idx) => (
                    <div
                      key={idx}
                      className="p-4 bg-severity-medium-bg/40 border border-severity-medium-fg/30 rounded-xl flex items-start justify-between gap-4"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <History className="w-4 h-4 text-severity-medium-fg shrink-0" />
                          <span className="text-xs font-bold text-ink">
                            {f.title}
                          </span>
                          <Badge variant="medium">STILL PERSISTS</Badge>
                        </div>
                        {f.what_happened && (
                          <p className="text-xs text-muted pl-6">{f.what_happened}</p>
                        )}
                        {f.recommendation && (
                          <p className="text-xs text-gremlin-dark font-medium pl-6">
                            Fix: {f.recommendation}
                          </p>
                        )}
                      </div>
                      <Badge variant={f.severity}>{f.severity}</Badge>
                    </div>
                  ))
                )
              )}
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
