import { useState, useEffect, useCallback } from 'react';

interface Session {
  id: string;
  title: string;
  messageCount: number;
  lastActivity: Date;
  createdAt: Date;
}

const SESSIONS_KEY = 'voice-assistant-sessions';
const CURRENT_SESSION_KEY = 'voice-assistant-current-session';

export function useSessions() {
  const [sessions, setSessions] = useState<Session[]>(() => {
    try {
      const stored = localStorage.getItem(SESSIONS_KEY);
      if (stored) {
        return JSON.parse(stored).map((s: any) => ({
          ...s,
          lastActivity: new Date(s.lastActivity),
          createdAt: new Date(s.createdAt)
        }));
      }
    } catch (e) {
      console.error('Failed to load sessions:', e);
    }
    return [];
  });

  const [currentSessionId, setCurrentSessionId] = useState<string | null>(() => {
    return localStorage.getItem(CURRENT_SESSION_KEY);
  });

  // Save sessions to localStorage
  useEffect(() => {
    localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions));
  }, [sessions]);

  useEffect(() => {
    if (currentSessionId) {
      localStorage.setItem(CURRENT_SESSION_KEY, currentSessionId);
    }
  }, [currentSessionId]);

  const createSession = useCallback(() => {
    const newSession: Session = {
      id: `sess_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      title: 'New Conversation',
      messageCount: 0,
      lastActivity: new Date(),
      createdAt: new Date()
    };
    setSessions(prev => [newSession, ...prev]);
    setCurrentSessionId(newSession.id);
    return newSession.id;
  }, []);

  const updateSession = useCallback((sessionId: string, updates: Partial<Session>) => {
    setSessions(prev => prev.map(s => 
      s.id === sessionId ? { ...s, ...updates, lastActivity: new Date() } : s
    ));
  }, []);

  const deleteSession = useCallback((sessionId: string) => {
    setSessions(prev => prev.filter(s => s.id !== sessionId));
    if (currentSessionId === sessionId) {
      setCurrentSessionId(null);
    }
  }, [currentSessionId]);

  const switchSession = useCallback((sessionId: string) => {
    setCurrentSessionId(sessionId);
  }, []);

  const incrementMessageCount = useCallback((sessionId: string) => {
    setSessions(prev => prev.map(s => 
      s.id === sessionId ? { ...s, messageCount: s.messageCount + 1, lastActivity: new Date() } : s
    ));
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
    updateSessionTitle,
    incrementMessageCount
  };
}