import { useState } from 'react';
import { Skull, Zap } from 'lucide-react';

export function Launchpad({ onLaunch }: { onLaunch: (data: { url: string; task: string; persona: string }) => void }) {
  const [url, setUrl] = useState('');
  const [task, setTask] = useState('');
  const [persona, setPersona] = useState('impatient');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    console.log('Launch attack:', { url, task, persona });
    try {
      const response = await fetch('http://127.0.0.1:8000/api/launch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, task, persona }),
      });
      if (response.ok) {
        console.log("Attack launched successfully!");
        onLaunch({ url, task, persona });
      } else {
        console.error("Failed to launch attack.");
      }
    } catch (err) {
      console.error("Error launching attack:", err);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-xl bg-bg-card border border-gremlin-purple/30 rounded-2xl shadow-[0_0_40px_rgba(157,0,255,0.15)] overflow-hidden">
        <div className="p-8">
          <div className="flex items-center gap-3 mb-8">
            <div className="w-12 h-12 rounded-xl bg-gremlin-purple/20 flex items-center justify-center border border-gremlin-purple/50">
              <Skull className="w-7 h-7 text-gremlin-green" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-white tracking-tight">UXGremlin</h1>
              <p className="text-text-main/80 text-sm">Automated UX Sabotage Engine</p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label htmlFor="url" className="block text-sm font-medium text-text-main mb-2">Target Website URL</label>
              <input
                id="url"
                type="url"
                required
                placeholder="https://example.com"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                className="w-full px-4 py-3 bg-bg-dark border border-gray-700 rounded-lg focus:outline-none focus:border-gremlin-purple focus:ring-1 focus:ring-gremlin-purple text-white placeholder-gray-500 transition-colors"
              />
            </div>

            <div>
              <label htmlFor="task" className="block text-sm font-medium text-text-main mb-2">Target Task</label>
              <textarea
                id="task"
                required
                placeholder="e.g., Sign up for the cheapest pricing plan"
                value={task}
                onChange={(e) => setTask(e.target.value)}
                rows={3}
                className="w-full px-4 py-3 bg-bg-dark border border-gray-700 rounded-lg focus:outline-none focus:border-gremlin-purple focus:ring-1 focus:ring-gremlin-purple text-white placeholder-gray-500 transition-colors resize-none"
              />
            </div>

            <div>
              <label htmlFor="persona" className="block text-sm font-medium text-text-main mb-2">Saboteur Persona</label>
              <select
                id="persona"
                value={persona}
                onChange={(e) => setPersona(e.target.value)}
                className="w-full px-4 py-3 bg-bg-dark border border-gray-700 rounded-lg focus:outline-none focus:border-gremlin-purple focus:ring-1 focus:ring-gremlin-purple text-white transition-colors appearance-none"
              >
                <option value="impatient">😈 Impatient User (Rushes, skips reading)</option>
                <option value="confused">😵‍💫 Confused User (Clicks randomly, gets lost)</option>
                <option value="skeptic">🧐 Skeptical User (Hesitates, looks for hidden catches)</option>
              </select>
            </div>

            <button
              type="submit"
              className="w-full py-4 mt-4 bg-gremlin-purple hover:bg-gremlin-purple/90 text-white font-bold rounded-lg shadow-[0_0_20px_rgba(157,0,255,0.4)] hover:shadow-[0_0_30px_rgba(57,255,20,0.4)] hover:text-gremlin-green transition-all flex items-center justify-center gap-2 group"
            >
              <Zap className="w-5 h-5 group-hover:animate-pulse" />
              SABOTAGE WEBSITE
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
