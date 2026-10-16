import { useState, useEffect } from 'react';
import { Launchpad } from './components/Launchpad';
import { LiveDashboard } from './components/LiveDashboard';
import { MultiLaneLiveDashboard } from './components/MultiLaneLiveDashboard';
import { Report, type HistoryItem, type SabotageReport } from './components/Report';
import { AlertTriangle, RefreshCcw } from 'lucide-react';

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

  if (isLoadingReport) {
    return (
      <div className="h-screen w-screen bg-bg-dark text-white flex flex-col items-center justify-center gap-4">
        <div className="w-12 h-12 rounded-full border-4 border-gremlin-purple border-t-transparent animate-spin" />
        <div className="text-center">
          <h2 className="text-lg font-bold uppercase tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-gremlin-purple to-gremlin-green">
            Loading Usability Report
          </h2>
          <p className="text-xs text-gray-400 mt-1">
            Retrieving persisted session from SQLite archive…
          </p>
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="h-screen w-screen bg-bg-dark text-white flex flex-col items-center justify-center p-6">
        <div className="max-w-md w-full bg-black/60 border border-red-500/40 rounded-xl p-8 flex flex-col items-center text-center shadow-2xl">
          <div className="w-12 h-12 rounded-full bg-red-950/60 border border-red-500/50 flex items-center justify-center mb-4 text-red-400">
            <AlertTriangle className="w-6 h-6" />
          </div>
          <h2 className="text-lg font-bold text-white mb-2">Report Not Found</h2>
          <p className="text-xs text-gray-400 mb-6 leading-relaxed">
            {loadError}. The report may not exist or has expired.
          </p>
          <button
            onClick={handleRestart}
            className="flex items-center gap-2 px-5 py-2.5 bg-gremlin-purple hover:bg-purple-600 text-white text-xs font-bold rounded-lg transition-all cursor-pointer shadow-lg"
          >
            <RefreshCcw className="w-4 h-4" />
            <span>Launch New Attack</span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="antialiased">
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
