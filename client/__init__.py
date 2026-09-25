"""
Voice Assistant Client Package

Usage:
    from client import VoiceAssistantClient, quick_conversation
    
    # Simple one-shot
    transcript, response, audio = await quick_conversation(audio_bytes)
    
    # Or use class for more control
    client = VoiceAssistantClient("ws://localhost:8000")
    await client.connect()
    transcript, response, audio = await client.process_audio(audio_bytes)
    await client.disconnect()
"""

from .voice_client import VoiceAssistantClient, VoiceConfig, quick_conversation

__all__ = [
    "VoiceAssistantClient",
    "VoiceConfig", 
    "quick_conversation",
]