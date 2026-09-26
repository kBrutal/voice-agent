"""
Pydantic models for memory storage.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from bson import ObjectId
from pydantic_core import core_schema


class PyObjectId(ObjectId):
    """Custom ObjectId for Pydantic v2."""
    
    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        return handler(str)
    
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.with_info_plain_validator_function(cls.validate)
    
    @classmethod
    def validate(cls, v, _info=None):
        if isinstance(v, ObjectId):
            return v
        if isinstance(v, str):
            return ObjectId(v)
        raise ValueError("Invalid ObjectId")


class ConversationTurn(BaseModel):
    """A single conversation turn (user or assistant message)."""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    user_id: str
    session_id: str
    turn_number: int
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


class ConversationSummary(BaseModel):
    """Summarized conversation segment."""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    user_id: str
    session_id: str
    start_turn: int
    end_turn: int
    summary: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


class SessionInfo(BaseModel):
    """Session metadata."""
    user_id: str
    session_id: str
    turn_count: int
    last_activity: datetime
    has_summary: bool