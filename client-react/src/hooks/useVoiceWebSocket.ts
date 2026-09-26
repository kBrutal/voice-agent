import { useState, useEffect, useRef, useCallback } from 'react';

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  audioUrl?: string;
  isComplete?: boolean;
}

interface Session {
  id: string;
  title: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
}

interface WebSocketMessage {
  type: 'audio_chunk' | 'audio_end' | 'transcript' | 'response_text' | 'response_chunk' | 'audio_chunk_response' | 'audio_end_response' | 'status' | 'error' | 'config' | 'interrupt' | 'ping' | 'pong';
  data?: string;
  text?: string;
  message?: string;
  is_final?: boolean;
}

export function useVoiceWebSocket(sessionId: string | null) {
  const [isConnected, setIsConnected] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [status, setStatus] = useState<'idle' | 'connecting' | 'recording' | 'processing' | 'speaking' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);
  
  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);

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
        setMessages(prev => [...prev, {
          id: crypto.randomUUID(),
          role: 'user',
          content: msg.text || '',
          timestamp: new Date()
        }]);
        setStatus('processing');
        break;

      case 'response_text':
        // Full response (fallback/compatibility)
        setMessages(prev => [...prev, {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: msg.text || '',
          timestamp: new Date(),
          isComplete: true
        }]);
        setStatus('speaking');
        break;

      case 'response_chunk':
        // Streaming text chunk - append to last assistant message or create new
        setMessages(prev => {
          const lastMsg = prev[prev.length - 1];
          if (lastMsg && lastMsg.role === 'assistant' && !lastMsg.isComplete) {
            return [
              ...prev.slice(0, -1),
              { ...lastMsg, content: lastMsg.content + (msg.text || ''), isComplete: msg.is_final || false }
            ];
          } else {
            return [...prev, {
              id: crypto.randomUUID(),
              role: 'assistant',
              content: msg.text || '',
              timestamp: new Date(),
              isComplete: msg.is_final || false
            }];
          }
        });
        if (!msg.is_final) {
          setStatus('speaking');
        }
        break;

      case 'audio_chunk':
        // Accumulate audio chunks
        if (msg.data) {
          accumulateAudioChunk(msg.data, msg.is_final || false);
        }
        break;

      case 'audio_end':
        // Play accumulated audio and mark message complete
        playAccumulatedAudio();
        setStatus('idle');
        setMessages(prev => {
          const lastMsg = prev[prev.length - 1];
          if (lastMsg && lastMsg.role === 'assistant' && !lastMsg.isComplete) {
            return [...prev.slice(0, -1), { ...lastMsg, isComplete: true }];
          }
          return prev;
        });
        break;

      case 'status':
        const statusMsg = msg.message?.toLowerCase().replace(/\s+/g, '_') || '';
        if (statusMsg.includes('process') || statusMsg.includes('generat') || statusMsg.includes('synthes') || statusMsg.includes('stream')) {
          setStatus('processing');
        } else if (statusMsg === 'speaking') {
          setStatus('speaking');
        } else if (statusMsg === 'ready' || statusMsg === 'idle') {
          setStatus('idle');
        }
        break;

      case 'error':
        setError(msg.message || 'Unknown error');
        setStatus('error');
        setTimeout(() => setStatus('idle'), 3000);
        break;
    }
  }, []);

  // Accumulate audio chunks
  const accumulatedAudioRef = useRef<Uint8Array[]>([]);
  
  const accumulateAudioChunk = useCallback((base64Data: string, isFinal: boolean) => {
    const binaryString = atob(base64Data);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    
    accumulatedAudioRef.current.push(bytes);
    
    if (isFinal) {
      playAccumulatedAudio();
    }
  }, []);

  // Play accumulated audio as a single WAV file
  const playAccumulatedAudio = useCallback(async () => {
    if (accumulatedAudioRef.current.length === 0) return;
    
    // Combine all chunks
    const totalLength = accumulatedAudioRef.current.reduce((sum, chunk) => sum + chunk.length, 0);
    const combined = new Uint8Array(totalLength);
    let offset = 0;
    for (const chunk of accumulatedAudioRef.current) {
      combined.set(chunk, offset);
      offset += chunk.length;
    }
    
    // Clear accumulation for next playback
    accumulatedAudioRef.current = [];
    
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 22050 });
    }
    
    try {
      // Decode the complete WAV file
      const audioBuffer = await audioContextRef.current.decodeAudioData(combined.buffer);
      const source = audioContextRef.current.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(audioContextRef.current.destination);
      currentAudioRef.current = source as any; // Store reference for interrupt
      
      source.start(0);
      
      await new Promise(resolve => {
        source.onended = resolve;
      });
      
      currentAudioRef.current = null;
    } catch (e) {
      console.error('Audio decode error:', e);
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

    // Stop current audio playback
    if (currentAudioRef.current) {
      try {
        (currentAudioRef.current as any).stop();
      } catch {
        (currentAudioRef.current as any).pause();
        (currentAudioRef.current as any).currentTime = 0;
      }
      currentAudioRef.current = null;
    }

    // Clear accumulated audio
    accumulatedAudioRef.current = [];

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
    startRecording,
    stopRecording,
    interrupt,
    sendText,
    clearMessages: () => setMessages([])
  };
}