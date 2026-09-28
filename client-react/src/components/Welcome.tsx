import React from 'react';
import { MenuIcon, MicIcon } from './Icons';

interface WelcomeProps {
  onNewSession: () => void;
  onOpenSidebar: () => void;
}

export const Welcome: React.FC<WelcomeProps> = ({ onNewSession, onOpenSidebar }) => (
  <section className="chat">
    <header className="topbar topbar--bare">
      <button className="icon-btn topbar__menu" onClick={onOpenSidebar} aria-label="Open conversations">
        <MenuIcon />
      </button>
    </header>
    <div className="welcome">
      <div className="orb" aria-hidden="true" />
      <h1 className="display">Talk it through.</h1>
      <p className="welcome__text">
        A voice assistant that remembers your conversations and searches the web when it needs to.
      </p>
      <button className="btn-primary" onClick={onNewSession}>
        <MicIcon />
        Start a conversation
      </button>
    </div>
  </section>
);
