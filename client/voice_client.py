#!/usr/bin/env python3
"""
Voice Assistant Python Client Library

Reusable async client for integrating voice assistant into other applications.
"""

import asyncio
import base64
import json
import uuid
from dataclasses import dataclass
from typing import Callable, Optional

import websockets


@dataclass
class VoiceConfig:
    """Audio configuration."""
    sample_rate: int = 16000
    channels: int = 1


class VoiceAssistantClient:
    """
    Async client for Voice Assistant WebSocket API.
    
    Usage:
        client = VoiceAssistantClient("ws://localhost:8000")
        await client.connect()
        
        # Send audio bytes, get response
        transcript, response_text, response_audio = await client.process_audio(audio_bytes)
        
        await client.disconnect()
    """
    
    def __init__(
        self,
        server_url: str = "ws://localhost:8000",
        config: Optional[VoiceConfig] = None,
        session_id: Optional[str] = None,
    ):
        self.server_url = server_url.rstrip('/')
        self.session_id = session_id or f"client_{uuid.uuid4().hex[:8]}"
        self.ws_url = f"{self.server_url}/ws/{self.session_id}"
        self.config = config or VoiceConfig()
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = False
        
    @property
    def connected(self) -> bool:
        return self._connected and self.websocket is not None
        
    async def connect(self) -> None:
        """Establish WebSocket connection."""
        if self.connected:
            return
            
        self.websocket = await websockets.connect(self.ws_url)
        self._connected = True
        
        # Send audio config
        await self.websocket.send(json.dumps({
            "type": "config",
            "sample_rate": self.config.sample_rate,
            "channels": self.config.channels,
        }))
        
        # Wait for connection ack (optional)
        # response = await self.websocket.recv()
        
    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        self._connected = False
        
    async def process_audio(
        self,
        audio_data: bytes,
        language: str = "auto",
    ) -> tuple[str, str, bytes]:
        """
        Process audio through the full pipeline.
        
        Args:
            audio_data: Raw PCM audio bytes (16-bit, mono, 16kHz)
            language: ASR language hint
            
        Returns:
            Tuple of (transcript, response_text, response_audio_bytes)
        """
        if not self.connected:
            await self.connect()
            
        # Reset state
        transcript = ""
        response_text = ""
        response_audio = bytearray()
        completed = asyncio.Event()
        
        async def listener():
            nonlocal transcript, response_text, response_audio
            try:
                async for message in self.websocket:
                    data = json.loads(message)
                    msg_type = data.get("type")
                    
                    if msg_type == "transcript":
                        transcript = data.get("text", "")
                    elif msg_type == "response_text":
                        response_text = data.get("text", "")
                    elif msg_type == "audio_chunk":
                        chunk_b64 = data.get("data", "")
                        response_audio.extend(base64.b64decode(chunk_b64))
                        if data.get("is_final"):
                            completed.set()
                            break
                    elif msg_type == "error":
                        raise RuntimeError(f"Server error: {data.get('message')}")
                    elif msg_type == "audio_end":
                        completed.set()
                        break
            except websockets.exceptions.ConnectionClosed:
                pass
                
        # Start listener
        listen_task = asyncio.create_task(listener())
        
        try:
            # Send audio in chunks
            chunk_size = 16384
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i + chunk_size]
                await self.websocket.send(json.dumps({
                    "type": "audio_chunk",
                    "data": base64.b64encode(chunk).decode(),
                }))
                
            # Signal end
            await self.websocket.send(json.dumps({"type": "audio_end"}))
            
            # Wait for completion (with timeout)
            await asyncio.wait_for(completed.wait(), timeout=60.0)
            
        finally:
            listen_task.cancel()
            try:
                await listen_task
            except asyncio.CancelledError:
                pass
                
        return transcript, response_text, bytes(response_audio)
        
    async def send_audio_stream(
        self,
        audio_iterator,  # async iterator yielding bytes
    ) -> None:
        """Send streaming audio chunks."""
        if not self.connected:
            await self.connect()
            
        async for chunk in audio_iterator:
            await self.websocket.send(json.dumps({
                "type": "audio_chunk",
                "data": base64.b64encode(chunk).decode(),
            }))
            
        await self.websocket.send(json.dumps({"type": "audio_end"}))
        
    async def receive_messages(
        self,
        on_transcript: Optional[Callable[[str], None]] = None,
        on_response_text: Optional[Callable[[str], None]] = None,
        on_audio_chunk: Optional[Callable[[bytes], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Listen for server messages with callbacks."""
        if not self.connected:
            await self.connect()
            
        try:
            async for message in self.websocket:
                data = json.loads(message)
                msg_type = data.get("type")
                
                if msg_type == "transcript" and on_transcript:
                    on_transcript(data.get("text", ""))
                elif msg_type == "response_text" and on_response_text:
                    on_response_text(data.get("text", ""))
                elif msg_type == "audio_chunk" and on_audio_chunk:
                    chunk_b64 = data.get("data", "")
                    on_audio_chunk(base64.b64decode(chunk_b64))
                elif msg_type == "error" and on_error:
                    on_error(data.get("message", "Unknown error"))
                    
        except websockets.exceptions.ConnectionClosed:
            pass


# Convenience function for simple use cases
async def quick_conversation(
    audio_data: bytes,
    server_url: str = "ws://localhost:8000",
) -> tuple[str, str, bytes]:
    """
    One-shot conversation: send audio, get response.
    
    Returns:
        (transcript, response_text, response_audio_bytes)
    """
    client = VoiceAssistantClient(server_url)
    try:
        return await client.process_audio(audio_data)
    finally:
        await client.disconnect()