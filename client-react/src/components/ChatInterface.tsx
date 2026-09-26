import React, { useRef, useEffect, useState, useCallback } from 'react';
import { Message, useVoiceWebSocket } from '../hooks/useVoiceWebSocket';
import { Session } from '../hooks/useSessions';

interface ChatInterfaceProps {
  session: Session | null;
  onSessionUpdate: (messageCount: number) => void;
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({ 
  session, 
  onSessionUpdate 
}) => {
  const { 
    isConnected, 
    messages, 
    status, 
    error, 
    startRecording, 
    stopRecording, 
    interrupt,
    clearMessages 
  } = useVoiceWebSocket(session?.id || null);

  const [showError, setShowError] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const voiceVisualizerRef = useRef<HTMLDivElement>(null);
  const animationFrameRef = useRef<number>();

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (status === 'recording' && voiceVisualizerRef.current) {
      animateVisualizer();
    } else {
      cancelAnimationFrame(animationFrameRef.current);
      resetVisualizer();
    }
  }, [status]);

  const animateVisualizer = () => {
    const bars = voiceVisualizerRef.current?.querySelectorAll('.visualizer-bar');
    if (!bars) return;

    bars.forEach((bar: Element, i: number) => {
      const height = Math.random() * 70 + 15;
      (bar as HTMLElement).style.height = `${height}%`;
    });
    animationFrameRef.current = requestAnimationFrame(animateVisualizer);
  };

  const resetVisualizer = () => {
    const bars = voiceVisualizerRef.current?.querySelectorAll('.visualizer-bar');
    bars?.forEach((bar: Element) => {
      (bar as HTMLElement).style.height = '12%';
    });
  };

  const handleRecord = () => {
    if (status === 'recording') {
      stopRecording();
    } else if (status === 'idle' || status === 'error') {
      startRecording();
    }
  };

  const handleInterrupt = () => {
    interrupt();
  };

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const getStatusConfig = (s: string) => {
    const configs = {
      recording: { icon: 'mic', label: 'Listening', color: 'var(--error)', bg: 'var(--error-bg)' },
      processing: { icon: 'processing', label: 'Processing', color: 'var(--warning)', bg: 'var(--warning-bg)' },
      speaking: { icon: 'volume', label: 'Speaking', color: 'var(--success)', bg: 'var(--success-bg)' },
      connecting: { icon: 'wifi', label: 'Connecting', color: 'var(--warning)', bg: 'var(--warning-bg)' },
      error: { icon: 'alert', label: 'Error', color: 'var(--error)', bg: 'var(--error-bg)' },
      idle: { icon: 'check', label: 'Ready', color: 'var(--text-secondary)', bg: 'var(--surface-2)' }
    };
    return configs[s as keyof typeof configs] || configs.idle;
  };

  const statusConfig = getStatusConfig(status);

  if (!session) {
    return (
      <div className="chat-empty-view">
        <div className="empty-hero">
          <div className="hero-icon">
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"></path>
              <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
              <line x1="12" y1="19" x2="12" y2="22"></line>
            </svg>
          </div>
          <h2>Welcome to VoiceAI</h2>
          <p>Start a conversation to talk with the AI assistant</p>
          <button className="hero-btn" onClick={() => {
            // This will be handled by parent
          }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"></line>
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
            Start New Conversation
          </button>
        </div>
        <style jsx>{`
          .chat-empty-view {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 40px;
            background: var(--bg-0);
          }
          .empty-hero {
            text-align: center;
            max-width: 400px;
          }
          .hero-icon {
            width: 120px;
            height: 120px;
            border-radius: var(--radius-xl);
            background: var(--surface-2);
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--text-muted);
            margin: 0 auto 32px;
            box-shadow: var(--shadow-lg);
          }
          .hero-icon svg {
            width: 48px;
            height: 48px;
            opacity: 0.5;
          }
          .empty-hero h2 {
            margin: 0 0 12px;
            font-size: 24px;
            font-weight: 700;
            color: var(--text-primary);
            letter-spacing: -0.5px;
          }
          .empty-hero p {
            margin: 0 0 32px;
            font-size: 15px;
            color: var(--text-muted);
            line-height: 1.6;
          }
          .hero-btn {
            display: inline-flex;
            align-items: center;
            gap: 10px;
            padding: 14px 28px;
            background: var(--accent);
            color: white;
            border: none;
            border-radius: var(--radius);
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            transition: all var(--transition);
            box-shadow: var(--shadow);
            letter-spacing: 0.3px;
          }
          .hero-btn:hover {
            background: var(--accent-600);
            transform: translateY(-2px);
            box-shadow: var(--shadow-glow);
          }
        `}
        </style>
      </div>
    );
  }

  return (
    <div className="chat-interface">
      <header className="chat-header glass">
        <div className="header-left">
          <div className="session-info">
            <h1 className="session-title">{session.title}</h1>
            <div className="session-meta">
              <span className={`status-chip ${status}`}>
                <span className={`chip-dot ${status}`}></span>
                {statusConfig.label}
              </span>
              <span className="meta-separator">•</span>
              <span className="meta-item">{messages.length} message{messages.length !== 1 ? 's' : ''}</span>
            </div>
          </div>
        </div>
        <div className="header-right">
          <div className="connection-status">
            <span className={`connection-dot ${isConnected ? 'connected' : 'disconnected'}`}></span>
            <span>{isConnected ? 'Connected' : 'Offline'}</span>
          </div>
          <button 
            className="icon-btn glass"
            onClick={clearMessages}
            title="Clear chat"
            disabled={messages.length === 0}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 6h18"></path>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"></path>
              <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
            </svg>
          </button>
        </div>
      </header>

      <main className="chat-messages" ref={messagesEndRef}>
        {messages.length === 0 ? (
          <div className="welcome-container">
            <div className="welcome-icon">
              <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"></path>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                <line x1="12" y1="19" x2="12" y2="22"></line>
              </svg>
            </div>
            <h3>Start talking</h3>
            <p>Press the microphone button to ask anything</p>
          </div>
        ) : (
          <div className="messages-list">
            {messages.map((msg) => (
              <div key={msg.id} className={`message-row ${msg.role}`}>
                <div className={`message-bubble ${msg.role} ${!msg.isComplete ? 'streaming' : ''}`}>
                  <div className="bubble-header">
                    <span className="bubble-role">
                      {msg.role === 'user' ? 'You' : 'Assistant'}
                    </span>
                    <span className="bubble-time">{formatTime(msg.timestamp)}</span>
                  </div>
                  <div className="bubble-content">
                    {msg.content}
                    {!msg.isComplete && (
                      <span className="streaming-indicator">
                        <span className="dot"></span>
                        <span className="dot"></span>
                        <span className="dot"></span>
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      <footer className="chat-footer glass">
        <div className="controls-container">
          <div className="visualizer-container">
            <div className="visualizer" ref={voiceVisualizerRef}>
              {[...Array(20)].map((_, i) => (
                <div key={i} className="visualizer-bar" style={{ animationDelay: `${i * 30}ms` }}></div>
              ))}
            </div>
          </div>

          <button
            className={`mic-button ${status}`}
            onClick={handleRecord}
            disabled={status === 'processing' || status === 'speaking'}
            aria-label={status === 'recording' ? 'Stop recording' : 'Start recording'}
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"></path>
              <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
              <line x1="12" y1="19" x2="12" y2="22"></line>
            </svg>
            {status === 'recording' && <span className="recording-ring"></span>}
          </button>

          <button
            className={`interrupt-btn glass ${status === 'speaking' || status === 'processing' ? 'active' : ''}`}
            onClick={handleInterrupt}
            disabled={status === 'idle' || status === 'recording'}
            aria-label="Interrupt"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="2" y="2" width="20" height="20" rx="4"></rect>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        {error && showError && (
          <div className="error-toast glass" onClick={() => setShowError(false)}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            <span>{error}</span>
            <button className="close-toast" onClick={(e) => { e.stopPropagation(); setShowError(false); }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </div>
        )}

        <style jsx>{`
          .chat-interface {
            display: flex;
            flex-direction: column;
            height: 100%;
            background: var(--bg-0);
          }
          .chat-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 20px 24px;
            border-bottom: 1px solid var(--border);
            background: var(--surface-1);
            backdrop-filter: blur(12px);
          }
          .header-left {
            display: flex;
            flex: 1;
            min-width: 0;
          }
          .session-info {
            display: flex;
            flex-direction: column;
            gap: 6px;
          }
          .session-title {
            margin: 0;
            font-size: 17px;
            font-weight: 600;
            color: var(--text-primary);
            letter-spacing: -0.3px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }
          .session-meta {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
            color: var(--text-muted);
          }
          .status-chip {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: var(--radius-full);
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.3px;
            text-transform: uppercase;
          }
          .status-chip.recording {
            background: var(--error-bg);
            color: var(--error);
          }
          .status-chip.processing,
          .status-chip.connecting {
            background: var(--warning-bg);
            color: var(--warning);
          }
          .status-chip.speaking {
            background: var(--success-bg);
            color: var(--success);
          }
          .status-chip.idle {
            background: var(--surface-2);
            color: var(--text-secondary);
          }
          .chip-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
          }
          .chip-dot.recording {
            background: var(--error);
            animation: chipPulse 1.2s ease-in-out infinite;
          }
          .chip-dot.processing,
          .chip-dot.connecting {
            background: var(--warning);
            animation: chipPulse 0.8s ease-in-out infinite;
          }
          .chip-dot.speaking {
            background: var(--success);
          }
          .chip-dot.idle {
            background: var(--text-muted);
          }
          @keyframes chipPulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.5; transform: scale(1.3); }
          }
          .meta-separator {
            color: var(--text-faint);
          }
          .meta-item {
            color: var(--text-muted);
          }
          .header-right {
            display: flex;
            align-items: center;
            gap: 12px;
          }
          .connection-status {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            font-weight: 500;
            color: var(--text-muted);
          }
          .connection-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
          }
          .connection-dot.connected {
            background: var(--success);
            box-shadow: 0 0 12px var(--success);
          }
          .connection-dot.disconnected {
            background: var(--error);
          }
          .icon-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 40px;
            height: 40px;
            border: none;
            border-radius: var(--radius);
            background: var(--surface-2);
            color: var(--text-secondary);
            cursor: pointer;
            transition: all var(--transition);
          }
          .icon-btn:hover:not(:disabled) {
            background: var(--surface-1);
            color: var(--text-primary);
            transform: translateY(-1px);
          }
          .icon-btn:disabled {
            opacity: 0.4;
            cursor: not-allowed;
          }
          .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 24px;
            display: flex;
            flex-direction: column;
          }
          .welcome-container {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            color: var(--text-muted);
          }
          .welcome-icon {
            width: 100px;
            height: 100px;
            border-radius: var(--radius-xl);
            background: var(--surface-2);
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--text-muted);
            margin-bottom: 24px;
          }
          .welcome-icon svg {
            width: 40px;
            height: 40px;
            opacity: 0.4;
          }
          .welcome-container h3 {
            margin: 0 0 8px;
            font-size: 20px;
            font-weight: 600;
            color: var(--text-primary);
          }
          .welcome-container p {
            margin: 0;
            font-size: 14px;
            color: var(--text-muted);
          }
          .messages-list {
            display: flex;
            flex-direction: column;
            gap: 16px;
            max-width: 800px;
            margin: 0 auto;
            width: 100%;
          }
          .message-row {
            display: flex;
            width: 100%;
          }
          .message-row.user {
            justify-content: flex-end;
          }
          .message-row.assistant {
            justify-content: flex-start;
          }
          .message-bubble {
            max-width: 75%;
            padding: 14px 18px;
            border-radius: var(--radius-lg);
            background: var(--surface-2);
            backdrop-filter: blur(8px);
            transition: all var(--transition);
          }
          .message-bubble.user {
            background: var(--accent);
            color: white;
            border-bottom-right-radius: var(--radius-sm);
            box-shadow: var(--shadow);
          }
          .message-bubble.assistant {
            background: var(--surface-2);
            border: 1px solid var(--border-light);
            border-bottom-left-radius: var(--radius-sm);
          }
          .message-bubble.streaming {
            border-left: 2px solid var(--accent);
          }
          .bubble-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            margin-bottom: 6px;
            font-size: 11px;
          }
          .bubble-role {
            font-weight: 600;
            color: var(--text-secondary);
            text-transform: capitalize;
          }
          .message-bubble.user .bubble-role {
            color: rgba(255, 255, 255, 0.8);
          }
          .bubble-time {
            color: var(--text-faint);
            font-size: 10px;
          }
          .message-bubble.user .bubble-time {
            color: rgba(255, 255, 255, 0.6);
          }
          .bubble-content {
            font-size: 14px;
            line-height: 1.6;
            color: var(--text-primary);
            display: inline-flex;
            align-items: baseline;
            gap: 4px;
          }
          .streaming-indicator {
            display: inline-flex;
            align-items: center;
            gap: 3px;
            margin-left: 4px;
          }
          .streaming-indicator .dot {
            width: 5px;
            height: 5px;
            border-radius: 50%;
            background: var(--accent);
            animation: dotBounce 1.2s ease-in-out infinite;
          }
          .streaming-indicator .dot:nth-child(2) {
            animation-delay: 0.15s;
          }
          .streaming-indicator .dot:nth-child(3) {
            animation-delay: 0.3s;
          }
          @keyframes dotBounce {
            0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
            30% { transform: translateY(-6px); opacity: 1; }
          }
          .chat-footer {
            padding: 20px 24px;
            border-top: 1px solid var(--border);
            background: var(--surface-1);
            backdrop-filter: blur(12px);
          }
          .controls-container {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 20px;
            max-width: 400px;
            margin: 0 auto;
          }
          .visualizer-container {
            flex: 1;
            max-width: 100px;
          }
          .visualizer {
            display: flex;
            align-items: flex-end;
            gap: 3px;
            height: 36px;
          }
          .visualizer-bar {
            flex: 1;
            background: linear-gradient(180deg, var(--accent), var(--accent-600));
            border-radius: 2px;
            height: 12%;
            transition: height 0.1s ease;
          }
          .mic-button {
            position: relative;
            display: flex;
            align-items: center;
            justify-content: center;
            width: 72px;
            height: 72px;
            border: none;
            border-radius: 50%;
            background: var(--surface-2);
            color: var(--text-secondary);
            cursor: pointer;
            transition: all var(--transition);
            box-shadow: var(--shadow);
          }
          .mic-button:hover:not(:disabled) {
            background: var(--accent);
            color: white;
            transform: scale(1.05);
            box-shadow: var(--shadow-glow);
          }
          .mic-button.recording {
            background: var(--error);
            color: white;
            animation: recordingPulse 1.5s ease-in-out infinite;
          }
          @keyframes recordingPulse {
            0%, 100% { box-shadow: 0 0 0 0 var(--error); }
            50% { box-shadow: 0 0 0 20px transparent; }
          }
          .mic-button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
          }
          .recording-ring {
            position: absolute;
            width: 100%;
            height: 100%;
            border-radius: 50%;
            border: 3px solid var(--error);
            animation: ringPulse 1.5s ease-out infinite;
          }
          @keyframes ringPulse {
            0% { transform: scale(1); opacity: 1; }
            100% { transform: scale(1.6); opacity: 0; }
          }
          .interrupt-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 48px;
            height: 48px;
            border: none;
            border-radius: 50%;
            background: var(--surface-2);
            color: var(--error);
            cursor: pointer;
            transition: all var(--transition);
            opacity: 0;
            pointer-events: none;
          }
          .interrupt-btn.active {
            opacity: 1;
            pointer-events: auto;
          }
          .interrupt-btn:hover {
            background: var(--error);
            color: white;
            transform: scale(1.1);
          }
          .interrupt-btn:disabled {
            opacity: 0.4;
            cursor: not-allowed;
          }
          .error-toast {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 12px 18px;
            margin: 0 auto 16px;
            max-width: 400px;
            background: var(--error-bg);
            border: 1px solid var(--error-border);
            border-radius: var(--radius);
            color: var(--error);
            font-size: 13px;
            cursor: pointer;
            animation: slideDown 0.3s ease;
          }
          @keyframes slideDown {
            from { opacity: 0; transform: translateY(-10px); }
            to { opacity: 1; transform: translateY(0); }
          }
          .close-toast {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 20px;
            height: 20px;
            border: none;
            background: transparent;
            color: currentColor;
            cursor: pointer;
            opacity: 0.7;
            transition: opacity var(--transition);
          }
          .close-toast:hover {
            opacity: 1;
          }
        `}
      </style>
      </footer>
    </div>
  );
};