#!/usr/bin/env python3
"""
Voice Assistant CLI Client

Records audio from microphone, sends to WebSocket server,
receives and plays back the response.
"""

import asyncio
import base64
import json
import sys
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path

import pyaudio
import websockets


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1024  # frames per buffer
    format: int = pyaudio.paInt16
    record_seconds: float = 10.0  # max recording time


class AudioPlayer:
    """Plays audio chunks using PyAudio."""
    
    def __init__(self, config: AudioConfig):
        self.config = config
        self.pa = pyaudio.PyAudio()
        self.stream = None
        
    def start(self):
        self.stream = self.pa.open(
            format=self.config.format,
            channels=self.config.channels,
            rate=self.config.sample_rate,
            output=True,
            frames_per_buffer=self.config.chunk_size,
        )
        
    def play_chunk(self, data: bytes):
        if self.stream:
            self.stream.write(data)
            
    def stop(self):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.pa.terminate()


class AudioRecorder:
    """Records audio from microphone."""
    
    def __init__(self, config: AudioConfig):
        self.config = config
        self.pa = pyaudio.PyAudio()
        self.stream = None
        self.frames = []
        self.recording = False
        
    def start(self):
        self.frames = []
        self.stream = self.pa.open(
            format=self.config.format,
            channels=self.config.channels,
            rate=self.config.sample_rate,
            input=True,
            frames_per_buffer=self.config.chunk_size,
            stream_callback=self._callback,
        )
        self.recording = True
        self.stream.start_stream()
        
    def _callback(self, in_data, frame_count, time_info, status):
        if self.recording:
            self.frames.append(in_data)
        return (in_data, pyaudio.paContinue)
        
    def stop(self) -> bytes:
        self.recording = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.pa.terminate()
        return b''.join(self.frames)
    
    def save_wav(self, filepath: str):
        """Save recorded audio to WAV file."""
        data = b''.join(self.frames)
        with wave.open(filepath, 'wb') as wf:
            wf.setnchannels(self.config.channels)
            wf.setsampwidth(self.pa.get_sample_size(self.config.format))
            wf.setframerate(self.config.sample_rate)
            wf.writeframes(data)


