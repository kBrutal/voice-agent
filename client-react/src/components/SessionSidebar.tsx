import React, { useState } from 'react';
import { Session, useSessions } from '../hooks/useSessions';

interface SessionSidebarProps {
  onSessionSelect: (sessionId: string) => void;
  onNewSession: () => void;
}

export const SessionSidebar: React.FC<SessionSidebarProps> = ({ 
  onSessionSelect, 
  onNewSession 
}) => {
  const { sessions, currentSessionId, deleteSession } = useSessions();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');

  const handleDelete = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    if (confirm('Delete this conversation?')) {
      deleteSession(sessionId);
    }
  };

  const handleTitleClick = (session: Session) => {
    setEditingId(session.id);
    setEditTitle(session.title);
  };

  const handleEditSubmit = (sessionId: string) => {
    setEditingId(null);
  };

  const handleEditKeyDown = (e: React.KeyboardEvent, sessionId: string) => {
    if (e.key === 'Enter') {
      handleEditSubmit(sessionId);
    } else if (e.key === 'Escape') {
      setEditingId(null);
    }
  };

  const formatTime = (date: Date | string) => {
    const d = new Date(date);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return 'Just now';
    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ago`;
    if (days < 7) return `${days}d ago`;
    return d.toLocaleDateString();
  };

  return (
    <aside className="session-sidebar glass">
      <div className="sidebar-header">
        <div className="logo">
          <svg width="28" height="28" viewBox="0 0 100 100" fill="none">
            <defs>
              <linearGradient id="logoGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#00d4ff" />
                <stop offset="100%" stopColor="#0066cc" />
              </linearGradient>
            </defs>
            <circle cx="50" cy="50" r="48" fill="url(#logoGrad)" />
            <path d="M50 25a25 25 0 0 1 25 25v15a25 25 0 0 1-50 0V50a25 0 0 0 1 25-25 25 0 0 1 25 25z" fill="white" opacity="0.95"/>
            <circle cx="50" cy="33" r="6" fill="white" />
            <rect x="38" y="52" width="24" height="3" rx="1.5" fill="white" opacity="0.5"/>
            <rect x="38" y="60" width="16" height="2" rx="1" fill="white" opacity="0.3"/>
          </svg>
          <h2>VoiceAI</h2>
        </div>
        <button className="new-session-btn glass-strong interactive" onClick={onNewSession}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19"></line>
            <line x1="5" y1="12" x2="19" y2="12"></line>
          </svg>
          <span>New Chat</span>
        </button>
      </div>

      <div className="sessions-list">
        {sessions.length === 0 ? (
          <div className="empty-sessions">
            <div className="empty-icon">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
              </svg>
            </div>
            <p>No conversations</p>
            <button className="empty-cta btn-primary interactive" onClick={onNewSession}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19"></line>
                <line x1="5" y1="12" x2="19" y2="12"></line>
              </svg>
              Start Conversation
            </button>
          </div>
        ) : (
          sessions.map(session => (
            <div
              key={session.id}
              className={`session-item glass interactive ${currentSessionId === session.id ? 'active' : ''}`}
              onClick={() => onSessionSelect(session.id)}
            >
              <div className="session-content">
                {editingId === session.id ? (
                  <input
                    type="text"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onKeyDown={(e) => handleEditKeyDown(e, session.id)}
                    onBlur={() => handleEditSubmit(session.id)}
                    autoFocus
                    className="session-title-edit"
                  />
                ) : (
                  <>
                    <div className="session-title" onDoubleClick={(e) => { e.stopPropagation(); handleTitleClick(session); }}>
                      {session.title || 'Untitled'}
                    </div>
                    <div className="session-meta">
                      <span className="message-count">{session.messageCount}</span>
                      <span className="separator">•</span>
                      <span className="time">{formatTime(session.lastActivity)}</span>
                    </div>
                  </>
                )}
              </div>
              <button
                className="delete-session-btn"
                onClick={(e) => handleDelete(e, session.id)}
                aria-label="Delete session"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="3 6 5 6 21 6"></polyline>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                </svg>
              </button>
            </div>
          ))
        )}
      </div>

      <style jsx>{`
        .session-sidebar {
          width: var(--sidebar-width);
          background: var(--surface-1);
          border-right: 1px solid var(--border);
          display: flex;
          flex-direction: column;
          height: 100vh;
          overflow: hidden;
          border-radius: 0;
        }
        .sidebar-header {
          padding: 24px;
          border-bottom: 1px solid var(--border);
          display: flex;
          flex-direction: column;
          gap: 20px;
        }
        .logo {
          display: flex;
          align-items: center;
          gap: 12px;
        }
        .logo h2 {
          margin: 0;
          font-size: 18px;
          font-weight: 700;
          background: linear-gradient(135deg, var(--text-primary), var(--accent-300));
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }
        .new-session-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 10px;
          padding: 12px 20px;
          background: var(--accent);
          color: white;
          border: none;
          border-radius: var(--radius);
          font-weight: 600;
          font-size: 14px;
          cursor: pointer;
          transition: all var(--transition);
          box-shadow: var(--shadow-sm);
          letter-spacing: 0.3px;
        }
        .new-session-btn:hover {
          background: var(--accent-600);
          transform: translateY(-2px);
          box-shadow: var(--shadow-glow);
        }
        .sessions-list {
          flex: 1;
          overflow-y: auto;
          padding: 12px;
        }
        .empty-sessions {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          height: 100%;
          padding: 24px;
          text-align: center;
          color: var(--text-muted);
        }
        .empty-icon {
          width: 80px;
          height: 80px;
          border-radius: var(--radius-xl);
          background: var(--surface-2);
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--text-muted);
          margin-bottom: 24px;
        }
        .empty-icon svg {
          width: 32px;
          height: 32px;
          opacity: 0.5;
        }
        .empty-sessions p {
          margin: 0 0 20px;
          font-size: 16px;
          font-weight: 500;
        }
        .empty-cta {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 18px;
          background: var(--accent);
          color: white;
          border: none;
          border-radius: var(--radius);
          font-weight: 500;
          font-size: 14px;
          cursor: pointer;
          transition: all var(--transition);
        }
        .empty-cta:hover {
          background: var(--accent-600);
          transform: translateY(-1px);
          box-shadow: var(--shadow);
        }
        .session-item {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 14px 16px;
          border-radius: var(--radius);
          cursor: pointer;
          transition: all var(--transition);
          position: relative;
          margin-bottom: 8px;
        }
        .session-item:hover {
          transform: translateY(-1px);
          box-shadow: var(--shadow);
        }
        .session-item.active {
          background: var(--accent-bg);
          border-color: var(--accent-border);
        }
        .session-content {
          flex: 1;
          min-width: 0;
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .session-title {
          font-size: 14px;
          font-weight: 500;
          color: var(--text-primary);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          line-height: 1.3;
        }
        .session-item.active .session-title {
          color: var(--accent);
        }
        .session-meta {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 11px;
          color: var(--text-muted);
        }
        .message-count {
          font-weight: 500;
          color: var(--text-secondary);
        }
        .separator {
          opacity: 0.5;
        }
        .time {
          color: var(--text-muted);
        }
        .session-title-edit {
          width: 100%;
          padding: 6px 10px;
          background: var(--bg-2);
          border: 1px solid var(--accent);
          border-radius: var(--radius-sm);
          color: var(--text-primary);
          font-size: 14px;
          outline: none;
          box-shadow: 0 0 0 3px var(--accent-bg);
        }
        .delete-session-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 32px;
          height: 32px;
          border: none;
          background: transparent;
          border-radius: var(--radius-sm);
          color: var(--text-muted);
          cursor: pointer;
          opacity: 0;
          transition: all var(--transition);
        }
        .session-item:hover .delete-session-btn {
          opacity: 1;
        }
        .delete-session-btn:hover {
          background: var(--error-bg);
          color: var(--error);
          transform: scale(1.1);
        }
      `}
      </style>
    </aside>
  );
};