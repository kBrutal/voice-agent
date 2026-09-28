import React, { Fragment, useEffect, useRef, useState } from 'react';
import { AgentStep, Message, useVoiceWebSocket } from '../hooks/useVoiceWebSocket';
import { DEFAULT_SESSION_TITLE, Session } from '../hooks/useSessions';
import {
  AlertIcon,
  ChevronDownIcon,
  CloseIcon,
  DocumentIcon,
  GlobeIcon,
  MenuIcon,
  MicIcon,
  ResetIcon,
  SearchIcon,
  SparkleIcon,
  StopIcon
} from './Icons';

interface ChatInterfaceProps {
  session: Session;
  onOpenSidebar: () => void;
  onSessionUpdate: (updates: { messageCount?: number; title?: string }) => void;
}

const formatTime = (date: Date) =>
  date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });

function countResults(content: string): number {
  return content.split('\n').filter(line => /^\d+\./.test(line.trim())).length;
}

function AgentActivity({ steps }: { steps: AgentStep[] }) {
  const toolSteps = steps.filter(s => s.kind === 'tool_call' || s.kind === 'tool_result');
  const searches = toolSteps.filter(s => s.kind === 'tool_call').length;
  if (searches === 0) return null;

  const done = steps.some(s => s.kind === 'finish');

  return (
    <details className="activity" open={!done}>
      <summary className="activity__summary">
        {done ? <GlobeIcon /> : <span className="spinner" aria-hidden="true" />}
        <span>
          {done
            ? `Searched the web · ${searches} ${searches === 1 ? 'query' : 'queries'}`
            : 'Searching the web…'}
        </span>
        <ChevronDownIcon className="activity__chevron" />
      </summary>
      <ul className="activity__list">
        {toolSteps.map(step => {
          if (step.kind === 'tool_call') {
            const query = String(step.toolArgs?.query ?? step.content);
            return (
              <li key={step.id} className="activity__item">
                <SearchIcon />
                <span>Searched <span className="activity__query">“{query}”</span></span>
              </li>
            );
          }
          const n = countResults(step.content);
          return (
            <li key={step.id} className="activity__item activity__item--result">
              <DocumentIcon />
              <span>{n > 0 ? `Read ${n} ${n === 1 ? 'result' : 'results'}` : step.content.slice(0, 120)}</span>
            </li>
          );
        })}
      </ul>
    </details>
  );
}

