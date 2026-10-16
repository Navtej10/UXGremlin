import { useEffect, useState } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  RefreshCcw,
  ShieldAlert,
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
} from 'lucide-react';
import { ComparisonSummary, type ComparisonItem } from './ComparisonSummary';
import { BeforeAfterPanel, type ReportDelta } from './BeforeAfterPanel';

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

const OUTCOME_CONFIG: Record<
  string,
  { label: string; bg: string; border: string; text: string; dot: string }
> = {
  completed: {
    label: 'Completed',
    bg: 'bg-emerald-950/60',
    border: 'border-emerald-500/50',
    text: 'text-emerald-400',
    dot: 'bg-emerald-400',
  },
  abandoned: {
    label: 'Abandoned',
    bg: 'bg-amber-950/60',
    border: 'border-amber-500/50',
    text: 'text-amber-400',
    dot: 'bg-amber-400',
  },
  gave_up: {
    label: 'Gave Up',
    bg: 'bg-rose-950/60',
    border: 'border-rose-500/50',
    text: 'text-rose-400',
    dot: 'bg-rose-400',
  },
  max_steps_reached: {
    label: 'Max Steps Reached',
    bg: 'bg-amber-950/60',
    border: 'border-amber-500/50',
    text: 'text-amber-400',
    dot: 'bg-amber-400',
  },
  error: {
    label: 'Execution Error',
    bg: 'bg-rose-950/60',
    border: 'border-rose-500/50',
    text: 'text-rose-400',
    dot: 'bg-rose-400',
  },
  timeout: {
    label: 'Audit Timeout (System Cap)',
    bg: 'bg-amber-950/60',
    border: 'border-amber-500/50',
    text: 'text-amber-400',
    dot: 'bg-amber-400',
  },
  system_error: {
    label: 'System Error (Interrupted)',
    bg: 'bg-purple-950/60',
    border: 'border-purple-500/50',
    text: 'text-purple-400',
    dot: 'bg-purple-400',
  },
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
  const scoreColor =
    total <= 20
      ? 'text-gremlin-green'
      : total <= 45
      ? 'text-amber-400'
      : total <= 70
      ? 'text-orange-400'
      : 'text-red-500';

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
    ((outcome === 'error' || report?.outcome === 'error') && totalSteps === 0 && (report?.error || activeReport?.error || outcomeReason))
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

  return (
    <div className="h-screen w-screen flex flex-col bg-bg-dark text-white overflow-hidden">
      {/* Universal Top Header */}
      <div className="h-16 border-b border-gray-800 flex items-center justify-between px-6 bg-bg-card shrink-0 gap-4 z-20">
        <div className="flex items-center gap-3">
          <ShieldAlert className="text-gremlin-purple w-6 h-6 shrink-0" />
          <h1
            onClick={() => setViewMode('score')}
            className="text-xl font-bold uppercase tracking-widest text-transparent bg-clip-text bg-gradient-to-r from-gremlin-purple to-gremlin-green cursor-pointer select-none"
            title="Return to Usability Score overview"
          >
            Sabotage Report
          </h1>
          {isReadOnly && (
            <span className="text-[11px] font-mono px-2.5 py-0.5 rounded bg-gremlin-purple/20 text-purple-300 border border-gremlin-purple/40">
              Archived Report
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Share Button */}
          <button
            onClick={handleShare}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-xs font-semibold rounded-lg border border-gray-700 text-gray-200 transition-colors cursor-pointer"
            title="Copy shareable report link"
          >
            {copiedShare ? (
              <>
                <Check className="w-3.5 h-3.5 text-gremlin-green" />
                <span className="text-gremlin-green">Copied!</span>
              </>
            ) : (
              <>
                <Share2 className="w-3.5 h-3.5 text-gray-400" />
                <span>Share</span>
              </>
            )}
          </button>

          {/* Export JSON Button */}
          <button
            onClick={handleExportJson}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-xs font-semibold rounded-lg border border-gray-700 text-gray-200 transition-colors cursor-pointer"
            title="Download JSON report payload"
          >
            <Download className="w-3.5 h-3.5 text-gray-400" />
            <span>Export JSON</span>
          </button>

          {/* Print / PDF Button */}
          <button
            onClick={handlePrintHtml}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-xs font-semibold rounded-lg border border-gray-700 text-gray-200 transition-colors cursor-pointer"
            title="Print or save as PDF"
          >
            <Printer className="w-3.5 h-3.5 text-gray-400" />
            <span>Print / PDF</span>
          </button>

          {/* Re-run Test Button */}
          {onReRun && (
            <button
              onClick={() => {
                const targetSessionId = report?.session_id || session.session_id;
                if (!targetSessionId) return;
                onReRun({
                  url: report?.url || session.url,
                  task: report?.task || session.task,
                  persona: selectedPersona || session.persona,
                  personas: report?.personas || session.personas,
                  previous_session_id: targetSessionId,
                });
              }}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-gremlin-purple hover:bg-purple-600 text-xs font-bold rounded-lg text-white shadow-sm transition-all cursor-pointer"
              title="Re-run this test and link to previous session"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Re-run this test</span>
            </button>
          )}

          {/* New Attack / Restart Button */}
          <button
            onClick={onRestart}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-xs font-semibold rounded-lg text-gray-300 transition-colors cursor-pointer"
          >
            <RefreshCcw className="w-3.5 h-3.5" />
            <span>New Attack</span>
          </button>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* PAGE 1: THE SCORE OVERVIEW (1)                                            */}
      {/* (Part 2 is accessible via button; Part 3 is accessed only via 'View Run') */}
      {/* ========================================================================= */}
      {viewMode === 'score' && (
        <div className="flex-1 overflow-y-auto p-6 md:p-8 bg-bg-dark">
          <div className="max-w-5xl mx-auto flex flex-col gap-6">
            {/* Before / After Delta Panel if this was a Re-test */}
            {report?.delta && (
              <div className="border border-gray-800 bg-black/60 rounded-2xl p-5 shadow-lg">
                <BeforeAfterPanel delta={report.delta} />
              </div>
            )}

            {/* Target and Task Hero Strip */}
            <div className="p-4 rounded-xl bg-black/40 border border-gray-800 flex flex-col md:flex-row md:items-center justify-between gap-4 text-xs">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-gray-400 font-bold uppercase tracking-wider shrink-0">Target:</span>
                <a
                  href={activeReport?.url || report?.url || session.url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-mono text-gremlin-green hover:underline flex items-center gap-1 text-sm font-semibold truncate"
                >
                  <span className="truncate">{activeReport?.url || report?.url || session.url}</span>
                  <ExternalLink className="w-3.5 h-3.5 shrink-0" />
                </a>
              </div>
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-gray-400 font-bold uppercase tracking-wider shrink-0">Task:</span>
                <span className="text-gray-200 text-sm italic font-medium truncate">
                  "{activeReport?.task || report?.task || session.task}"
                </span>
              </div>
            </div>

            {/* Error at Beginning Banner & Prompt to Rerun */}
            {isErrorAtBeginning && (
              <div className="p-6 rounded-2xl border border-rose-500/50 bg-gradient-to-br from-rose-950/70 via-black/90 to-bg-card shadow-[0_0_35px_rgba(244,63,94,0.18)] flex flex-col gap-4">
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-xl bg-rose-950/90 border border-rose-500/60 flex items-center justify-center text-rose-400 shrink-0 shadow-lg">
                    <AlertTriangle className="w-6 h-6 animate-pulse" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs uppercase font-extrabold tracking-wider px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40">
                        Audit Failed at Start
                      </span>
                      <span className="text-xs text-gray-400 font-mono">0 steps executed</span>
                    </div>
                    <h3 className="text-lg font-bold text-white mt-1">
                      Unable to Start Usability Test
                    </h3>
                    <p className="text-xs text-gray-300 mt-1 leading-relaxed">
                      {initialRerunPrompt}
                    </p>
                  </div>
                </div>

                {/* Stated Error Box */}
                <div className="p-4 rounded-xl bg-black/90 border border-rose-500/30 font-mono text-xs text-rose-300 space-y-1">
                  <div className="text-[10px] uppercase font-bold text-gray-400 font-sans tracking-wider">
                    Stated Error Details
                  </div>
                  <div className="break-all">{initialErrorMessage}</div>
                </div>

                {/* Prompt to Rerun Actions */}
                <div className="flex flex-wrap items-center gap-3 pt-1">
                  <button
                    onClick={triggerRerun}
                    className="px-5 py-2.5 bg-gradient-to-r from-gremlin-purple to-purple-600 hover:from-purple-600 hover:to-gremlin-purple text-white text-xs font-bold rounded-xl shadow-lg transition-all flex items-center gap-2 cursor-pointer"
                  >
                    <RotateCcw className="w-4 h-4" />
                    <span>Rerun Test Now</span>
                  </button>

                  <button
                    onClick={onRestart}
                    className="px-4 py-2.5 bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs font-semibold rounded-xl border border-gray-700 transition cursor-pointer"
                  >
                    Configure Different Target / Task
                  </button>
                </div>
              </div>
            )}

            {/* System Interrupted Banner (Timeout / System Error) */}
            {isSystemInterrupted && (
              <div className="p-4 rounded-xl border border-amber-500/40 bg-amber-950/30 text-amber-300 text-xs flex items-start gap-3 shadow-lg">
                <Activity className="w-5 h-5 shrink-0 text-amber-400 mt-0.5" />
                <div>
                  <span className="font-bold uppercase tracking-wider block text-[11px] text-amber-400 mb-0.5">
                    Audit Interrupted ({outcome === 'timeout' ? 'System Timeout Limit' : 'Infrastructure Error'}) · Usability Score Up to Step {totalSteps}
                  </span>
                  <span className="text-gray-300">
                    Testing concluded early at step {totalSteps} due to an infrastructure {outcome === 'timeout' ? 'timeout cap' : 'error'}. Usability friction ({currentScore?.total ?? 0}/100) is scored strictly based on heuristic findings and signals detected up to this point without penalizing the target application with a task failure penalty.
                  </span>
                </div>
              </div>
            )}

            {/* The Score Summary Cards (1) */}
            <ComparisonSummary
              comparison={report?.comparison}
              comparisonSummary={report?.comparison_summary}
              selectedPersona={selectedPersona}
              onSelectPersona={(p) => {
                setSelectedPersona(p);
              }}
              onViewRun={handleViewRun}
              fallbackItem={fallbackComparisonItem}
            />

            {/* Action Card to Proceed to (2): Score & Explanation */}
            <div className="w-full bg-gradient-to-r from-purple-950/40 via-bg-card to-gray-900 border border-gremlin-purple/30 rounded-2xl p-6 flex flex-col sm:flex-row items-center justify-between gap-5 shadow-[0_0_30px_rgba(157,0,255,0.1)]">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-gremlin-purple/20 border border-gremlin-purple/40 flex items-center justify-center text-gremlin-green shrink-0">
                  <FileText className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    Detailed Score Breakdown & Explanation
                  </h3>
                  <p className="text-xs text-gray-400 mt-1 max-w-xl leading-relaxed">
                    Explore the heuristic friction penalty breakdown, cognitive friction drivers, verified task outcomes, and prioritized usability findings with suggested code fixes.
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3 w-full sm:w-auto shrink-0">
                <button
                  onClick={() => handleViewExplanation(selectedPersona)}
                  className="w-full sm:w-auto px-5 py-2.5 bg-gradient-to-r from-gremlin-purple to-purple-600 hover:from-purple-600 hover:to-gremlin-purple text-white text-xs font-bold rounded-xl shadow-lg transition-all flex items-center justify-center gap-2 cursor-pointer"
                >
                  <span>View Score & Explanation</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* PAGE 2: SCORE AND EXPLANATION (2)                                         */}
      {/* (Accessible after (1); displays outcome, score breakdown, findings)       */}
      {/* ========================================================================= */}
      {viewMode === 'explanation' && (
        <div className="flex-1 overflow-y-auto p-6 md:p-8 bg-bg-dark">
          <div className="max-w-5xl mx-auto flex flex-col gap-6">
            {/* Navigation Subheader */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-gray-800">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setViewMode('score')}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-xs font-semibold rounded-lg border border-gray-700 text-gray-200 transition-colors cursor-pointer"
                >
                  <ChevronLeft className="w-4 h-4" />
                  <span>Back to Scores</span>
                </button>
                <div className="h-4 w-[1px] bg-gray-800 hidden sm:block" />
                <h2 className="text-base font-bold text-white flex items-center gap-2">
                  <span>Score & Explanation</span>
                  <span className="text-xs font-mono font-normal px-2.5 py-0.5 rounded-full bg-gremlin-purple/20 border border-gremlin-purple/40 text-purple-300">
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
                        onClick={() => setSelectedPersona(p)}
                        className={`px-2.5 py-1 rounded text-xs font-semibold border transition-all cursor-pointer ${
                          selectedPersona === p
                            ? 'bg-gremlin-purple text-white border-gremlin-purple shadow-sm'
                            : 'bg-black/40 text-gray-400 border-gray-800 hover:border-gray-700 hover:text-white'
                        }`}
                      >
                        {PERSONA_NAMES[p]?.split(' ')[0] || p}
                      </button>
                    ))}
                  </div>
                )}
                <button
                  onClick={() => handleViewRun(selectedPersona)}
                  className="flex items-center gap-1.5 px-3.5 py-1.5 bg-gremlin-purple/30 hover:bg-gremlin-purple/50 text-xs font-bold rounded-lg border border-gremlin-purple/50 text-purple-200 hover:text-white transition-all cursor-pointer shadow-sm"
                  title="View step-by-step browser run"
                >
                  <span>View Run ({totalSteps} steps)</span>
                  <ArrowRight className="w-3.5 h-3.5 text-gremlin-green" />
                </button>
              </div>
            </div>

            {/* Target and Task Summary */}
            <div className="p-4 rounded-xl bg-black/40 border border-gray-800 grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
              <div>
                <span className="text-gray-400 font-bold uppercase tracking-wider block mb-1">Target URL</span>
                <a
                  href={activeReport?.url || report?.url || session.url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-mono text-gremlin-green hover:underline flex items-center gap-1 text-sm font-semibold truncate"
                >
                  <span className="truncate">{activeReport?.url || report?.url || session.url}</span>
                  <ExternalLink className="w-3 h-3 shrink-0" />
                </a>
              </div>
              <div>
                <span className="text-gray-400 font-bold uppercase tracking-wider block mb-1">Audited Task</span>
                <span className="text-gray-200 text-sm italic font-medium block">
                  "{activeReport?.task || report?.task || session.task}"
                </span>
              </div>
            </div>

            {/* Error at Beginning Banner & Prompt to Rerun */}
            {isErrorAtBeginning && (
              <div className="p-6 rounded-2xl border border-rose-500/50 bg-gradient-to-br from-rose-950/70 via-black/90 to-bg-card shadow-[0_0_35px_rgba(244,63,94,0.18)] flex flex-col gap-4">
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-xl bg-rose-950/90 border border-rose-500/60 flex items-center justify-center text-rose-400 shrink-0 shadow-lg">
                    <AlertTriangle className="w-6 h-6 animate-pulse" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs uppercase font-extrabold tracking-wider px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40">
                        Audit Failed at Start
                      </span>
                      <span className="text-xs text-gray-400 font-mono">0 steps executed</span>
                    </div>
                    <h3 className="text-lg font-bold text-white mt-1">
                      Unable to Start Usability Test
                    </h3>
                    <p className="text-xs text-gray-300 mt-1 leading-relaxed">
                      {initialRerunPrompt}
                    </p>
                  </div>
                </div>

                {/* Stated Error Box */}
                <div className="p-4 rounded-xl bg-black/90 border border-rose-500/30 font-mono text-xs text-rose-300 space-y-1">
                  <div className="text-[10px] uppercase font-bold text-gray-400 font-sans tracking-wider">
                    Stated Error Details
                  </div>
                  <div className="break-all">{initialErrorMessage}</div>
                </div>

                {/* Prompt to Rerun Actions */}
                <div className="flex flex-wrap items-center gap-3 pt-1">
                  <button
                    onClick={triggerRerun}
                    className="px-5 py-2.5 bg-gradient-to-r from-gremlin-purple to-purple-600 hover:from-purple-600 hover:to-gremlin-purple text-white text-xs font-bold rounded-xl shadow-lg transition-all flex items-center gap-2 cursor-pointer"
                  >
                    <RotateCcw className="w-4 h-4" />
                    <span>Rerun Test Now</span>
                  </button>

                  <button
                    onClick={onRestart}
                    className="px-4 py-2.5 bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs font-semibold rounded-xl border border-gray-700 transition cursor-pointer"
                  >
                    Configure Different Target / Task
                  </button>
                </div>
              </div>
            )}

            {/* System Interrupted Banner (Timeout / System Error) */}
            {isSystemInterrupted && (
              <div className="p-4 rounded-xl border border-amber-500/40 bg-amber-950/30 text-amber-300 text-xs flex items-start gap-3 shadow-lg">
                <Activity className="w-5 h-5 shrink-0 text-amber-400 mt-0.5" />
                <div>
                  <span className="font-bold uppercase tracking-wider block text-[11px] text-amber-400 mb-0.5">
                    Audit Interrupted ({outcome === 'timeout' ? 'System Timeout Limit' : 'Infrastructure Error'}) · Usability Score Up to Step {totalSteps}
                  </span>
                  <span className="text-gray-300">
                    Testing concluded early at step {totalSteps} due to an infrastructure {outcome === 'timeout' ? 'timeout cap' : 'error'}. Usability friction ({currentScore?.total ?? 0}/100) is scored strictly based on heuristic findings and signals detected up to this point without penalizing the target application with a task failure penalty.
                  </span>
                </div>
              </div>
            )}

            {/* Task Outcome Banner */}
            {outcome && (
              <div
                className={`p-5 rounded-2xl border ${
                  OUTCOME_CONFIG[outcome]?.bg ?? 'bg-gray-800/60'
                } ${
                  OUTCOME_CONFIG[outcome]?.border ?? 'border-gray-700'
                } shadow-lg flex flex-col gap-2.5`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[11px] uppercase tracking-wider text-gray-400 font-bold">
                    Task Outcome ({PERSONA_NAMES[selectedPersona]?.split(' ')[0] || selectedPersona})
                  </span>
                  {claimedOutcome &&
                    verifiedOutcome &&
                    claimedOutcome !== verifiedOutcome && (
                      <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-black/60 text-amber-300 border border-amber-500/30">
                        Claimed: {claimedOutcome} · Verified: {verifiedOutcome}
                      </span>
                    )}
                </div>
                <div className="flex items-center gap-2.5">
                  <span
                    className={`w-3 h-3 rounded-full ${
                      OUTCOME_CONFIG[outcome]?.dot ?? 'bg-gray-400'
                    } animate-pulse`}
                  />
                  <span
                    className={`text-xl font-extrabold tracking-wide uppercase ${
                      OUTCOME_CONFIG[outcome]?.text ?? 'text-white'
                    }`}
                  >
                    {OUTCOME_CONFIG[outcome]?.label ?? outcome}
                  </span>
                </div>
                {outcomeReason && (
                  <p className="text-xs text-gray-300 leading-relaxed pl-3 border-l-2 border-white/20 mt-1">
                    {outcomeReason}
                  </p>
                )}
              </div>
            )}

            {/* Baseline Warning */}
            {(activeReport?.baseline_failed || report?.baseline_failed) && (
              <div className="p-4 rounded-xl border border-amber-500/50 bg-amber-950/40 text-amber-300 text-xs flex items-start gap-3 shadow-lg">
                <ShieldAlert className="w-5 h-5 shrink-0 text-amber-400 mt-0.5" />
                <div>
                  <span className="font-bold uppercase tracking-wider block text-[11px] text-amber-400 mb-0.5">
                    Baseline Warning
                  </span>
                  <span>
                    Task may be unreachable or unclear: direct baseline agent failed to achieve completion. Friction score fell back to heuristic step budget.
                  </span>
                </div>
              </div>
            )}

            {/* Friction Score & Score Parts Breakdown */}
            <div className="p-6 bg-black/40 border border-gray-800 rounded-2xl shadow-lg">
              <h2 className="text-gray-400 text-sm uppercase tracking-wider mb-4 font-bold flex items-center justify-between">
                <span>Friction Score Breakdown</span>
                <span className="text-xs font-mono font-normal text-gray-400">
                  {PERSONA_NAMES[selectedPersona] || selectedPersona}
                </span>
              </h2>

              {!currentScore ? (
                <p className="text-center text-gray-500 text-sm py-8">Generating report…</p>
              ) : (
                <>
                  <div className="flex flex-col sm:flex-row items-center justify-between gap-6 pb-6 border-b border-gray-800/80">
                    <div className="flex items-center gap-5">
                      <div className={`text-6xl font-black font-mono tracking-tight ${scoreColor}`}>
                        {currentScore.total}
                      </div>
                      <div>
                        <div className="text-sm font-bold text-white">
                          {currentScore.label} Friction
                        </div>
                        <div className="text-xs text-gray-400 mt-0.5">
                          {currentScore.steps_taken} steps taken · about {currentScore.ideal_steps} expected
                          {activeReport?.baseline_failed || report?.baseline_failed ? ' (heuristic fallback)' : ''}
                        </div>
                      </div>
                    </div>

                    {((report?.runs && report.runs > 1) || (currentScore.runs && currentScore.runs > 1)) && (
                      <div className="text-left bg-gray-900/90 border border-gray-700/70 rounded-xl px-4 py-2 shadow-sm">
                        <div className="text-sm font-extrabold text-white tracking-wide">
                          {report?.score_min ?? currentScore.score_min}–{report?.score_max ?? currentScore.score_max}
                        </div>
                        <div className="text-[11px] text-gremlin-green font-medium">
                          consistent across {report?.runs ?? currentScore.runs} runs
                        </div>
                      </div>
                    )}
                  </div>

                  <p className="mt-4 text-sm text-gray-300 leading-relaxed font-medium">
                    {activeReport?.verdict || report?.verdict}
                  </p>

                  <div className="mt-6 space-y-4">
                    <h3 className="text-xs uppercase font-bold text-gray-400 tracking-wider">
                      Cognitive Friction Penalties & Heuristics
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {currentScore.parts?.map((p) => (
                        <div key={p.name} className="p-4 rounded-xl bg-gray-900/60 border border-gray-800/80 flex flex-col justify-between">
                          <div>
                            <div className="flex justify-between items-center text-sm font-semibold">
                              <span className="text-gray-200">{p.name}</span>
                              <span className="text-rose-400 font-mono">+{p.points} pts</span>
                            </div>
                            <div className="h-1.5 rounded-full bg-gray-800 mt-2 overflow-hidden">
                              <div
                                className="h-1.5 rounded-full bg-red-500"
                                style={{ width: `${Math.min(100, p.points * 5)}%` }}
                              />
                            </div>
                            <p className="mt-2 text-xs text-gray-400 leading-relaxed">{p.why}</p>
                          </div>
                          {p.evidence && p.evidence.length > 0 && (
                            <div className="mt-3 pt-2.5 border-t border-gray-800/60 flex items-center gap-1.5 flex-wrap">
                              <span className="text-[10px] uppercase font-bold text-gray-500 mr-1">Steps:</span>
                              {p.evidence.slice(0, 8).map((n) => (
                                <button
                                  key={n}
                                  onClick={() => jumpToStep(n)}
                                  className="px-2 py-0.5 text-xs font-mono font-semibold rounded bg-gray-800 hover:bg-gremlin-purple hover:text-white text-gray-300 transition-colors cursor-pointer"
                                  title={`Inspect Step ${n}`}
                                >
                                  step {n}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>

                  {selectedPersona === 'pro_tester' && (
                    <div className="mt-5 pt-4 border-t border-gray-800/80 flex items-center justify-between text-xs">
                      <span className="text-gray-400 font-medium">Automated QA Defects Flagged:</span>
                      <span className="font-bold text-gremlin-green text-sm font-mono">
                        {activeReport?.bugs ?? report?.bugs ?? 0} defects
                      </span>
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Usability Findings & Defect Highlights */}
            <div className="flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <span>Usability Findings & Defect Highlights</span>
                  <span className="text-xs font-mono font-normal px-2.5 py-0.5 rounded-full bg-gray-800 text-gray-300 border border-gray-700">
                    {currentFindings.length} {currentFindings.length === 1 ? 'Finding' : 'Findings'}
                  </span>
                </h3>
              </div>

              {currentFindings.length === 0 ? (
                <div className="p-8 text-center text-gray-500 text-sm bg-black/40 border border-gray-800 rounded-2xl">
                  No critical usability vulnerabilities detected for this persona.
                </div>
              ) : (
                currentFindings.map((f) => (
                  <div key={f.title} className="p-6 bg-black/40 border border-gray-800 rounded-2xl shadow-lg">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <h4 className="font-bold text-base text-white">{f.title}</h4>
                      <div className="flex items-center gap-2">
                        {f.consistency && (
                          <span
                            className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded border ${
                              f.consistency === 'consistent'
                                ? 'bg-emerald-950/80 text-emerald-400 border-emerald-500/40'
                                : 'bg-gray-800/80 text-gray-400 border-gray-700'
                            }`}
                          >
                            {f.consistency}
                          </span>
                        )}
                        <span className={`text-xs uppercase font-extrabold px-2 py-0.5 rounded border ${
                          f.severity === 'critical'
                            ? 'bg-rose-950/80 text-rose-400 border-rose-500/50'
                            : f.severity === 'high'
                            ? 'bg-amber-950/80 text-amber-400 border-amber-500/50'
                            : 'bg-blue-950/80 text-blue-400 border-blue-500/50'
                        }`}>
                          {f.severity}
                        </span>
                      </div>
                    </div>

                    <p className="mt-3 text-sm text-gray-300 leading-relaxed">{f.what_happened}</p>
                    <p className="mt-1.5 text-xs text-gray-400">
                      <strong className="text-gray-300">Impact:</strong> {f.impact}
                    </p>

                    {f.suggested_fix ? (
                      <div className="mt-3 p-3 bg-black/80 border border-emerald-500/30 rounded-xl font-mono text-xs text-gremlin-green whitespace-pre-wrap shadow-inner">
                        <div className="text-[10px] uppercase tracking-wider text-gray-400 font-sans font-bold mb-1.5 flex items-center justify-between">
                          <span>Suggested Fix</span>
                          {f.selector && <span className="text-gray-500 font-mono text-[10px] lowercase">{f.selector}</span>}
                        </div>
                        {f.suggested_fix}
                      </div>
                    ) : (
                      <p className="mt-2 text-xs text-gremlin-green">
                        <strong>Fix Recommendation:</strong> {f.recommendation}
                      </p>
                    )}

                    {f.screenshot && (
                      <div className="mt-4 overflow-hidden rounded-xl border border-red-500/40 bg-black/90 shadow-md">
                        <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-red-400 bg-red-950/40 border-b border-red-500/20 flex items-center justify-between font-semibold">
                          <span>Defect Highlight (Step {f.step_number || (f.evidence_steps && f.evidence_steps[0]) || 1})</span>
                          {f.bounding_box && (
                            <span className="text-gray-400 font-mono text-[9px]">
                              [{f.bounding_box.width}×{f.bounding_box.height}px]
                            </span>
                          )}
                        </div>
                        <div
                          className="cursor-pointer group relative overflow-hidden bg-gray-950/90 p-2 flex items-center justify-center"
                          onClick={() => {
                            const stepNum = f.step_number || (f.evidence_steps && f.evidence_steps[0]);
                            if (stepNum) jumpToStep(stepNum);
                          }}
                          title="Click to jump into Step Replay at this step"
                        >
                          <img
                            src={`data:image/jpeg;base64,${f.screenshot}`}
                            alt={f.title}
                            className="max-h-64 w-full object-contain rounded transition group-hover:scale-[1.01]"
                          />
                        </div>
                      </div>
                    )}

                    {f.evidence_steps && f.evidence_steps.length > 0 && (
                      <div className="mt-3.5 flex items-center gap-1.5 flex-wrap">
                        <span className="text-[10px] uppercase font-bold text-gray-500 mr-1">Evidence Steps:</span>
                        {f.evidence_steps.map((n) => (
                          <button
                            key={n}
                            onClick={() => jumpToStep(n)}
                            className="px-2.5 py-0.5 text-xs font-mono font-semibold rounded bg-gray-800 hover:bg-gremlin-purple hover:text-white text-gray-300 transition cursor-pointer"
                          >
                            step {n}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>

            {/* Bottom Actions */}
            <div className="pt-4 border-t border-gray-800 flex items-center justify-between">
              <button
                onClick={() => setViewMode('score')}
                className="flex items-center gap-1.5 px-4 py-2 bg-gray-800 hover:bg-gray-700 text-xs font-semibold rounded-xl border border-gray-700 text-gray-200 transition cursor-pointer"
              >
                <ChevronLeft className="w-4 h-4" />
                <span>Back to Usability Score</span>
              </button>
              <button
                onClick={() => handleViewRun(selectedPersona)}
                className="flex items-center gap-2 px-5 py-2.5 bg-gremlin-purple hover:bg-purple-600 text-xs font-bold rounded-xl text-white shadow-lg transition cursor-pointer"
              >
                <span>View Step-by-Step Run ({totalSteps} steps)</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* PAGE 3: THE STEPS / RUN REPLAY (3)                                        */}
      {/* (Accessible ONLY when user clicks 'View Run' in (1) or an evidence step)  */}
      {/* ========================================================================= */}
      {viewMode === 'run' && (
        <div className="flex-1 flex flex-col bg-bg-dark overflow-hidden">
          {/* Top Bar for Step Replay */}
          <div className="h-14 border-b border-gray-800 bg-bg-card px-6 flex items-center justify-between shrink-0 gap-4 z-10">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setViewMode('score')}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-xs font-semibold rounded-lg border border-gray-700 text-gray-200 transition-colors cursor-pointer"
                title="Return to Score Overview"
              >
                <ChevronLeft className="w-4 h-4" />
                <span>Scores</span>
              </button>
              <button
                onClick={() => setViewMode('explanation')}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-xs font-semibold rounded-lg border border-gray-700 text-gray-200 transition-colors cursor-pointer"
                title="Go to Score & Explanation"
              >
                <FileText className="w-3.5 h-3.5 text-gray-400" />
                <span>Score & Explanation</span>
              </button>
              <div className="h-4 w-[1px] bg-gray-800 hidden sm:block" />
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400 font-bold uppercase tracking-wider hidden sm:inline">Persona:</span>
                <span className="text-xs text-gremlin-purple font-semibold font-mono">
                  {PERSONA_NAMES[selectedPersona] || selectedPersona}
                </span>
              </div>
            </div>

            {/* Persona Switcher & Controls */}
            <div className="flex items-center gap-3">
              {session.personas && session.personas.length > 1 && (
                <div className="flex flex-wrap gap-1 mr-2">
                  {session.personas.map((p) => (
                    <button
                      key={p}
                      onClick={() => {
                        setSelectedPersona(p);
                        setCurrentIndex(0);
                      }}
                      className={`px-2.5 py-1 rounded text-xs font-semibold border transition-all cursor-pointer ${
                        selectedPersona === p
                          ? 'bg-gremlin-purple text-white border-gremlin-purple shadow-sm'
                          : 'bg-black/40 text-gray-400 border-gray-800 hover:border-gray-700 hover:text-white'
                      }`}
                    >
                      {PERSONA_NAMES[p]?.split(' ')[0] || p}
                    </button>
                  ))}
                </div>
              )}

              <span className="text-xs font-mono font-semibold text-gray-300">
                Step {totalSteps > 0 ? currentIndex + 1 : 0} of {totalSteps}
              </span>

              <div className="flex items-center gap-1.5">
                <button
                  onClick={handlePrev}
                  disabled={currentIndex === 0}
                  className="p-1.5 rounded-lg bg-gray-800 disabled:opacity-40 hover:bg-gray-700 text-gray-200 transition cursor-pointer"
                  title="Previous Step (Left Arrow)"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  onClick={handleNext}
                  disabled={currentIndex >= totalSteps - 1}
                  className="p-1.5 rounded-lg bg-gray-800 disabled:opacity-40 hover:bg-gray-700 text-gray-200 transition cursor-pointer"
                  title="Next Step (Right Arrow)"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>

          {/* Step Timeline Strip */}
          {totalSteps > 1 && (
            <div className="px-6 py-2 bg-black/50 border-b border-gray-800/80 flex items-center gap-1.5 overflow-x-auto shrink-0">
              <span className="text-[10px] uppercase font-bold text-gray-500 mr-2 shrink-0">Timeline:</span>
              {slideshowItems.map((_, idx) => (
                <button
                  key={idx}
                  onClick={() => setCurrentIndex(idx)}
                  className={`px-2.5 py-0.5 rounded text-[11px] font-mono font-bold transition-all cursor-pointer shrink-0 ${
                    currentIndex === idx
                      ? 'bg-gremlin-purple text-white shadow-[0_0_10px_rgba(157,0,255,0.4)]'
                      : 'bg-gray-800/80 text-gray-400 hover:bg-gray-700 hover:text-gray-200'
                  }`}
                >
                  {idx + 1}
                </button>
              ))}
            </div>
          )}

          {/* Screenshot Display & Observation */}
          <div className="flex-1 min-h-0 p-4 md:p-6 flex flex-col gap-4">
            <div className="flex-1 min-h-0 bg-black border border-gray-800 rounded-2xl overflow-hidden flex items-center justify-center p-2 relative shadow-inner">
              {currentItem?.screenshot ? (
                <img
                  src={`data:image/jpeg;base64,${currentItem.screenshot}`}
                  alt={`Step ${currentIndex + 1} screenshot`}
                  className="max-h-full max-w-full object-contain rounded shadow-lg"
                />
              ) : (
                <div className="text-gray-500 text-xs font-mono">
                  No screenshot recorded for this step
                </div>
              )}
            </div>

            {/* Bottom Thought & Observation Console */}
            <div className="h-28 border border-gray-800 bg-bg-card rounded-2xl p-4 overflow-y-auto shadow-lg shrink-0">
              <div className="text-xs font-mono text-gray-300 leading-relaxed">
                <span className="text-gremlin-purple font-bold mr-2">&gt;</span>
                {currentItem?.thought || 'No thought recorded for this step.'}
              </div>
              {('friction_note' in currentItem) && currentItem.friction_note && (
                <div className="mt-2 text-[11px] text-amber-400 font-mono flex items-center gap-1.5">
                  <ShieldAlert className="w-3.5 h-3.5 shrink-0" />
                  <span>{currentItem.friction_note}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
