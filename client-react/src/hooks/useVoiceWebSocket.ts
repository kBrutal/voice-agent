import { useState, useEffect, useRef, useCallback } from 'react';
import { messagesStorageKey } from './useSessions';

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  audioUrl?: string;
  isComplete?: boolean;
}

function loadMessages(sessionId: string | null): Message[] {
  if (!sessionId) return [];
  try {
    const stored = localStorage.getItem(messagesStorageKey(sessionId));
    if (!stored) return [];
    return JSON.parse(stored).map((m: Message) => ({
      ...m,
      timestamp: new Date(m.timestamp),
      isComplete: true
    }));
  } catch {
    return [];
  }
}

function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

interface WebSocketMessage {
  type: 'audio_segment' | 'audio_end' | 'transcript' | 'status' | 'error' | 'ping' | 'pong' | 'agent_step';
  data?: string;
  text?: string;
  message?: string;
  index?: number;
  is_last?: boolean;
  kind?: 'reason' | 'tool_call' | 'tool_result' | 'finish';
  content?: string;
  tool_name?: string;
  tool_args?: Record<string, unknown>;
}

export interface AgentStep {
  id: string;
  kind: 'reason' | 'tool_call' | 'tool_result' | 'finish';
  content: string;
  toolName?: string;
  toolArgs?: Record<string, unknown>;
  timestamp: Date;
}

