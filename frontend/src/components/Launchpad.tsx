import { useState, type FormEvent } from 'react';
import {
  Link,
  Zap,
  Check,
  Sparkles,
  Camera,
  Terminal,
  Code2,
  Eye,
  Sliders,
  ChevronDown,
} from 'lucide-react';
import { Gremlin } from './mascot/Gremlin';
import {
  Button,
  Card,
  Input,
  Textarea,
  Toggle,
  Stepper,
  ChipSelect,
  Badge,
} from './ui';

interface LaunchpadProps {
  onLaunch: (data: {
    session_id?: string;
    url: string;
    task: string;
    persona: string;
    personas?: string[];
    baseline?: boolean;
    runs?: number;
  }) => void;
}

interface PersonaConfig {
  id: string;
  name: string;
  icon: string;
  desc: string;
  tag: string;
  pill?: string;
}

const AVAILABLE_PERSONAS: PersonaConfig[] = [
  {
    id: 'pro_tester',
    name: 'Pro Tester',
    icon: '🎯',
    desc: 'Methodical poweruser. Tests keyboard shortcuts, edge cases, and complex form interactions.',
    tag: 'High tolerance, low abandon rate',
  },
  {
    id: 'impatient',
    name: 'Impatient',
    icon: '😈',
    desc: 'Quick to abandon. Skips copy, clicks rapidly, easily frustrated by slow loads or hidden CTAs.',
    tag: 'Finds checkout abandonment blockers',
    pill: 'High RageClick',
  },
  {
    id: 'confused',
    name: 'Confused',
    icon: '😵‍💫',
    desc: 'First-time non-technical visitor. Easily distracted, misinterprets ambiguous labels and vague iconography.',
    tag: 'Reveals label friction & IA loops',
  },
  {
    id: 'skeptic',
    name: 'Skeptic',
    icon: '🧐',
    desc: 'Reluctant buyer. Looks for hidden fees, scrutinizes trust badges, checks privacy statements and return policies.',
    tag: 'Pinpoints trust leakages & opt-outs',
  },
  {
    id: 'mobile',
    name: 'Mobile User',
    icon: '📱',
    desc: 'Emulates 390x844 mobile viewport with touch gestures, auditing 44px tap targets and thumb reach.',
    tag: 'Finds viewport clipping & tap targets',
  },
];

const EXAMPLE_PROMPTS = [
  'Sign up for the cheapest plan',
  'Complete checkout flow',
  'Find pricing FAQ & cancel flow',
];