function MessageRow({ message }: { message: Message }) {
  if (message.role === 'user') {
    return (
      <div className="msg msg--user">
        <div className="msg__col">
          <div className="msg__bubble">{message.content}</div>
          <span className="msg__time">{formatTime(message.timestamp)}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="msg msg--assistant">
      <div className="msg__avatar"><SparkleIcon /></div>
      <div className="msg__body">
        <div className="msg__text">
          {message.content}
          {!message.isComplete && (
            <span className="typing" aria-label="Assistant is responding">
              <span /><span /><span />
            </span>
          )}
        </div>
        {message.isComplete && <span className="msg__time">{formatTime(message.timestamp)}</span>}
      </div>
    </div>
  );
}

type WaveMode = 'idle' | 'recording' | 'speaking';

function Waveform({ side, mode }: { side: 'left' | 'right'; mode: WaveMode }) {
  const bars = 14;
  return (
    <div className={`wave wave--${side} wave--${mode}`} aria-hidden="true">
      {Array.from({ length: bars }, (_, i) => {
        const distance = side === 'left' ? bars - 1 - i : i;
        return (
          <span
            key={i}
            style={{
              animationDelay: `${(distance * 97) % 700}ms`,
              animationDuration: `${700 + ((distance * 53) % 500)}ms`,
              opacity: 1 - distance * 0.05
            }}
          />
        );
      })}
    </div>
  );
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  session,
  onOpenSidebar,
  onSessionUpdate
}) => {
  const {
    isConnected,
    messages,
    status,
    error,
    agentSteps,
    voicePending,
    startRecording,
    stopRecording,
    interrupt,
    clearMessages
  } = useVoiceWebSocket(session.id);

  const [showError, setShowError] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, agentSteps]);

  useEffect(() => {
    if (messages.length === session.messageCount) return;

    const updates: { messageCount?: number; title?: string } = { messageCount: messages.length };
    const firstUserMessage = messages.find(m => m.role === 'user');
    if (firstUserMessage && session.title === DEFAULT_SESSION_TITLE) {
      updates.title = firstUserMessage.content.slice(0, 60);
    }
    onSessionUpdate(updates);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages.length]);

  useEffect(() => {
    if (!error) return;
    setShowError(true);
    const timer = setTimeout(() => setShowError(false), 5000);
    return () => clearTimeout(timer);
  }, [error]);

  const isBusy = status === 'processing' || status === 'speaking';
  const lastUserIndex = messages.map(m => m.role).lastIndexOf('user');
  const lastStep = agentSteps[agentSteps.length - 1];

  const hint = !isConnected
    ? 'Connecting to server…'
    : status === 'recording'
      ? 'Listening — tap to send'
      : status === 'processing'
        ? (voicePending
          ? 'Preparing voice…'
          : lastStep?.kind === 'tool_call' ? 'Searching the web…' : 'Thinking…')
        : status === 'speaking'
          ? 'Speaking'
          : status === 'error'
            ? 'Something went wrong — tap to try again'
            : 'Tap to speak';

  const waveMode: WaveMode = status === 'recording' ? 'recording' : status === 'speaking' ? 'speaking' : 'idle';

  const handleMicClick = () => {
    if (status === 'recording') stopRecording();
    else startRecording();
  };

  return (
    <section className="chat">
      <header className="topbar">
        <button className="icon-btn topbar__menu" onClick={onOpenSidebar} aria-label="Open conversations">
          <MenuIcon />
        </button>
        <h1 className="topbar__title">{session.title}</h1>
        <div className="topbar__right">
          <span className={`conn ${isConnected ? 'conn--on' : ''}`}>
            <span className="conn__dot" />
            <span className="conn__label">{isConnected ? 'Connected' : 'Offline'}</span>
          </span>
          <button
            className="icon-btn"
            onClick={clearMessages}
            disabled={messages.length === 0 || isBusy}
            title="Clear conversation"
            aria-label="Clear conversation"
          >
            <ResetIcon />
          </button>
        </div>
      </header>

      <div className="chat__scroll">
        <div className="chat__column">
          {messages.length === 0 ? (
            <div className="chat-empty">
              <div className="orb" aria-hidden="true" />
              <h2 className="display">What's on your mind?</h2>
              <p className="chat-empty__text">
                Tap the microphone and start talking. I'll search the web when I need something current.
              </p>
            </div>
          ) : (
            messages.map((message, index) => (
              <Fragment key={message.id}>
                <MessageRow message={message} />
                {index === lastUserIndex && <AgentActivity steps={agentSteps} />}
              </Fragment>
            ))
          )}
          <div ref={endRef} />
        </div>
      </div>

      <footer className="dock">
        {error && showError && (
          <div className="toast" role="alert">
            <AlertIcon />
            <span className="toast__text">{error}</span>
            <button className="icon-btn toast__close" onClick={() => setShowError(false)} aria-label="Dismiss">
              <CloseIcon />
            </button>
          </div>
        )}

        <div className="dock__inner">
          <Waveform side="left" mode={waveMode} />
          <button
            className={`mic mic--${isConnected ? status : 'offline'}`}
            onClick={handleMicClick}
            disabled={!isConnected || isBusy}
            aria-label={status === 'recording' ? 'Stop and send' : 'Start speaking'}
          >
            {status === 'recording' ? <StopIcon /> : <MicIcon />}
          </button>
          <Waveform side="right" mode={waveMode} />
        </div>

        <div className="dock__hint" aria-live="polite">
          <span>{hint}</span>
          {isBusy && (
            <button className="pill-btn" onClick={interrupt}>
              <StopIcon />
              Stop
            </button>
          )}
        </div>
      </footer>
    </section>
  );
};