export function useVoiceWebSocket(sessionId: string | null) {
  const [isConnected, setIsConnected] = useState(false);
  const [messages, setMessages] = useState<Message[]>(() => loadMessages(sessionId));
  const [status, setStatus] = useState<'idle' | 'connecting' | 'recording' | 'processing' | 'speaking' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [agentSteps, setAgentSteps] = useState<AgentStep[]>([]);
  const [voicePending, setVoicePending] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    try {
      localStorage.setItem(messagesStorageKey(sessionId), JSON.stringify(messages));
    } catch (e) {
      console.error('Failed to save messages:', e);
    }
  }, [sessionId, messages]);

  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);

  // Reply audio arrives as a sequence of WAV segments; they're decoded in order
  // and scheduled back to back. `playbackGenRef` invalidates in-flight decodes
  // after an interrupt so stale segments never start playing.
  const playChainRef = useRef<Promise<void>>(Promise.resolve());
  const activeSourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const nextStartTimeRef = useRef(0);
  const serverDoneRef = useRef(true);
  const playbackGenRef = useRef(0);
  const textTimersRef = useRef<number[]>([]);

  const appendAssistantWord = (word: string) => {
    setMessages(prev => {
      const last = prev[prev.length - 1];
      if (last && last.role === 'assistant' && !last.isComplete) {
        return [...prev.slice(0, -1), { ...last, content: `${last.content} ${word}` }];
      }
      return [...prev, {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: word,
        timestamp: new Date(),
        isComplete: false
      }];
    });
  };

  const completeAssistantMessage = () => {
    setMessages(prev => {
      const last = prev[prev.length - 1];
      if (last && last.role === 'assistant' && !last.isComplete) {
        return [...prev.slice(0, -1), { ...last, isComplete: true }];
      }
      return prev;
    });
  };

  const getAudioContext = () => {
    if (!audioContextRef.current) {
      audioContextRef.current = new AudioContext();
    }
    return audioContextRef.current;
  };

  const resetPlayback = () => {
    playbackGenRef.current += 1;
    activeSourcesRef.current.forEach(source => {
      try {
        source.stop();
      } catch {
        // already stopped
      }
    });
    activeSourcesRef.current = [];
    textTimersRef.current.forEach(timer => clearTimeout(timer));
    textTimersRef.current = [];
    nextStartTimeRef.current = 0;
    playChainRef.current = Promise.resolve();
  };

  const enqueuePlayback = (task: (generation: number) => Promise<void>) => {
    const generation = playbackGenRef.current;
    playChainRef.current = playChainRef.current
      .then(() => (generation === playbackGenRef.current ? task(generation) : undefined))
      .catch(e => console.error('Audio playback error:', e));
  };

  const scheduleSegment = async (base64Wav: string, text: string, isLast: boolean, generation: number) => {
    const ctx = getAudioContext();
    await ctx.resume();
    const buffer = await ctx.decodeAudioData(base64ToArrayBuffer(base64Wav));
    if (generation !== playbackGenRef.current) return;

    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    const startAt = Math.max(ctx.currentTime + 0.05, nextStartTimeRef.current);
    source.start(startAt);
    nextStartTimeRef.current = startAt + buffer.duration;
    activeSourcesRef.current.push(source);

    // Reveal each word when the voice should be reaching it, estimated by
    // the word's character position within this segment's audio duration.
    const startDelayMs = (startAt - ctx.currentTime) * 1000;
    const durationMs = buffer.duration * 1000;
    const words = text.split(/\s+/).filter(Boolean);
    const totalChars = Math.max(text.length, 1);
    let offset = 0;
    for (const word of words) {
      const delay = startDelayMs + durationMs * (offset / totalChars);
      textTimersRef.current.push(window.setTimeout(() => appendAssistantWord(word), delay));
      offset += word.length + 1;
    }
    textTimersRef.current.push(window.setTimeout(() => {
      setStatus('speaking');
      setVoicePending(false);
    }, startDelayMs));
    if (isLast) {
      textTimersRef.current.push(window.setTimeout(completeAssistantMessage, startDelayMs + durationMs));
    }

    source.onended = () => {
      activeSourcesRef.current = activeSourcesRef.current.filter(s => s !== source);
      if (activeSourcesRef.current.length === 0 && serverDoneRef.current) {
        setStatus('idle');
      }
    };
  };

  // Initialize WebSocket
  useEffect(() => {
    if (!sessionId) return;

    const wsUrl = `ws://${window.location.host}/ws/${sessionId}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('WebSocket connected');
      setIsConnected(true);
      setError(null);
      
      // Send config
      ws.send(JSON.stringify({
        type: 'config',
        sample_rate: 16000,
        channels: 1
      }));
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setIsConnected(false);
      if (status !== 'processing' && status !== 'speaking') {
        setTimeout(() => {
          if (wsRef.current?.readyState === WebSocket.CLOSED) {
            // Could reconnect here if needed
          }
        }, 3000);
      }
    };

    ws.onerror = (err) => {
      console.error('WebSocket error:', err);
      setError('Connection error');
    };

    ws.onmessage = (event) => {
      try {
        const msg: WebSocketMessage = JSON.parse(event.data);
        handleMessage(msg);
      } catch (e) {
        console.error('Failed to parse message:', e);
      }
    };

    return () => {
      ws.close();
    };
  }, [sessionId]);

  const handleMessage = useCallback((msg: WebSocketMessage) => {
    switch (msg.type) {
      case 'transcript':
        resetPlayback();
        serverDoneRef.current = false;
        setVoicePending(false);
        setAgentSteps([]);
        setMessages(prev => [...prev, {
          id: crypto.randomUUID(),
          role: 'user',
          content: msg.text || '',
          timestamp: new Date()
        }]);
        setStatus('processing');
        break;

      case 'agent_step':
        setAgentSteps(prev => [...prev, {
          id: crypto.randomUUID(),
          kind: msg.kind || 'reason',
          content: msg.content || '',
          toolName: msg.tool_name,
          toolArgs: msg.tool_args,
          timestamp: new Date()
        }]);
        break;

      case 'audio_segment':
        if (msg.data) {
          const data = msg.data;
          const text = msg.text || '';
          const isLast = msg.is_last ?? false;
          enqueuePlayback(generation => scheduleSegment(data, text, isLast, generation));
        }
        break;

      case 'audio_end':
        enqueuePlayback(async () => {
          serverDoneRef.current = true;
          if (activeSourcesRef.current.length === 0) setStatus('idle');
        });
        break;

      case 'status': {
        const statusMsg = msg.message?.toLowerCase() || '';
        if (['process', 'generat', 'convert'].some(k => statusMsg.includes(k))) {
          setStatus('processing');
        } else if (statusMsg.includes('synthes')) {
          setVoicePending(true);
        }
        break;
      }

      case 'error':
        setError(msg.message || 'Unknown error');
        setStatus('error');
        setTimeout(() => setStatus('idle'), 3000);
        break;
    }
  }, []);

  const startRecording = useCallback(async () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setError('Not connected');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });

      audioChunksRef.current = [];
      mediaRecorderRef.current = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus'
      });

      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorderRef.current.onstop = () => {
        if (wsRef.current?.readyState === WebSocket.OPEN && audioChunksRef.current.length > 0) {
          const blob = new Blob(audioChunksRef.current, { type: 'audio/webm;codecs=opus' });
          const reader = new FileReader();
          reader.onloadend = () => {
            const base64data = reader.result?.split(',')[1];
            if (base64data) {
              wsRef.current?.send(JSON.stringify({
                type: 'audio_chunk',
                data: base64data
              }));
              wsRef.current?.send(JSON.stringify({ type: 'audio_end' }));
            }
          };
          reader.readAsDataURL(blob);
        }
      };

      mediaRecorderRef.current.start(100);
      setStatus('recording');
      setError(null);
    } catch (err) {
      console.error('Recording error:', err);
      setError('Microphone access denied');
    }
  }, []);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    setStatus('processing');
  }, []);

  const interrupt = useCallback(() => {
    // Stop recording
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }

    resetPlayback();
    serverDoneRef.current = true;
    setVoicePending(false);
    completeAssistantMessage();

    // Send interrupt to server
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'interrupt' }));
    }

    // Reset state
    setStatus('idle');
    setError(null);
  }, []);

  const sendText = useCallback((text: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(),
        role: 'user',
        content: text,
        timestamp: new Date()
      }]);
    }
  }, []);

  return {
    isConnected,
    messages,
    status,
    error,
    agentSteps,
    voicePending,
    startRecording,
    stopRecording,
    interrupt,
    sendText,
    clearMessages: () => setMessages([]),
    clearAgentSteps: () => setAgentSteps([])
  };
}