import { useEffect, useState } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  RefreshCcw,
  Share2,
  Download,
  Printer,
  RotateCcw,
  Check,
  ArrowRight,
  FileText,
  ExternalLink,
  AlertTriangle,
  Activity,
  Info,
} from 'lucide-react';
import { ComparisonSummary, type ComparisonItem } from './ComparisonSummary';
import { BeforeAfterPanel, type ReportDelta } from './BeforeAfterPanel';
import { Gremlin } from './mascot/Gremlin';
import {
  Badge,
  Button,
  Card,
  CodeChip,
  StepChip,
  TerminalPanel,
} from './ui';

export interface HistoryItem {
  thought: string;
  screenshot: string | null;
  step_number?: number;
  action?: string;
}

export interface ActionItem {
  step_number: number;
  action: string;
  target?: string;
  thought: string;
  screenshot: string | null;
  ok?: boolean;
  url?: string;
  url_after?: string;
  friction_type?: string | null;
  friction_note?: string;
}

interface ScorePart {
  name: string;
  points: number;
  evidence: number[];
  why: string;
}

export interface Finding {
  title: string;
  severity: 'critical' | 'high' | 'medium';
  evidence_steps: number[];
  what_happened: string;
  impact: string;
  recommendation: string;
  consistency?: 'consistent' | 'occasional';
  step_number?: number;
  screenshot?: string | null;
  bounding_box?: { x: number; y: number; width: number; height: number } | null;
  suggested_fix?: string;
  selector?: string;
  discovered_by?: string;
}

export interface SabotageReport {
  session_id?: string;
  previous_session_id?: string;
  delta?: ReportDelta;
  url?: string;
  task?: string;
  persona?: string;
  personas?: string[];
  is_compare?: boolean;
  comparison?: Record<string, ComparisonItem>;
  comparison_summary?: ComparisonItem[];
  persona_reports?: Record<string, SabotageReport>;
  status?: string;
  error?: string;
  error_at_beginning?: boolean;
  prompt_rerun?: boolean;
  rerun_prompt?: string;
  outcome?: 'completed' | 'abandoned' | 'gave_up' | 'max_steps_reached' | 'error' | 'timeout' | 'system_error';
  outcome_reason?: string;
  claimed_outcome?: string;
  verified_outcome?: string;
  baseline_failed?: boolean;
  baseline_note?: string;
  expected_steps?: number;
  runs?: number;
  score_min?: number;
  score_max?: number;
  score_mean?: number;
  score: {
    total: number;
    label: string;
    parts: ScorePart[];
    steps_taken: number;
    ideal_steps: number;
    runs?: number;
    score_min?: number;
    score_max?: number;
    score_mean?: number;
  };
  verdict: string;
  findings: Finding[];
  bugs?: number;
  actions?: ActionItem[];
}

export interface ReportProps {
  session: {
    session_id?: string;
    previous_session_id?: string;
    url: string;
    task: string;
    persona: string;
    personas?: string[];
  };
  history: HistoryItem[];
  initialReport?: SabotageReport | null;
  isReadOnly?: boolean;
  onRestart: () => void;
  onReRun?: (prevSession: {
    url: string;
    task: string;
    persona: string;
    personas?: string[];
    previous_session_id: string;
  }) => void;
}

const PERSONA_NAMES: Record<string, string> = {
  pro_tester: '🎯 Professional UX Tester',
  impatient: '😈 Impatient User',
  confused: '😵‍💫 Confused User',
  skeptic: '🧐 Skeptical User',
  mobile: '📱 Mobile User',
};

export type ReportViewMode = 'score' | 'explanation' | 'run';

