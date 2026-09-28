"""
Data types shared across the agent loop.
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ToolResult:
    tool_call_id: str
    name: str
    content: str
    is_error: bool = False


@dataclass
class AgentStep:
    """One step of the Observe/Reason/Act/Finish loop, for logging and UI display."""
    kind: Literal["reason", "tool_call", "tool_result", "finish"]
    content: str
    tool_name: str | None = None
    tool_args: dict | None = None


@dataclass
class AgentResult:
    final_response: str
    steps: list[AgentStep] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
