import React, { useState } from 'react';
import { Session } from '../hooks/useSessions';
import { CloseIcon, MicIcon, PlusIcon, TrashIcon } from './Icons';

interface SessionSidebarProps {
  sessions: Session[];
  currentSessionId: string | null;
  isOpen: boolean;
  onClose: () => void;
  onSessionSelect: (sessionId: string) => void;
  onNewSession: () => void;
  onDeleteSession: (sessionId: string) => void;
  onRenameSession: (sessionId: string, title: string) => void;
}

const DAY_MS = 86_400_000;

function groupLabel(date: Date): string {
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const diff = startOfToday.getTime() - date.getTime();
  if (diff <= 0) return 'Today';
  if (diff <= DAY_MS) return 'Yesterday';
  if (diff <= 7 * DAY_MS) return 'Previous 7 days';
  return 'Older';
}

function relativeTime(date: Date): string {
  const minutes = Math.floor((Date.now() - date.getTime()) / 60_000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function groupSessions(sessions: Session[]): [string, Session[]][] {
  const sorted = [...sessions].sort((a, b) => b.lastActivity.getTime() - a.lastActivity.getTime());
  const groups = new Map<string, Session[]>();
  for (const session of sorted) {
    const label = groupLabel(session.lastActivity);
    groups.set(label, [...(groups.get(label) ?? []), session]);
  }
  return [...groups.entries()];
}

export const SessionSidebar: React.FC<SessionSidebarProps> = ({
  sessions,
  currentSessionId,
  isOpen,
  onClose,
  onSessionSelect,
  onNewSession,
  onDeleteSession,
  onRenameSession
}) => {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const startEditing = (session: Session) => {
    setEditingId(session.id);
    setEditTitle(session.title);
  };

  const commitEdit = (sessionId: string) => {
    const trimmed = editTitle.trim();
    if (trimmed) onRenameSession(sessionId, trimmed);
    setEditingId(null);
  };

  const handleDeleteClick = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    if (pendingDeleteId === sessionId) {
      onDeleteSession(sessionId);
      setPendingDeleteId(null);
    } else {
      setPendingDeleteId(sessionId);
    }
  };

  return (
    <aside className={`sidebar ${isOpen ? 'sidebar--open' : ''}`} aria-label="Conversations">
      <div className="sidebar__top">
        <div className="brand">
          <span className="brand__mark"><MicIcon /></span>
          <span className="brand__name">VoiceAI</span>
        </div>
        <button className="icon-btn sidebar__close" onClick={onClose} aria-label="Close conversations">
          <CloseIcon />
        </button>
      </div>

      <button className="new-chat" onClick={onNewSession}>
        <PlusIcon />
        New chat
      </button>

      <nav className="sidebar__list">
        {sessions.length === 0 ? (
          <p className="sidebar__empty">Your conversations will show up here.</p>
        ) : (
          groupSessions(sessions).map(([label, group]) => (
            <div key={label} className="sidebar__section">
              <div className="sidebar__group">{label}</div>
              {group.map(session => {
                const isActive = session.id === currentSessionId;
                const isPendingDelete = pendingDeleteId === session.id;
                return (
                  <div
                    key={session.id}
                    className={`conv ${isActive ? 'conv--active' : ''}`}
                    role="button"
                    tabIndex={0}
                    aria-current={isActive ? 'true' : undefined}
                    onClick={() => onSessionSelect(session.id)}
                    onKeyDown={(e) => { if (e.key === 'Enter') onSessionSelect(session.id); }}
                    onMouseLeave={() => isPendingDelete && setPendingDeleteId(null)}
                  >
                    <div className="conv__body">
                      {editingId === session.id ? (
                        <input
                          className="conv__input"
                          value={editTitle}
                          onChange={(e) => setEditTitle(e.target.value)}
                          onKeyDown={(e) => {
                            e.stopPropagation();
                            if (e.key === 'Enter') commitEdit(session.id);
                            if (e.key === 'Escape') setEditingId(null);
                          }}
                          onBlur={() => commitEdit(session.id)}
                          onClick={(e) => e.stopPropagation()}
                          autoFocus
                        />
                      ) : (
                        <>
                          <div
                            className="conv__title"
                            title="Double-click to rename"
                            onDoubleClick={(e) => { e.stopPropagation(); startEditing(session); }}
                          >
                            {session.title || 'Untitled'}
                          </div>
                          <div className="conv__meta">
                            {session.messageCount} {session.messageCount === 1 ? 'message' : 'messages'} · {relativeTime(session.lastActivity)}
                          </div>
                        </>
                      )}
                    </div>
                    {editingId !== session.id && (
                      <button
                        className={`conv__action ${isPendingDelete ? 'conv__action--confirm' : ''}`}
                        onClick={(e) => handleDeleteClick(e, session.id)}
                        aria-label={isPendingDelete ? 'Confirm delete' : 'Delete conversation'}
                      >
                        {isPendingDelete ? 'Delete' : <TrashIcon />}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          ))
        )}
      </nav>
    </aside>
  );
};