export function Launchpad({ onLaunch }: LaunchpadProps) {
  const [url, setUrl] = useState('');
  const [task, setTask] = useState('');
  const [selectedPersonas, setSelectedPersonas] = useState<string[]>(['pro_tester']);
  const [baseline, setBaseline] = useState(true);
  const [runs, setRuns] = useState(1);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [urlError, setUrlError] = useState<string | null>(null);

  const togglePersona = (id: string) => {
    setSelectedPersonas((prev) => {
      if (prev.includes(id)) {
        if (prev.length === 1) return prev; // Keep at least one persona
        return prev.filter((p) => p !== id);
      } else {
        return [...prev, id];
      }
    });
  };

  const handleSelectAll = () => {
    setSelectedPersonas(AVAILABLE_PERSONAS.map((p) => p.id));
  };

  const handleSelectTop3 = () => {
    setSelectedPersonas(['pro_tester', 'impatient', 'mobile']);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!url.trim()) {
      setUrlError('Please enter a target website URL');
      return;
    }
    setUrlError(null);
    setIsSubmitting(true);

    try {
      const response = await fetch('http://127.0.0.1:8000/api/start-session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: url.trim(),
          task: task.trim(),
          persona: selectedPersonas[0],
          personas: selectedPersonas,
          baseline,
          runs,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        onLaunch({
          session_id: data.session_id,
          url: url.trim(),
          task: task.trim(),
          persona: selectedPersonas[0],
          personas: selectedPersonas,
          baseline,
          runs,
        });
      } else {
        console.error('Failed to launch attack.');
      }
    } catch (err) {
      console.error('Error launching attack:', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const isCompareMode = selectedPersonas.length > 1;

  return (
    <div className="min-h-screen bg-canvas text-ink flex flex-col antialiased">
      {/* Top Application Header */}
      <header className="h-16 border-b border-stone bg-surface px-6 md:px-10 flex items-center justify-between shrink-0 sticky top-0 z-20">
        <div className="flex items-center gap-3">
          <Gremlin pose="idle" size="sm" animate={false} />
          <div>
            <span className="font-bold text-base tracking-tight text-ink">UXGremlin</span>
            <span className="hidden sm:inline-block text-xs text-muted ml-2.5 pl-2.5 border-l border-stone">
              Finds what users miss.
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="hidden md:flex items-center gap-2 px-3 py-1 bg-canvas border border-stone rounded-full font-mono text-[11px] text-muted">
            <span className="w-2 h-2 rounded-full bg-gremlin-dark" />
            <span>Autonomous Runner: v2.4 Ready</span>
          </div>
          <Badge variant="running">Runs today: 4</Badge>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-[1240px] w-full mx-auto p-6 md:p-10 flex flex-col gap-8">
        {/* Hero Section */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 pb-2">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2 flex-wrap">
              <h1 className="text-2xl md:text-3xl font-extrabold text-ink tracking-tight">
                Release the gremlin
              </h1>
              <Badge variant="running">AGENT ACTIVE</Badge>
            </div>
            <p className="text-sm text-muted max-w-2xl leading-relaxed">
              Configure an autonomous browser session to test a specific user flow and uncover silent usability friction before your customers do.
            </p>
          </div>

          <div className="hidden lg:flex items-center gap-4 shrink-0">
            <Gremlin pose="idle" size="hero" animate={true} />
          </div>
        </div>

        {/* Two-Column Grid: Left Form Card / Right Information Rail */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Main Form Card (7 Cols on desktop) */}
          <div className="lg:col-span-8 flex flex-col gap-6">
            <Card className="p-6 md:p-8">
              <form onSubmit={handleSubmit} className="flex flex-col gap-6">
                {/* Target URL Input */}
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label htmlFor="url" className="text-xs font-semibold text-ink">
                      Website target URL <span className="text-severity-critical-fg">*</span>
                    </label>
                    <span className="text-[11px] font-mono text-muted">HTTPS only</span>
                  </div>
                  <Input
                    id="url"
                    type="url"
                    required
                    mono
                    placeholder="https://example.com/signup"
                    value={url}
                    error={urlError || undefined}
                    onChange={(e) => {
                      setUrl(e.target.value);
                      if (urlError) setUrlError(null);
                    }}
                    leftIcon={<Link className="w-4 h-4" />}
                    rightElement={
                      <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-canvas border border-stone text-muted">
                        Headers
                      </span>
                    }
                  />
                </div>

                {/* Target Task Textarea & Example Chips */}
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label htmlFor="task" className="text-xs font-semibold text-ink">
                      What should the gremlin try to do? <span className="text-severity-critical-fg">*</span>
                    </label>
                    <span className="text-[11px] text-muted">Plain English instruction</span>
                  </div>
                  <Textarea
                    id="task"
                    required
                    rows={3}
                    placeholder="Sign up for a free trial, select the Starter tier, and attempt to invite a teammate without getting stuck."
                    value={task}
                    onChange={(e) => setTask(e.target.value)}
                    bottomRightHint={task.length > 0 ? `~${Math.ceil(task.length / 4)} tokens` : undefined}
                  />

                  {/* Example prompt chips */}
                  <div className="mt-2.5 flex items-center gap-1.5 flex-wrap">
                    <span className="text-[11px] text-muted mr-1 font-medium select-none">
                      Try prompt:
                    </span>
                    {EXAMPLE_PROMPTS.map((promptText) => (
                      <ChipSelect
                        key={promptText}
                        onClick={() => setTask(promptText)}
                      >
                        {promptText}
                      </ChipSelect>
                    ))}
                  </div>
                </div>

                {/* Persona Multi-Select Section */}
                <div className="pt-2 border-t border-stone">
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <h2 className="text-xs font-semibold text-ink block">
                        Testing Persona
                      </h2>
                      <p className="text-xs text-muted">
                        Choose how the autonomous agent behaves and reacts to UX friction.
                      </p>
                    </div>
                    <div className="flex items-center gap-2 text-xs">
                      <span className="font-mono text-[11px] px-2 py-0.5 rounded-full bg-gremlin/20 text-ink font-semibold border border-gremlin/40">
                        {selectedPersonas.length} {selectedPersonas.length === 1 ? 'persona' : 'personas'} selected
                      </span>
                      <button
                        type="button"
                        onClick={handleSelectTop3}
                        className="text-muted hover:text-ink transition underline cursor-pointer text-[11px]"
                      >
                        Top 3
                      </button>
                      <span className="text-stone font-bold">·</span>
                      <button
                        type="button"
                        onClick={handleSelectAll}
                        className="text-muted hover:text-ink transition underline cursor-pointer text-[11px]"
                      >
                        All 5
                      </button>
                    </div>
                  </div>

                  {/* Personas 2-Column Grid */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {AVAILABLE_PERSONAS.map((p) => {
                      const isSelected = selectedPersonas.includes(p.id);
                      return (
                        <div
                          key={p.id}
                          role="checkbox"
                          tabIndex={0}
                          aria-checked={isSelected}
                          onClick={() => togglePersona(p.id)}
                          onKeyDown={(e) => {
                            if (e.key === ' ' || e.key === 'Enter') {
                              e.preventDefault();
                              togglePersona(p.id);
                            }
                          }}
                          className={`p-3.5 rounded-2xl border text-left transition-all duration-150 flex flex-col justify-between gap-3 cursor-pointer select-none focus-visible:outline-2 focus-visible:outline-gremlin-dark focus-visible:outline-offset-2 ${
                            isSelected
                              ? 'bg-gremlin/15 border-2 border-gremlin shadow-subtle'
                              : 'bg-surface border-stone hover:border-muted/50 hover:bg-canvas/60'
                          }`}
                        >
                          <div>
                            <div className="flex items-center justify-between gap-2 mb-1.5">
                              <div className="flex items-center gap-2">
                                <span className="text-lg shrink-0">{p.icon}</span>
                                <span className="text-xs font-bold text-ink">{p.name}</span>
                              </div>
                              <div className="flex items-center gap-1.5">
                                {p.pill && (
                                  <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-severity-critical-bg text-severity-critical-fg border border-severity-critical-fg/20">
                                    {p.pill}
                                  </span>
                                )}
                                <div
                                  className={`w-4 h-4 rounded-full flex items-center justify-center shrink-0 border transition-all ${
                                    isSelected
                                      ? 'bg-gremlin-dark border-gremlin-dark text-surface'
                                      : 'border-stone bg-canvas'
                                  }`}
                                >
                                  {isSelected && <Check className="w-3 h-3 stroke-[3]" />}
                                </div>
                              </div>
                            </div>
                            <p className="text-xs text-muted leading-relaxed line-clamp-3">
                              {p.desc}
                            </p>
                          </div>

                          <div className="pt-2 border-t border-stone/50 flex items-center justify-between text-[11px] text-muted">
                            <span className="truncate">● {p.tag}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* Multi-lane Callout */}
                  {isCompareMode && (
                    <div className="mt-3.5 p-3 rounded-xl bg-gremlin/10 border border-gremlin/30 flex items-center justify-between text-xs text-ink">
                      <span className="flex items-center gap-2 font-semibold">
                        <span className="w-2 h-2 rounded-full bg-gremlin-dark animate-pulse" />
                        <span>{selectedPersonas.length} personas selected → {selectedPersonas.length} parallel execution lanes</span>
                      </span>
                      <span className="text-muted font-mono text-[11px]">Concurrent browser contexts</span>
                    </div>
                  )}
                </div>

                {/* Advanced Execution Parameters Toggle / Accordion */}
                <div className="pt-2 border-t border-stone">
                  <button
                    type="button"
                    onClick={() => setShowAdvanced(!showAdvanced)}
                    className="w-full flex items-center justify-between text-xs text-muted hover:text-ink font-semibold py-1 transition cursor-pointer select-none"
                  >
                    <div className="flex items-center gap-2">
                      <Sliders className="w-3.5 h-3.5" />
                      <span>Advanced execution parameters</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[11px] text-muted">
                        Desktop Chrome 1440×900 · Max 25 steps
                      </span>
                      <ChevronDown
                        className={`w-3.5 h-3.5 transition-transform ${
                          showAdvanced ? 'rotate-180' : ''
                        }`}
                      />
                    </div>
                  </button>

                  {showAdvanced && (
                    <div className="mt-4 p-4 rounded-xl bg-canvas border border-stone flex flex-col gap-4">
                      {/* Baseline Calibration Toggle */}
                      <Toggle
                        id="baseline-toggle"
                        checked={baseline}
                        onChange={setBaseline}
                        label="Run Baseline Calibration"
                        helperText="Runs a direct baseline agent first to determine expected ideal steps (cached per task)."
                      />

                      {/* Number of Runs Stepper */}
                      <div className="pt-3 border-t border-stone/60">
                        <Stepper
                          value={runs}
                          onChange={setRuns}
                          min={1}
                          max={3}
                          label="Multi-Run Consistency Audit"
                          helperText={
                            runs === 1
                              ? '1 single run (~1-2 minutes).'
                              : `${runs} sequential runs to test behavioral reproducibility across executions.`
                          }
                        />
                      </div>
                    </div>
                  )}
                </div>

                {/* Submit CTA Button */}
                <div className="pt-2">
                  <Button
                    type="submit"
                    variant="primary"
                    size="lg"
                    loading={isSubmitting}
                    className="w-full uppercase tracking-wider text-sm font-extrabold shadow-card hover:-translate-y-0.5"
                    leftIcon={<Zap className="w-4 h-4 text-ink fill-ink" />}
                  >
                    {isCompareMode
                      ? `SABOTAGE WEBSITE (${selectedPersonas.length} LANES)`
                      : 'SABOTAGE WEBSITE'}
                  </Button>
                </div>

                {/* Sandboxed notice footer */}
                <div className="text-center text-[11px] text-muted font-mono flex items-center justify-center gap-2 select-none">
                  <span className="w-1.5 h-1.5 rounded-full bg-gremlin-dark" />
                  <span>Sandboxed Chromium Container (Playwright) · Bounded exploration</span>
                </div>
              </form>
            </Card>
          </div>

          {/* Right Information Rail (4 Cols on desktop) */}
          <div className="lg:col-span-4 flex flex-col gap-6">
            {/* Lilac "What to Expect" Scope Card */}
            <Card className="p-6 bg-lilac/30 border-lilac-text/20">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2 text-xs font-bold text-lilac-text">
                  <Sparkles className="w-4 h-4 text-lilac-text" />
                  <span>What to expect</span>
                </div>
                <Badge variant="ai-lilac">LIVE AGENT</Badge>
              </div>

              <p className="text-xs text-ink/80 leading-relaxed font-medium">
                Bounded exploration, not an exhaustive audit. The agent simulates one realistic visitor session with behavioral traits from your chosen persona.
              </p>

              <div className="mt-4 pt-3 border-t border-lilac-text/15 space-y-2.5">
                <span className="text-[10px] uppercase font-bold tracking-wider text-lilac-text block">
                  Diagnostic Outputs Captured:
                </span>

                <div className="flex items-start gap-2 text-xs text-ink/90">
                  <Camera className="w-3.5 h-3.5 text-lilac-text shrink-0 mt-0.5" />
                  <span><strong>DOM screenshots</strong>: captured before &amp; after each action.</span>
                </div>

                <div className="flex items-start gap-2 text-xs text-ink/90">
                  <Terminal className="w-3.5 h-3.5 text-lilac-text shrink-0 mt-0.5" />
                  <span><strong>Thought trail</strong>: inner monologue explaining friction.</span>
                </div>

                <div className="flex items-start gap-2 text-xs text-ink/90">
                  <Code2 className="w-3.5 h-3.5 text-lilac-text shrink-0 mt-0.5" />
                  <span><strong>DOM selectors</strong>: target elements for code reproduction.</span>
                </div>

                <div className="flex items-start gap-2 text-xs text-ink/90">
                  <Eye className="w-3.5 h-3.5 text-lilac-text shrink-0 mt-0.5" />
                  <span><strong>Heuristic friction penalties</strong>: cognitive load scoring.</span>
                </div>
              </div>

              <div className="mt-4 p-3 rounded-xl bg-surface border border-lilac-text/20 text-xs text-ink leading-relaxed">
                <strong className="text-lilac-text block text-[11px] uppercase tracking-wider mb-1">
                  💡 Gremlin Pro-Tip:
                </strong>
                Specific tasks like <em>"Sign up for the cheapest plan"</em> yield sharper, higher-severity findings than open-ended browsing.
              </div>
            </Card>

            {/* Simulated Live Runner Preview Frame */}
            <Card className="p-4 overflow-hidden">
              <div className="flex items-center justify-between mb-3 text-xs">
                <span className="font-semibold text-ink">Simulated Runner Preview</span>
                <span className="w-2 h-2 rounded-full bg-gremlin-dark" />
              </div>

              {/* Mini Browser Frame */}
              <div className="bg-canvas border border-stone rounded-xl overflow-hidden">
                <div className="h-6 px-2.5 bg-surface border-b border-stone flex items-center justify-between">
                  <div className="flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-stone" />
                    <span className="w-1.5 h-1.5 rounded-full bg-stone" />
                    <span className="w-1.5 h-1.5 rounded-full bg-stone" />
                  </div>
                  <span className="font-mono text-[9px] text-muted">
                    {url ? url.replace(/^https?:\/\//, '').slice(0, 24) : 'playwright/chromium'}
                  </span>
                  <div className="w-3" />
                </div>
                <div className="h-28 flex flex-col items-center justify-center p-4 bg-canvas text-center">
                  <div className="px-3 py-1 rounded bg-gremlin/30 border border-gremlin text-[11px] font-mono text-ink font-bold">
                    Target #interactive-element
                  </div>
                  <span className="text-[10px] text-muted font-mono mt-2">
                    Telemetry streams live via FastAPI SSE
                  </span>
                </div>
              </div>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
}
