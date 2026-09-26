"""
MongoDB memory store with automatic summarization.
"""

import logging
from datetime import datetime
from typing import List, Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from .models import ConversationTurn, ConversationSummary
from server.config import settings

logger = logging.getLogger(__name__)


class MongoMemoryStore:
    """MongoDB-backed conversation memory with auto-summarization."""
    
    def __init__(self, uri: str | None = None, db_name: str | None = None):
        self.uri = uri or settings.mongodb_uri
        self.db_name = db_name or settings.mongodb_db
        self._client: AsyncIOMotorClient | None = None
        self._db: AsyncIOMotorDatabase | None = None
    
    async def connect(self):
        """Initialize MongoDB connection."""
        if self._client is None:
            self._client = AsyncIOMotorClient(self.uri)
            self._db = self._client[self.db_name]
            await self._create_indexes()
            logger.info(f"Connected to MongoDB: {self.db_name}")
    
    async def close(self):
        """Close MongoDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
    
    @property
    def db(self) -> AsyncIOMotorDatabase:
        if self._db is None:
            raise RuntimeError("Memory store not connected. Call connect() first.")
        return self._db
    
    @property
    def conversations(self):
        return self.db.conversations
    
    @property
    def summaries(self):
        return self.db.summaries
    
    async def _create_indexes(self):
        """Create necessary indexes."""
        await self.conversations.create_index(
            [("user_id", ASCENDING), ("session_id", ASCENDING), ("turn_number", ASCENDING)],
            unique=True
        )
        await self.conversations.create_index(
            [("user_id", ASCENDING), ("session_id", ASCENDING), ("timestamp", DESCENDING)]
        )
        await self.summaries.create_index(
            [("user_id", ASCENDING), ("session_id", ASCENDING), ("end_turn", DESCENDING)]
        )
    
    # ==================== Core Operations ====================
    
    async def _next_turn(self, user_id: str, session_id: str) -> int:
        """Get next turn number for a session."""
        last = await self.conversations.find_one(
            {"user_id": user_id, "session_id": session_id},
            sort=[("turn_number", DESCENDING)],
            projection={"turn_number": 1}
        )
        return (last["turn_number"] + 1) if last else 1
    
    async def add_turn(
        self, 
        user_id: str, 
        session_id: str, 
        role: str, 
        content: str
    ) -> int:
        """Add a conversation turn and trigger summarization check."""
        await self.connect()
        
        turn_number = await self._next_turn(user_id, session_id)
        
        turn = ConversationTurn(
            user_id=user_id,
            session_id=session_id,
            turn_number=turn_number,
            role=role,
            content=content
        )
        
        await self.conversations.insert_one(turn.model_dump(by_alias=True, exclude={"id"}))
        logger.debug(f"Added turn {turn_number} for {user_id}/{session_id} ({role})")
        
        # Trigger summarization check
        await self._maybe_summarize(user_id, session_id)
        
        return turn_number
    
    async def get_history(
        self, 
        user_id: str, 
        session_id: str, 
        max_turns: int | None = None
    ) -> List[ConversationTurn]:
        """Get recent conversation history with latest summary context."""
        await self.connect()
        
        max_turns = max_turns or settings.memory_max_turns
        
        # 1. Get latest summary for this session
        latest_summary = await self.summaries.find_one(
            {"user_id": user_id, "session_id": session_id},
            sort=[("end_turn", DESCENDING)]
        )
        
        # 2. Get recent turns after the last summary
        after_turn = latest_summary["end_turn"] if latest_summary else 0
        
        cursor = self.conversations.find({
            "user_id": user_id,
            "session_id": session_id,
            "turn_number": {"$gt": after_turn}
        }).sort("turn_number", DESCENDING).limit(max_turns)
        
        turns = await cursor.to_list(length=max_turns)
        turns = [ConversationTurn(**t) for t in reversed(turns)]  # chronological
        
        # 3. Prepend summary as system message if exists
        if latest_summary:
            summary_turn = ConversationTurn(
                user_id=user_id,
                session_id=session_id,
                turn_number=0,  # Special marker
                role="system",
                content=f"Previous conversation summary: {latest_summary['summary']}"
            )
            turns.insert(0, summary_turn)
        
        return turns
    
    async def get_history_as_messages(
        self, 
        user_id: str, 
        session_id: str, 
        max_turns: int | None = None
    ) -> List[dict]:
        """Get history formatted for LLM API (role, content)."""
        turns = await self.get_history(user_id, session_id, max_turns)
        return [{"role": t.role, "content": t.content} for t in turns]
    
    async def clear_session(self, user_id: str, session_id: str):
        """Clear all conversation data for a session."""
        await self.connect()
        await self.conversations.delete_many({
            "user_id": user_id, 
            "session_id": session_id
        })
        await self.summaries.delete_many({
            "user_id": user_id, 
            "session_id": session_id
        })
        logger.info(f"Cleared session {user_id}/{session_id}")
    
    async def list_sessions(self, user_id: str) -> List[dict]:
        """List all sessions for a user with metadata."""
        await self.connect()
        
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {
                "_id": "$session_id",
                "turn_count": {"$sum": 1},
                "last_activity": {"$max": "$timestamp"},
                "first_turn": {"$min": "$turn_number"},
                "last_turn": {"$max": "$turn_number"}
            }},
            {"$sort": {"last_activity": DESCENDING}}
        ]
        
        sessions = await self.conversations.aggregate(pipeline).to_list(length=100)
        
        # Add summary info
        for sess in sessions:
            summary = await self.summaries.find_one(
                {"user_id": user_id, "session_id": sess["_id"]},
                sort=[("end_turn", DESCENDING)]
            )
            sess["has_summary"] = summary is not None
            sess["session_id"] = sess.pop("_id")
        
        return sessions
    
    # ==================== Summarization ====================
    
    async def _maybe_summarize(self, user_id: str, session_id: str):
        """Check if summarization is needed and trigger it."""
        threshold = settings.memory_summarize_threshold
        
        # Find latest summary
        latest_summary = await self.summaries.find_one(
            {"user_id": user_id, "session_id": session_id},
            sort=[("end_turn", DESCENDING)]
        )
        after_turn = latest_summary["end_turn"] if latest_summary else 0
        
        # Count unsummarized turns
        count = await self.conversations.count_documents({
            "user_id": user_id,
            "session_id": session_id,
            "turn_number": {"$gt": after_turn}
        })
        
        if count >= threshold:
            logger.info(f"Summarization triggered for {user_id}/{session_id} ({count} turns)")
            await self._summarize_and_delete(user_id, session_id, after_turn)
    
    async def _summarize_and_delete(self, user_id: str, session_id: str, after_turn: int):
        """Summarize old turns and delete them."""
        from server.llm import summarize_with_deepseek
        
        # Get turns to summarize
        cursor = self.conversations.find({
            "user_id": user_id,
            "session_id": session_id,
            "turn_number": {"$gt": after_turn}
        }).sort("turn_number", ASCENDING)
        
        turns = await cursor.to_list(length=100)
        if not turns:
            return
        
        # Build conversation text
        conv_text = "\n".join(f"{t['role']}: {t['content']}" for t in turns)
        
        # Create summarization prompt
        prompt = f"""Summarize this conversation in 3-4 sentences, 
keeping key facts, decisions, and topics discussed:\n\n{conv_text}"""
        
        try:
            summary_text = await summarize_with_deepseek(prompt)
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return
        
        # Store summary
        summary = ConversationSummary(
            user_id=user_id,
            session_id=session_id,
            start_turn=turns[0]["turn_number"],
            end_turn=turns[-1]["turn_number"],
            summary=summary_text
        )
        
        await self.summaries.insert_one(summary.model_dump(by_alias=True, exclude={"id"}))
        logger.info(f"Stored summary for {user_id}/{session_id}: turns {summary.start_turn}-{summary.end_turn}")
        
        # Delete summarized turns
        result = await self.conversations.delete_many({
            "user_id": user_id,
            "session_id": session_id,
            "turn_number": {"$lte": turns[-1]["turn_number"]}
        })
        logger.info(f"Deleted {result.deleted_count} summarized turns")


# Global instance
_memory_store: MongoMemoryStore | None = None


def get_memory_store() -> MongoMemoryStore:
    """Get or create global memory store instance."""
    global _memory_store
    if _memory_store is None:
        _memory_store = MongoMemoryStore()
    return _memory_store