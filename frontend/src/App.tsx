import { useState, useEffect } from 'react';
import { Launchpad } from './components/Launchpad';
import { LiveDashboard } from './components/LiveDashboard';
import { MultiLaneLiveDashboard } from './components/MultiLaneLiveDashboard';
import { Report, type HistoryItem, type SabotageReport } from './components/Report';
import { Gremlin } from './components/mascot/Gremlin';
import { Button, Card, Skeleton } from './components/ui';
import { Zap } from 'lucide-react';

export interface SessionInfo {
  session_id?: string;
  previous_session_id?: string;
  url: string;
  task: string;
  persona: string;
  personas?: string[];
  baseline?: boolean;
  runs?: number;
}

function App() {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [history, setHistory] = useState<HistoryItem[] | null>(null);
  const [savedReport, setSavedReport] = useState<SabotageReport | null>(null);
  const [isReadOnly, setIsReadOnly] = useState<boolean>(false);
  const [isLoadingReport, setIsLoadingReport] = useState<boolean>(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const fetchSavedReport = async (reportId: string) => {
    setIsLoadingReport(true);
    setLoadError(null);
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/report/${encodeURIComponent(reportId)}`);
      if (!res.ok) {
        throw new Error(`Report "${reportId}" not found (HTTP ${res.status})`);
      }
      const data = await res.json();
      if (data.error) {
        throw new Error(data.error);
      }
      setSavedReport(data as SabotageReport);
      setSession({
        session_id: data.session_id || reportId,
        previous_session_id: data.previous_session_id,
        url: data.url || 'Target Application',
        task: data.task || 'Usability Audit',
        persona: data.persona || 'pro_tester',
        personas: data.personas || (data.persona ? [data.persona] : ['pro_tester']),
      });
      setHistory((data.actions as HistoryItem[]) || []);
      setIsReadOnly(true);
    } catch (err) {
      console.error('Failed to load saved report:', err);
      setLoadError((err as Error).message || 'Failed to load report');
    } finally {
      setIsLoadingReport(false);
    }
  };

  // Check URL path on mount and on popstate for read-only /report/:id routing
  useEffect(() => {
    const handleRoute = () => {
      const pathname = window.location.pathname;
      if (pathname.startsWith('/report/')) {
        const reportId = pathname.replace(/^\/report\/?/, '').trim();
        if (reportId) {
          fetchSavedReport(reportId);
          return;
        }
      }
      if (pathname === '/' || pathname === '') {
        setSession(null);
        setHistory(null);
        setSavedReport(null);
        setIsReadOnly(false);
        setLoadError(null);
      }
    };

    handleRoute();
    window.addEventListener('popstate', handleRoute);
    return () => window.removeEventListener('popstate', handleRoute);
  }, []);

  const handleRestart = () => {
    setSession(null);
    setHistory(null);
    setSavedReport(null);
    setIsReadOnly(false);
    setLoadError(null);
    window.history.pushState(null, '', '/');
  };

  const handleReRun = async (params: {
    url: string;
    task: string;
    persona: string;
    personas?: string[];
    previous_session_id: string;
  }) => {
    try {
      const response = await fetch('http://127.0.0.1:8000/api/start-session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: params.url,
          task: params.task,
          persona: params.persona,
          personas: params.personas || [params.persona],
          previous_session_id: params.previous_session_id,
          baseline: true,
          runs: 1,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        setSavedReport(null);
        setHistory(null);
        setIsReadOnly(false);
        setSession({
          session_id: data.session_id,
          previous_session_id: params.previous_session_id,
          url: params.url,
          task: params.task,
          persona: params.persona,
          personas: params.personas || [params.persona],
        });
        window.history.pushState(null, '', `/report/${data.session_id}`);
      }
    } catch (err) {
      console.error('Failed to launch re-test:', err);
    }
  };

  const isCompareMode = Boolean(session?.personas && session.personas.length > 1);

  // Supplementary State: Loading
  if (isLoadingReport) {
    return (
      <div className="h-screen w-screen bg-canvas text-ink flex flex-col items-center justify-center p-6 antialiased">
        <div className="flex flex-col items-center gap-4 max-w-sm text-center">
          <Gremlin pose="investigating" size="lg" animate={true} />
          <div>
            <h2 className="text-base font-bold text-ink tracking-tight">
              Digging through the archives…
            </h2>
            <p className="text-xs text-muted mt-1 leading-relaxed">
              Retrieving persisted usability session from the SQLite archive.
            </p>
          </div>

          {/* Skeleton Hint of Report Layout */}
          <div className="w-full mt-4 p-4 bg-surface border border-stone rounded-2xl shadow-subtle space-y-3">
            <div className="flex items-center justify-between">
              <Skeleton className="h-4 w-32 rounded-lg" />
              <Skeleton className="h-4 w-16 rounded-lg" />
            </div>
            <Skeleton className="h-14 w-full rounded-xl" />
            <div className="grid grid-cols-2 gap-2">
              <Skeleton className="h-8 w-full rounded-lg" />
              <Skeleton className="h-8 w-full rounded-lg" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Supplementary State: 404 Report Not Found
  if (loadError) {
    return (
      <div className="h-screen w-screen bg-canvas text-ink flex flex-col items-center justify-center p-6 antialiased">
        <Card className="max-w-md w-full p-8 flex flex-col items-center text-center shadow-card">
          <div className="mb-4">
            <Gremlin pose="confused" size="lg" animate={true} />
          </div>
          <h2 className="text-lg font-extrabold text-ink mb-1.5">
            We couldn't find that report
          </h2>
          <p className="text-xs text-muted mb-6 leading-relaxed">
            {loadError}. The report link may be invalid, expired, or removed from the archive.
          </p>
          <Button
            variant="primary"
            size="md"
            onClick={handleRestart}
            leftIcon={<Zap className="w-4 h-4 text-ink fill-ink" />}
            className="w-full"
          >
            Start a new attack
          </Button>
        </Card>
      </div>
    );
  }

  return (
    <div className="antialiased bg-canvas min-h-screen text-ink">
      {!session ? (
        <Launchpad
          onLaunch={(s) => {
            setSession(s);
            setIsReadOnly(false);
            if (s.session_id) {
              window.history.pushState(null, '', `/report/${s.session_id}`);
            }
          }}
        />
      ) : !history ? (
        isCompareMode ? (
          <MultiLaneLiveDashboard session={session} onComplete={(h) => setHistory(h)} />
        ) : (
          <LiveDashboard session={session} onComplete={setHistory} />
        )
      ) : (
        <Report
          session={session}
          history={history}
          initialReport={savedReport}
          isReadOnly={isReadOnly}
          onRestart={handleRestart}
          onReRun={handleReRun}
        />
      )}
    </div>
  );
}

export default App;
