"""
Configuration settings for Voice Assistant.
Loads from .env file using pydantic-settings.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # DeepSeek API
    deepseek_api_key: str
    
    # MongoDB Atlas
    mongodb_uri: str
    mongodb_db: str = "voice_assistant"
    
    # Memory settings
    memory_max_turns: int = 10
    memory_summarize_threshold: int = 20

    # Agent settings
    agent_max_iterations: int = 6
    agent_search_max_results: int = 5

    # NeMo Speech Server
    nemo_asr_url: str = "http://127.0.0.1:8080/v1/audio/transcriptions"
    nemo_tts_url: str = "http://127.0.0.1:8080/v1/audio/speech"
    
    # WebSocket Server
    websocket_host: str = "0.0.0.0"
    websocket_port: int = 8000
    
    # User ID (single user for now)
    default_user_id: str = "default"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "allow"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# Convenience access
settings = get_settings()