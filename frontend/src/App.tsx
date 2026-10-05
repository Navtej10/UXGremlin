import { useState } from 'react';
import { Launchpad } from './components/Launchpad';
import { LiveDashboard } from './components/LiveDashboard';
import { Report, HistoryItem } from './components/Report';

function App() {
  const [session, setSession] = useState<{ url: string; task: string; persona: string } | null>(null);
  const [history, setHistory] = useState<HistoryItem[] | null>(null);

  const handleRestart = () => {
    setSession(null);
    setHistory(null);
  };

  return (
    <div className="antialiased">
      {!session ? (
        <Launchpad onLaunch={setSession} />
      ) : !history ? (
        <LiveDashboard session={session} onComplete={setHistory} />
      ) : (
        <Report session={session} history={history} onRestart={handleRestart} />
      )}
    </div>
  );
}

export default App;
