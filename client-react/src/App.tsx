import React, { useState, useEffect } from 'react';
import { SessionSidebar } from './components/SessionSidebar';
import { ChatInterface } from './components/ChatInterface';
import { useSessions } from './hooks/useSessions';
import { Session } from './hooks/useSessions';

function App() {
  const { sessions, currentSessionId, createSession, switchSession } = useSessions();
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Find current session
  const currentSession = sessions.find(s => s.id === currentSessionId) || null;

  // Handle new session creation
  const handleNewSession = () => {
    const newId = createSession();
    switchSession(newId);
    if (window.innerWidth < 768) {
      setSidebarOpen(false);
    }
  };

  // Handle session selection
  const handleSessionSelect = (sessionId: string) => {
    switchSession(sessionId);
    if (window.innerWidth < 768) {
      setSidebarOpen(false);
    }
  };

  // Handle mobile sidebar toggle
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth >= 768) {
        setSidebarOpen(true);
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return (
    <div className="app">
      <button 
        className="sidebar-toggle"
        onClick={() => setSidebarOpen(!sidebarOpen)}
        aria-label={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          {sidebarOpen ? (
            <>
              <line x1="19" y1="12" x2="5" y2="12"></line>
              <path d="M12 19l-7-7 7-7"></path>
            </>
          ) : (
            <>
              <line x1="3" y1="12" x2="21" y2="12"></line>
              <line x1="3" y1="6" x2="21" y2="6"></line>
              <line x1="3" y1="18" x2="21" y2="18"></line>
            </>
          )}
        </svg>
      </button>

      <div className="main-content">
        <SessionSidebar 
          onSessionSelect={handleSessionSelect}
          onNewSession={handleNewSession}
        />
        <ChatInterface 
          session={currentSession}
          onSessionUpdate={() => {}}
        />
      </div>

      <style jsx>{`
        .app {
          min-height: 100vh;
          display: flex;
          background: var(--bg-0);
          color: var(--text-primary);
          position: relative;
        }
        .sidebar-toggle {
          display: none;
          position: fixed;
          top: 20px;
          left: 20px;
          z-index: 100;
          width: 48px;
          height: 48px;
          border: none;
          border-radius: var(--radius);
          background: var(--bg-2);
          color: var(--text-secondary);
          cursor: pointer;
          box-shadow: var(--shadow);
          align-items: center;
          justify-content: center;
          transition: all var(--transition);
        }
        .sidebar-toggle:hover {
          background: var(--bg-3);
          color: var(--text-primary);
          transform: translateY(-2px);
          box-shadow: var(--shadow-lg);
        }
        .main-content {
          display: flex;
          flex: 1;
          min-height: 100vh;
        }
        @media (max-width: 768px) {
          .sidebar-toggle {
            display: flex;
          }
          .main-content > .session-sidebar {
            position: fixed;
            left: 0;
            top: 0;
            bottom: 0;
            z-index: 50;
            transform: translateX(-100%);
            transition: transform var(--transition);
          }
          .main-content > .session-sidebar.open {
            transform: translateX(0);
          }
        }
      `}
      </style>
    </div>
  );
}

export default App;