class VoiceAssistantClient:
    """WebSocket client for Voice Assistant."""
    
    def __init__(
        self,
        server_url: str = "ws://localhost:8000",
        audio_config: AudioConfig | None = None,
    ):
        self.server_url = server_url.rstrip('/')
        self.session_id = f"cli_{uuid.uuid4().hex[:8]}"
        self.ws_url = f"{self.server_url}/ws/{self.session_id}"
        self.config = audio_config or AudioConfig()
        self.recorder = AudioRecorder(self.config)
        self.player = AudioPlayer(self.config)
        self.websocket = None
        self.response_audio = bytearray()
        self.transcript = ""
        self.response_text = ""
        
    async def connect(self):
        print(f"Connecting to {self.ws_url}...")
        self.websocket = await websockets.connect(self.ws_url)
        
        # Send config
        await self.websocket.send(json.dumps({
            "type": "config",
            "sample_rate": self.config.sample_rate,
            "channels": self.config.channels,
        }))
        print("Connected!")
        
    async def disconnect(self):
        if self.websocket:
            await self.websocket.close()
            
    async def send_audio(self, audio_data: bytes):
        """Send audio data as base64 chunks."""
        # Send in chunks to avoid large messages
        chunk_size = 16384
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i + chunk_size]
            await self.websocket.send(json.dumps({
                "type": "audio_chunk",
                "data": base64.b64encode(chunk).decode(),
            }))
        # Signal end of audio
        await self.websocket.send(json.dumps({"type": "audio_end"}))
        
    async def listen(self):
        """Listen for server messages."""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                await self._handle_message(data)
        except websockets.exceptions.ConnectionClosed:
            print("\nConnection closed by server")
            
    async def _handle_message(self, message: dict):
        msg_type = message.get("type")
        
        if msg_type == "transcript":
            self.transcript = message.get("text", "")
            print(f"\n📝 You said: {self.transcript}")
            
        elif msg_type == "response_text":
            self.response_text = message.get("text", "")
            print(f"🤖 Assistant: {self.response_text}")
            
        elif msg_type == "audio_chunk":
            audio_b64 = message.get("data", "")
            is_final = message.get("is_final", False)
            audio_bytes = base64.b64decode(audio_b64)
            self.response_audio.extend(audio_bytes)
            self.player.play_chunk(audio_bytes)
            
            if is_final:
                print("🔊 Playback complete")
                
        elif msg_type == "status":
            status = message.get("message", "")
            print(f"⏳ {status}")
            
        elif msg_type == "error":
            error = message.get("message", "Unknown error")
            print(f"❌ Error: {error}")
            
        elif msg_type == "audio_end":
            print("✅ Response complete")
            
    async def run_conversation(self):
        """Run a single conversation turn."""
        print("\n" + "="*50)
        print("🎤 Press Enter to start recording...")
        print("   (Recording will auto-stop after silence or max duration)")
        input()
        
        print("🔴 Recording... Speak now!")
        print("   Press Enter to stop early")
        
        # Start recording in background
        self.recorder.start()
        self.player.start()
        
        # Wait for Enter key or timeout
        stop_event = asyncio.Event()
        
        def wait_for_enter():
            input()
            stop_event.set()
            
        # Run input in executor to not block
        loop = asyncio.get_event_loop()
        input_task = loop.run_in_executor(None, wait_for_enter)
        
        # Wait for either Enter or max duration
        done, pending = await asyncio.wait(
            [input_task, asyncio.create_task(asyncio.sleep(self.config.record_seconds))],
            return_when=asyncio.FIRST_COMPLETED,
        )
        
        # Cancel pending
        for task in pending:
            task.cancel()
            
        # Stop recording
        audio_data = self.recorder.stop()
        print("⏹️  Recording stopped")
        
        if not audio_data:
            print("⚠️  No audio recorded")
            return
            
        # Send audio to server
        print("📤 Sending audio...")
        await self.send_audio(audio_data)
        
        # Listen for response
        await self.listen()
        
        # Save conversation for debugging
        self._save_debug_files(audio_data)
        
    def _save_debug_files(self, input_audio: bytes):
        """Save input/output audio for debugging."""
        debug_dir = Path("/tmp/voice_assistant_debug")
        debug_dir.mkdir(exist_ok=True)
        
        # Save input
        with wave.open(str(debug_dir / "input.wav"), 'wb') as wf:
            wf.setnchannels(self.config.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.config.sample_rate)
            wf.writeframes(input_audio)
            
        # Save output
        if self.response_audio:
            with wave.open(str(debug_dir / "output.wav"), 'wb') as wf:
                wf.setnchannels(self.config.channels)
                wf.setsampwidth(2)
                wf.setframerate(self.config.sample_rate)
                wf.writeframes(self.response_audio)
                
        print(f"💾 Debug files saved to {debug_dir}")


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Voice Assistant CLI Client")
    parser.add_argument(
        "--server",
        default="ws://localhost:8000",
        help="WebSocket server URL (default: ws://localhost:8000)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
        help="Max recording duration in seconds (default: 10)",
    )
    parser.add_argument(
        "--rate",
        type=int,
        default=16000,
        help="Sample rate (default: 16000)",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuous conversation loop",
    )
    
    args = parser.parse_args()
    
    config = AudioConfig(
        sample_rate=args.rate,
        record_seconds=args.duration,
    )
    
    client = VoiceAssistantClient(args.server, config)
    
    try:
        await client.connect()
        
        if args.loop:
            print("\n🔄 Continuous mode - Press Ctrl+C to exit")
            while True:
                await client.run_conversation()
        else:
            await client.run_conversation()
            
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    finally:
        await client.disconnect()
        client.player.stop()


if __name__ == "__main__":
    asyncio.run(main())