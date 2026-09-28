import { useEffect, useState } from 'react';
import { SessionSidebar } from './components/SessionSidebar';
import { ChatInterface } from './components/ChatInterface';
import { Welcome } from './components/Welcome';
import { useSessions } from './hooks/useSessions';

function App() {
  const {
    sessions,
    currentSessionId,
    createSession,
    switchSession,
    deleteSession,
    updateSession,
    updateSessionTitle
  } = useSessions();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const currentSession = sessions.find(s => s.id === currentSessionId) ?? null;

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSidebarOpen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const handleNewSession = () => {
    createSession();
    setSidebarOpen(false);
  };

  const handleSessionSelect = (sessionId: string) => {
    switchSession(sessionId);
    setSidebarOpen(false);
  };

  return (
    <div className="app">
      {sidebarOpen && <div className="backdrop" onClick={() => setSidebarOpen(false)} aria-hidden="true" />}

      <SessionSidebar
        sessions={sessions.filter(s => s.messageCount > 0)}
        currentSessionId={currentSessionId}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onSessionSelect={handleSessionSelect}
        onNewSession={handleNewSession}
        onDeleteSession={deleteSession}
        onRenameSession={updateSessionTitle}
      />

      <main className="app__main">
        {currentSession ? (
          // Keyed by session so the socket and message state reset per conversation.
          <ChatInterface
            key={currentSession.id}
            session={currentSession}
            onOpenSidebar={() => setSidebarOpen(true)}
            onSessionUpdate={(updates) => updateSession(currentSession.id, updates)}
          />
        ) : (
          <Welcome onNewSession={handleNewSession} onOpenSidebar={() => setSidebarOpen(true)} />
        )}
      </main>
    </div>
  );
}

export default App;
