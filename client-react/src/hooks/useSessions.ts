import { useState, useEffect, useCallback } from 'react';

export interface Session {
  id: string;
  title: string;
  messageCount: number;
  lastActivity: Date;
  createdAt: Date;
}

export const DEFAULT_SESSION_TITLE = 'New Conversation';

const SESSIONS_KEY = 'voice-assistant-sessions';
const CURRENT_SESSION_KEY = 'voice-assistant-current-session';

export const messagesStorageKey = (sessionId: string) => `voice-assistant-messages-${sessionId}`;

function loadSessions(): Session[] {
  try {
    const stored = localStorage.getItem(SESSIONS_KEY);
    if (stored) {
      const all: Session[] = JSON.parse(stored);
      for (const s of all) {
        if (s.messageCount === 0) localStorage.removeItem(messagesStorageKey(s.id));
      }
      return all
        .filter(s => s.messageCount > 0)
        .map(s => ({
          ...s,
          lastActivity: new Date(s.lastActivity),
          createdAt: new Date(s.createdAt)
        }));
    }
  } catch (e) {
    console.error('Failed to load sessions:', e);
  }
  return [];
}

export function useSessions() {
  const [sessions, setSessions] = useState<Session[]>(loadSessions);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(() =>
    localStorage.getItem(CURRENT_SESSION_KEY)
  );

  useEffect(() => {
    localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions.filter(s => s.messageCount > 0)));
  }, [sessions]);

  useEffect(() => {
    if (currentSessionId) {
      localStorage.setItem(CURRENT_SESSION_KEY, currentSessionId);
    } else {
      localStorage.removeItem(CURRENT_SESSION_KEY);
    }
  }, [currentSessionId]);

  const createSession = useCallback(() => {
    const emptySession = sessions.find(s => s.messageCount === 0);
    if (emptySession) {
      setCurrentSessionId(emptySession.id);
      return emptySession.id;
    }

    const newSession: Session = {
      id: `sess_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`,
      title: DEFAULT_SESSION_TITLE,
      messageCount: 0,
      lastActivity: new Date(),
      createdAt: new Date()
    };
    setSessions(prev => [newSession, ...prev]);
    setCurrentSessionId(newSession.id);
    return newSession.id;
  }, [sessions]);

  const updateSession = useCallback((sessionId: string, updates: Partial<Session>) => {
    setSessions(prev => prev.map(s =>
      s.id === sessionId ? { ...s, ...updates, lastActivity: new Date() } : s
    ));
  }, []);

  const deleteSession = useCallback((sessionId: string) => {
    setSessions(prev => prev.filter(s => s.id !== sessionId));
    localStorage.removeItem(messagesStorageKey(sessionId));
    setCurrentSessionId(prev => (prev === sessionId ? null : prev));
  }, []);

  const switchSession = useCallback((sessionId: string) => {
    setCurrentSessionId(sessionId);
  }, []);

  const updateSessionTitle = useCallback((sessionId: string, title: string) => {
    updateSession(sessionId, { title });
  }, [updateSession]);

  return {
    sessions,
    currentSessionId,
    createSession,
    switchSession,
    deleteSession,
    updateSession,
    updateSessionTitle
  };
}