export function Report({
  session,
  history,
  initialReport,
  isReadOnly,
  onRestart,
  onReRun,
}: ReportProps) {
  const [viewMode, setViewMode] = useState<ReportViewMode>('score');
  const [currentIndex, setCurrentIndex] = useState(0);
  const [report, setReport] = useState<SabotageReport | null>(initialReport || null);
  const [copiedShare, setCopiedShare] = useState(false);
  const [selectedPersona, setSelectedPersona] = useState<string>(
    initialReport?.personas?.[0] || session.personas?.[0] || session.persona
  );

  const currentSessionId = report?.session_id || session.session_id;

  const handleShare = async () => {
    if (!currentSessionId) return;
    const shareUrl = `${window.location.origin}/report/${currentSessionId}`;
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopiedShare(true);
      setTimeout(() => setCopiedShare(false), 2500);
    } catch {
      prompt('Copy shareable report link:', shareUrl);
    }
  };

  const handleExportJson = () => {
    if (!currentSessionId) return;
    window.open(
      `http://127.0.0.1:8000/api/report/${encodeURIComponent(currentSessionId)}/export/json`,
      '_blank'
    );
  };

  const handlePrintHtml = () => {
    if (!currentSessionId) return;
    window.open(
      `http://127.0.0.1:8000/api/report/${encodeURIComponent(currentSessionId)}/export/html`,
      '_blank'
    );
  };

  useEffect(() => {
    if (initialReport && (initialReport.score || initialReport.error_at_beginning)) {
      return;
    }

    let cancelled = false;
    let tries = 0;
    const reportUrl = session.session_id
      ? `http://127.0.0.1:8000/api/report?session_id=${encodeURIComponent(session.session_id)}`
      : 'http://127.0.0.1:8000/api/report';

    const load = async () => {
      try {
        const res = await fetch(reportUrl);
        const data = await res.json();
        if (data?.score || data?.comparison || data?.error_at_beginning) {
          if (!cancelled) {
            setReport(data as SabotageReport);
            if (data.personas && data.personas.length > 0) {
              setSelectedPersona((curr) =>
                data.personas.includes(curr) ? curr : data.personas[0]
              );
            }
            if (session.session_id && !window.location.pathname.startsWith('/report/')) {
              window.history.pushState(null, '', `/report/${session.session_id}`);
            }
          }
          return;
        }
      } catch {
        /* retry below */
      }
      if (!cancelled && ++tries < 15) setTimeout(load, 1000);
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [session.session_id, initialReport]);

  // Active persona report (for switching between archetypes)
  const activeReport: SabotageReport =
    (report?.persona_reports && report.persona_reports[selectedPersona]) ||
    report ||
    ({} as SabotageReport);

  // ONE source of truth: the backend's saved action list
  const slideshowItems: (ActionItem | HistoryItem)[] =
    activeReport?.actions && activeReport.actions.length > 0
      ? activeReport.actions
      : report?.actions && report.actions.length > 0
      ? report.actions
      : history;
  const totalSteps = slideshowItems.length;

  const jumpToStep = (n: number) => {
    if (activeReport?.actions && activeReport.actions.length > 0) {
      const idx = activeReport.actions.findIndex((a) => a.step_number === n);
      if (idx >= 0) {
        setCurrentIndex(idx);
        setViewMode('run');
        return;
      }
    }
    const prefix = `Step ${n} · `;
    const exec = history.findIndex((h) => h.thought.startsWith(`${prefix}Executing`));
    const any = history.findIndex((h) => h.thought.startsWith(prefix));
    const i = exec >= 0 ? exec : any;
    if (i >= 0) {
      setCurrentIndex(i);
    } else {
      setCurrentIndex(Math.max(0, Math.min(totalSteps - 1, n - 1)));
    }
    setViewMode('run');
  };

  const handleViewRun = (personaId?: string) => {
    if (personaId) {
      setSelectedPersona(personaId);
    }
    setCurrentIndex(0);
    setViewMode('run');
  };

  const handleViewExplanation = (personaId?: string) => {
    if (personaId) {
      setSelectedPersona(personaId);
    }
    setViewMode('explanation');
  };

  // Keyboard navigation for step replay
  useEffect(() => {
    if (viewMode !== 'run') return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') {
        setCurrentIndex((prev) => Math.max(0, prev - 1));
      } else if (e.key === 'ArrowRight') {
        setCurrentIndex((prev) => Math.min(Math.max(0, totalSteps - 1), prev + 1));
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [viewMode, totalSteps]);

  const currentScore = activeReport?.score || report?.score;
  const total = currentScore?.total ?? 0;
  const scoreTextColor =
    total <= 20
      ? 'text-severity-low-fg'
      : total <= 45
      ? 'text-severity-medium-fg'
      : 'text-severity-critical-fg';

  const handlePrev = () => {
    setCurrentIndex((prev) => Math.max(0, prev - 1));
  };

  const handleNext = () => {
    setCurrentIndex((prev) => Math.min(Math.max(0, totalSteps - 1), prev + 1));
  };

  const currentItem = slideshowItems[currentIndex];
  const outcome = activeReport?.outcome || report?.outcome;
  const outcomeReason = activeReport?.outcome_reason || report?.outcome_reason;
  const claimedOutcome = activeReport?.claimed_outcome || report?.claimed_outcome;
  const verifiedOutcome = activeReport?.verified_outcome || report?.verified_outcome;
  const currentFindings =
    activeReport?.findings && activeReport.findings.length > 0
      ? activeReport.findings
      : report?.findings || [];

  const isErrorAtBeginning = Boolean(
    report?.error_at_beginning ||
    activeReport?.error_at_beginning ||
    report?.status === 'error_at_beginning' ||
    activeReport?.status === 'error_at_beginning' ||
    ((outcome === 'error' || report?.outcome === 'error') &&
      totalSteps === 0 &&
      (report?.error || activeReport?.error || outcomeReason))
  );

  const initialErrorMessage =
    report?.error ||
    activeReport?.error ||
    outcomeReason ||
    'The target application could not be reached or an error occurred before testing could start.';

  const initialRerunPrompt =
    report?.rerun_prompt ||
    activeReport?.rerun_prompt ||
    `The test could not start due to an error: ${initialErrorMessage}. Please verify that the target URL is accessible and rerun the test.`;

  const isSystemInterrupted = Boolean(
    outcome === 'timeout' ||
    outcome === 'system_error' ||
    activeReport?.outcome === 'timeout' ||
    activeReport?.outcome === 'system_error'
  );

  const triggerRerun = () => {
    const targetSessionId = report?.session_id || session.session_id || '';
    if (onReRun) {
      onReRun({
        url: report?.url || session.url,
        task: report?.task || session.task,
        persona: selectedPersona || session.persona,
        personas: report?.personas || session.personas,
        previous_session_id: targetSessionId,
      });
    } else {
      onRestart();
    }
  };

  // Fallback ComparisonItem in case backend didn't supply comparison_summary
  const fallbackComparisonItem: ComparisonItem = {
    persona: selectedPersona || session.persona || 'pro_tester',
    score: currentScore?.total ?? 0,
    outcome: outcome || 'completed',
    steps: totalSteps || currentScore?.steps_taken || 0,
    top_finding: currentFindings[0]?.title || 'No critical issues identified',
  };

  const outcomeVariant =
    outcome === 'completed'
      ? 'completed'
      : outcome === 'error'
      ? 'critical'
      : outcome === 'abandoned' || outcome === 'gave_up'
      ? 'abandoned'
      : 'medium';

  return (
    <div className="min-h-screen flex flex-col bg-canvas text-ink antialiased">
      {/* Universal Sticky Top Header Bar */}
      <header className="h-16 border-b border-stone bg-surface px-6 md:px-10 flex items-center justify-between shrink-0 sticky top-0 z-30 shadow-subtle gap-4">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onRestart}
            className="flex items-center gap-2 cursor-pointer select-none text-left hover:opacity-80 transition-opacity"
            title="Return to Launchpad (Home)"
          >
            <Gremlin pose="completion" size="sm" animate={false} />
            <div>
              <span className="font-extrabold text-base tracking-tight text-ink">
                UXGremlin
              </span>
              <span className="hidden sm:inline-block text-xs text-muted ml-2.5 pl-2.5 border-l border-stone">
                Sabotage Report
              </span>
            </div>
          </button>
          {isReadOnly && (
            <Badge variant="medium">Archived Report</Badge>
          )}
        </div>

        {/* Right Header Controls */}
        <div className="flex items-center gap-2">
          {/* Share Button */}
          <Button
            variant="secondary"
            size="sm"
            onClick={handleShare}
            leftIcon={
              copiedShare ? (
                <Check className="w-3.5 h-3.5 text-severity-low-fg" />
              ) : (
                <Share2 className="w-3.5 h-3.5 text-muted" />
              )
            }
          >
            {copiedShare ? 'Copied Link!' : 'Share Report'}
          </Button>

          {/* Export JSON */}
          <Button
            variant="ghost"
            size="sm"
            onClick={handleExportJson}
            leftIcon={<Download className="w-3.5 h-3.5 text-muted" />}
            className="hidden sm:inline-flex"
          >
            JSON
          </Button>

          {/* Export HTML / Print */}
          <Button
            variant="ghost"
            size="sm"
            onClick={handlePrintHtml}
            leftIcon={<Printer className="w-3.5 h-3.5 text-muted" />}
            className="hidden md:inline-flex"
          >
            Print
          </Button>

          {/* Re-run Test Button */}
          {onReRun && (
            <Button
              variant="primary"
              size="sm"
              onClick={triggerRerun}
              leftIcon={<RotateCcw className="w-3.5 h-3.5 text-ink" />}
            >
              Re-run this test
            </Button>
          )}

          {/* New Attack / Restart */}
          <Button
            variant="secondary"
            size="sm"
            onClick={onRestart}
            leftIcon={<RefreshCcw className="w-3.5 h-3.5 text-muted" />}
          >
            New Attack
          </Button>
        </div>
      </header>


      {/* ========================================================================= */}
      {/* VIEW 1: THE SCORE OVERVIEW                                                */}
      {/* ========================================================================= */}
      {viewMode === 'score' && (
        <main className="flex-1 max-w-[1200px] w-full mx-auto p-6 md:p-8 flex flex-col gap-6">
          {/* Header Hero Area with Gremlin pose=completion */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-6 bg-surface border border-stone rounded-2xl shadow-card">
            <div className="flex items-center gap-4">
              <Gremlin pose="completion" size="lg" animate={true} />
              <div>
                <h1 className="text-xl md:text-2xl font-extrabold text-ink tracking-tight">
                  Usability Audit Complete
                </h1>
                <p className="text-xs text-muted mt-0.5 max-w-xl leading-relaxed">
                  The gremlin navigated your user flow, uncovered friction points, and generated an evidence-backed usability diagnosis.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <Button
                variant="primary"
                size="md"
                onClick={() => handleViewExplanation(selectedPersona)}
                rightIcon={<ArrowRight className="w-4 h-4 text-ink" />}
              >
                View Detailed Score &amp; Findings
              </Button>
            </div>
          </div>

          {/* Before / After Delta Panel if this was a Re-test */}
          {report?.delta && <BeforeAfterPanel delta={report.delta} />}

          {/* Target and Task Strip */}
          <div className="p-4 rounded-xl bg-surface border border-stone flex flex-col md:flex-row md:items-center justify-between gap-4 text-xs shadow-subtle">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-muted font-bold uppercase tracking-wider shrink-0">Target:</span>
              <CodeChip code={activeReport?.url || report?.url || session.url} />
              <a
                href={activeReport?.url || report?.url || session.url}
                target="_blank"
                rel="noreferrer"
                className="text-gremlin-dark hover:underline flex items-center gap-1 font-semibold"
                title="Open target URL in new tab"
              >
                <ExternalLink className="w-3.5 h-3.5 shrink-0" />
              </a>
            </div>
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-muted font-bold uppercase tracking-wider shrink-0">Task:</span>
              <span className="text-ink font-medium truncate">
                "{activeReport?.task || report?.task || session.task}"
              </span>
            </div>
          </div>

          {/* Error at Beginning Banner & Prompt to Rerun */}
          {isErrorAtBeginning && (
            <Card className="p-6 border-severity-critical-fg/30 bg-severity-critical-bg/30">
              <div className="flex items-start gap-4">
                <div className="w-10 h-10 rounded-xl bg-severity-critical-bg border border-severity-critical-fg/30 flex items-center justify-center text-severity-critical-fg shrink-0">
                  <AlertTriangle className="w-5 h-5" />
                </div>
                <div className="flex-1 space-y-2">
                  <div className="flex items-center gap-2">
                    <Badge variant="critical">Audit Failed at Start</Badge>
                    <span className="text-xs text-muted font-mono">0 steps executed</span>
                  </div>
                  <h3 className="text-base font-bold text-ink">
                    Unable to complete usability test
                  </h3>
                  <p className="text-xs text-muted leading-relaxed">
                    {initialRerunPrompt}
                  </p>
                  <div className="p-3 rounded-lg bg-surface border border-stone font-mono text-xs text-severity-critical-fg">
                    {initialErrorMessage}
                  </div>
                  <div className="pt-2 flex items-center gap-3">
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={triggerRerun}
                      leftIcon={<RotateCcw className="w-4 h-4 text-ink" />}
                    >
                      Rerun Test Now
                    </Button>
                    <Button variant="secondary" size="sm" onClick={onRestart}>
                      Configure Different Target
                    </Button>
                  </div>
                </div>
              </div>
            </Card>
          )}

          {/* System Interrupted Banner */}
          {isSystemInterrupted && (
            <div className="p-4 rounded-xl border border-severity-medium-fg/30 bg-severity-medium-bg/30 text-xs text-ink flex items-start gap-3">
              <Activity className="w-5 h-5 shrink-0 text-severity-medium-fg mt-0.5" />
              <div>
                <span className="font-bold uppercase tracking-wider block text-[11px] text-severity-medium-fg mb-0.5">
                  Audit Interrupted ({outcome === 'timeout' ? 'System Timeout Limit' : 'Infrastructure Error'})
                </span>
                <span className="text-muted leading-relaxed">
                  Testing concluded early at step {totalSteps} due to an infrastructure timeout cap. Usability friction ({currentScore?.total ?? 0}/100) is scored based on signals detected up to this point.
                </span>
              </div>
            </div>
          )}

          {/* The Score Summary Cards (ComparisonSummary) */}
          <ComparisonSummary
            comparison={report?.comparison}
            comparisonSummary={report?.comparison_summary}
            selectedPersona={selectedPersona}
            onSelectPersona={(p) => setSelectedPersona(p)}
            onViewRun={handleViewRun}
            fallbackItem={fallbackComparisonItem}
          />

        </main>
      )}

      {/* ========================================================================= */}
      {/* VIEW 2: SCORE AND EXPLANATION                                             */}
      {/* ========================================================================= */}
      {viewMode === 'explanation' && (
        <main className="flex-1 max-w-[1200px] w-full mx-auto p-6 md:p-8 flex flex-col gap-6">
          {/* Subheader Navigation */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-stone">
            <div className="flex items-center gap-3">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setViewMode('score')}
                leftIcon={<ChevronLeft className="w-4 h-4" />}
              >
                Back to Scores
              </Button>
              <div className="h-4 w-px bg-stone hidden sm:block" />
              <h2 className="text-base font-bold text-ink flex items-center gap-2">
                <span>Score &amp; Explanation</span>
                <span className="text-xs font-mono font-normal px-2.5 py-0.5 rounded-full bg-gremlin/20 border border-gremlin/40 text-ink">
                  {PERSONA_NAMES[selectedPersona] || selectedPersona}
                </span>
              </h2>
            </div>

            <div className="flex items-center gap-2">
              {session.personas && session.personas.length > 1 && (
                <div className="flex flex-wrap gap-1.5 mr-2">
                  {session.personas.map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => setSelectedPersona(p)}
                      className={`px-2.5 py-1 rounded-xl text-xs font-semibold border transition-all cursor-pointer ${
                        selectedPersona === p
                          ? 'bg-gremlin text-ink border-gremlin-dark font-bold shadow-subtle'
                          : 'bg-surface text-muted border-stone hover:border-muted/50 hover:text-ink'
                      }`}
                    >
                      {PERSONA_NAMES[p]?.split(' ')[0] || p}
                    </button>
                  ))}
                </div>
              )}
              <Button
                variant="primary"
                size="sm"
                onClick={() => handleViewRun(selectedPersona)}
                rightIcon={<ArrowRight className="w-4 h-4 text-ink" />}
              >
                View Step Run ({totalSteps} steps)
              </Button>
            </div>
          </div>

          {/* Task Outcome Banner Card */}
          {outcome && (
            <Card className="p-5 border-stone">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] uppercase tracking-wider text-muted font-bold">
                  Task Outcome ({PERSONA_NAMES[selectedPersona]?.split(' ')[0] || selectedPersona})
                </span>
                {claimedOutcome && verifiedOutcome && claimedOutcome !== verifiedOutcome && (
                  <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-canvas text-muted border border-stone">
                    Claimed: {claimedOutcome} · Verified: {verifiedOutcome}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3">
                <Badge variant={outcomeVariant}>{outcome}</Badge>
                {outcomeReason && (
                  <p className="text-xs text-muted leading-relaxed pl-3 border-l-2 border-stone">
                    {outcomeReason}
                  </p>
                )}
              </div>
            </Card>
          )}

          {/* Friction Score Breakdown Card */}
          <Card className="p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs uppercase font-bold text-muted tracking-wider">
                Friction Score Breakdown
              </h3>
              <span className="text-xs text-muted font-mono italic">
                Heuristic score, not a validated metric.
              </span>
            </div>

            {!currentScore ? (
              <p className="text-center text-muted text-sm py-8">Generating report…</p>
            ) : (
              <>
                <div className="flex flex-col sm:flex-row items-center justify-between gap-6 pb-6 border-b border-stone">
                  <div className="flex items-center gap-5">
                    <div className={`text-6xl font-black font-mono tracking-tight ${scoreTextColor}`}>
                      {currentScore.total}
                    </div>
                    <div>
                      <div className="text-sm font-bold text-ink">
                        {currentScore.label} Friction Level
                      </div>
                      <div className="text-xs text-muted mt-0.5 font-mono">
                        {currentScore.steps_taken} steps taken · about {currentScore.ideal_steps} expected
                      </div>
                    </div>
                  </div>

                  {((report?.runs && report.runs > 1) || (currentScore.runs && currentScore.runs > 1)) && (
                    <div className="bg-canvas border border-stone rounded-xl px-4 py-2.5 text-left">
                      <div className="text-sm font-extrabold text-ink font-mono">
                        {report?.score_min ?? currentScore.score_min}–{report?.score_max ?? currentScore.score_max}
                      </div>
                      <div className="text-[11px] text-gremlin-dark font-medium">
                        Consistent across {report?.runs ?? currentScore.runs} runs
                      </div>
                    </div>
                  )}
                </div>

                {/* Plain-Language Verdict */}
                <p className="mt-4 text-sm text-ink leading-relaxed font-medium">
                  {activeReport?.verdict || report?.verdict}
                </p>

                {/* Cognitive Friction Penalties List */}
                <div className="mt-6 space-y-3">
                  <h4 className="text-xs uppercase font-bold text-muted tracking-wider">
                    Cognitive Friction Penalties &amp; Heuristics
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {currentScore.parts?.map((p) => (
                      <div
                        key={p.name}
                        className="p-4 rounded-xl bg-canvas border border-stone flex flex-col justify-between gap-2"
                      >
                        <div>
                          <div className="flex justify-between items-center text-xs font-semibold">
                            <span className="text-ink">{p.name}</span>
                            <span className="text-severity-critical-fg font-mono font-bold">
                              +{p.points} pts
                            </span>
                          </div>
                          <div className="h-1.5 rounded-full bg-stone mt-2 overflow-hidden">
                            <div
                              className="h-1.5 rounded-full bg-severity-critical-fg"
                              style={{ width: `${Math.min(100, p.points * 5)}%` }}
                            />
                          </div>
                          <p className="mt-2 text-xs text-muted leading-relaxed">{p.why}</p>
                        </div>

                        {p.evidence && p.evidence.length > 0 && (
                          <div className="mt-2 pt-2 border-t border-stone/60 flex items-center gap-1.5 flex-wrap">
                            <span className="text-[10px] uppercase font-bold text-muted mr-1">
                              Evidence:
                            </span>
                            {p.evidence.slice(0, 8).map((n) => (
                              <StepChip
                                key={n}
                                step={n}
                                onClick={() => jumpToStep(n)}
                              />
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </Card>

          {/* Usability Findings List */}
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-ink flex items-center gap-2">
                <span>Usability Findings &amp; Defect Highlights</span>
                <span className="text-xs font-mono font-normal px-2.5 py-0.5 rounded-full bg-surface border border-stone text-muted">
                  {currentFindings.length} {currentFindings.length === 1 ? 'Finding' : 'Findings'}
                </span>
              </h3>
            </div>

            {currentFindings.length === 0 ? (
              <div className="p-8 text-center text-muted text-sm bg-surface border border-stone rounded-2xl">
                No critical usability vulnerabilities detected for this persona.
              </div>
            ) : (
              currentFindings.map((f, idx) => (
                <Card key={idx} className="p-6">
                  {/* Card Header */}
                  <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge variant={f.severity}>{f.severity}</Badge>
                      {f.consistency && (
                        <span className="text-[10px] uppercase font-bold font-mono px-2 py-0.5 rounded bg-canvas border border-stone text-muted">
                          {f.consistency}
                        </span>
                      )}
                    </div>

                    {f.evidence_steps && f.evidence_steps.length > 0 ? (
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-[10px] uppercase font-bold text-muted mr-1">
                          Evidence:
                        </span>
                        {f.evidence_steps.map((n) => (
                          <StepChip
                            key={n}
                            step={n}
                            hasFriction
                            severity={f.severity}
                            onClick={() => jumpToStep(n)}
                          />
                        ))}
                      </div>
                    ) : (
                      <div className="flex items-center gap-1 text-[11px] text-severity-medium-fg font-medium">
                        <Info className="w-3.5 h-3.5" />
                        <span>No direct evidence</span>
                      </div>
                    )}
                  </div>

                  {/* Finding Title */}
                  <h4 className="font-bold text-base text-ink mb-2">{f.title}</h4>

                  {/* Description & Impact */}
                  <p className="text-sm text-ink/90 leading-relaxed mb-2">{f.what_happened}</p>
                  <p className="text-xs text-muted leading-relaxed">
                    <strong className="text-ink">Impact:</strong> {f.impact}
                  </p>

                  {/* Selector Block */}
                  {f.selector && (
                    <div className="mt-3">
                      <CodeChip code={f.selector} prefix="SELECTOR" />
                    </div>
                  )}

                  {/* Suggested Fix Block */}
                  {f.suggested_fix ? (
                    <div className="mt-3 p-3 bg-canvas border border-stone rounded-xl font-mono text-xs text-ink whitespace-pre-wrap">
                      <div className="text-[10px] uppercase tracking-wider text-muted font-sans font-bold mb-1">
                        Suggested Fix
                      </div>
                      {f.suggested_fix}
                    </div>
                  ) : (
                    <p className="mt-2 text-xs text-gremlin-dark font-medium">
                      <strong>Fix Recommendation:</strong> {f.recommendation}
                    </p>
                  )}

                  {/* Defect Screenshot with 2px Red Outline */}
                  {f.screenshot && (
                    <div className="mt-4 overflow-hidden rounded-xl border border-stone bg-canvas p-2">
                      <div className="px-3 py-1 text-[10px] uppercase tracking-wider text-muted flex items-center justify-between font-semibold mb-1">
                        <span>
                          Defect Highlight (Step {f.step_number || f.evidence_steps?.[0] || 1})
                        </span>
                        {f.bounding_box && (
                          <span className="font-mono text-[9px]">
                            [{f.bounding_box.width}×{f.bounding_box.height}px]
                          </span>
                        )}
                      </div>
                      <div
                        role="button"
                        tabIndex={0}
                        onClick={() => {
                          const stepNum = f.step_number || f.evidence_steps?.[0];
                          if (stepNum) jumpToStep(stepNum);
                        }}
                        className="cursor-pointer relative overflow-hidden bg-surface p-2 flex items-center justify-center rounded-lg border border-stone"
                        title="Click to jump into Step Replay"
                      >
                        <img
                          src={`data:image/jpeg;base64,${f.screenshot}`}
                          alt={f.title}
                          className="max-h-64 w-full object-contain rounded"
                        />
                      </div>
                    </div>
                  )}
                </Card>
              ))
            )}
          </div>
        </main>
      )}

      {/* ========================================================================= */}
      {/* VIEW 3: STEP-BY-STEP RUN REPLAY                                           */}
      {/* ========================================================================= */}
      {viewMode === 'run' && (
        <div className="flex-1 flex flex-col bg-canvas overflow-hidden">
          {/* Top Bar for Step Replay */}
          <div className="h-14 border-b border-stone bg-surface px-6 flex items-center justify-between shrink-0 gap-4 z-10 shadow-subtle">
            <div className="flex items-center gap-3">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setViewMode('score')}
                leftIcon={<ChevronLeft className="w-4 h-4" />}
              >
                Scores
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setViewMode('explanation')}
                leftIcon={<FileText className="w-3.5 h-3.5 text-muted" />}
              >
                Score &amp; Explanation
              </Button>
              <div className="h-4 w-px bg-stone hidden sm:block" />
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted font-bold uppercase tracking-wider hidden sm:inline">
                  Persona:
                </span>
                <span className="text-xs text-ink font-semibold font-mono">
                  {PERSONA_NAMES[selectedPersona] || selectedPersona}
                </span>
              </div>
            </div>

            {/* Persona Switcher & Scrubber Controls */}
            <div className="flex items-center gap-3">
              {session.personas && session.personas.length > 1 && (
                <div className="flex flex-wrap gap-1 mr-2">
                  {session.personas.map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => {
                        setSelectedPersona(p);
                        setCurrentIndex(0);
                      }}
                      className={`px-2.5 py-1 rounded-xl text-xs font-semibold border transition-all cursor-pointer ${
                        selectedPersona === p
                          ? 'bg-gremlin text-ink border-gremlin-dark font-bold shadow-subtle'
                          : 'bg-surface text-muted border-stone hover:border-muted/50 hover:text-ink'
                      }`}
                    >
                      {PERSONA_NAMES[p]?.split(' ')[0] || p}
                    </button>
                  ))}
                </div>
              )}

              <span className="text-xs font-mono font-semibold text-ink">
                Step {totalSteps > 0 ? currentIndex + 1 : 0} of {totalSteps}
              </span>

              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={handlePrev}
                  disabled={currentIndex === 0}
                  className="p-1.5 rounded-lg bg-surface border border-stone hover:bg-stone/30 disabled:opacity-40 text-ink transition cursor-pointer"
                  title="Previous Step (Left Arrow)"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  onClick={handleNext}
                  disabled={currentIndex >= totalSteps - 1}
                  className="p-1.5 rounded-lg bg-surface border border-stone hover:bg-stone/30 disabled:opacity-40 text-ink transition cursor-pointer"
                  title="Next Step (Right Arrow)"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
                <span className="hidden sm:inline-block px-1.5 py-0.5 rounded text-[10px] font-mono text-muted border border-stone bg-canvas">
                  ← →
                </span>
              </div>
            </div>
          </div>

          {/* Step Timeline Strip */}
          {totalSteps > 1 && (
            <div className="px-6 py-2 bg-canvas border-b border-stone flex items-center gap-1.5 overflow-x-auto shrink-0">
              <span className="text-[10px] uppercase font-bold text-muted mr-2 shrink-0">
                Timeline:
              </span>
              {slideshowItems.map((item, idx) => {
                const hasFriction = Boolean(
                  ('friction_note' in item && item.friction_note) ||
                  ('friction_type' in item && item.friction_type)
                );
                return (
                  <StepChip
                    key={idx}
                    step={idx + 1}
                    active={currentIndex === idx}
                    hasFriction={hasFriction}
                    onClick={() => setCurrentIndex(idx)}
                  />
                );
              })}
            </div>
          )}

          {/* Screenshot Canvas & Thought Console */}
          <div className="flex-1 min-h-0 p-4 md:p-6 flex flex-col lg:flex-row gap-6 overflow-hidden">
            {/* Left: Screenshot in Browser Frame */}
            <div className="flex-1 lg:flex-[0.65] flex flex-col min-h-0 bg-surface border border-stone rounded-2xl shadow-card overflow-hidden">
              <div className="h-10 px-4 border-b border-stone bg-canvas/40 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-stone" />
                  <span className="w-2.5 h-2.5 rounded-full bg-stone" />
                  <span className="w-2.5 h-2.5 rounded-full bg-stone" />
                </div>
                <span className="font-mono text-xs text-muted">
                  Step {currentIndex + 1} of {totalSteps}
                </span>
                <div className="w-4" />
              </div>

              <div className="flex-1 min-h-0 p-4 bg-canvas/20 flex items-center justify-center relative overflow-hidden">
                {currentItem?.screenshot ? (
                  <img
                    src={`data:image/jpeg;base64,${currentItem.screenshot}`}
                    alt={`Step ${currentIndex + 1} screenshot`}
                    className="max-h-full max-w-full object-contain rounded-xl border border-stone shadow-card bg-surface"
                  />
                ) : (
                  <div className="text-muted text-xs font-mono">
                    No screenshot recorded for this step
                  </div>
                )}
              </div>
            </div>

            {/* Right: Thought Console & Observations */}
            <div className="flex-1 lg:flex-[0.35] flex flex-col min-h-0">
              <TerminalPanel
                entries={[
                  currentItem?.thought || 'No thought recorded for this step.',
                  ...(('friction_note' in currentItem && currentItem.friction_note)
                    ? [`[Friction Detected] ${currentItem.friction_note}`]
                    : []),
                ]}
                title={`Step ${currentIndex + 1} Cognitive Decision`}
                className="flex-1 min-h-0"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
