import { useState } from 'react';
import { Launchpad } from './components/Launchpad';
import { LiveDashboard } from './components/LiveDashboard';

function App() {
  const [session, setSession] = useState<{ url: string; task: string; persona: string } | null>(null);

  return (
    <div className="antialiased">
      {session ? (
        <LiveDashboard session={session} />
      ) : (
        <Launchpad onLaunch={setSession} />
      )}
    </div>
  );
}

export default App;
