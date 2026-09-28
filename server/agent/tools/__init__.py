"""
Tool abstraction and registry for the agent loop.
"""

import json
import logging
from abc import ABC, abstractmethod

from ..types import ToolCall, ToolResult

logger = logging.getLogger(__name__)


class Tool(ABC):
    name: str
    description: str
    parameters: dict  # JSON schema for the function's arguments

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """Run the tool and return a text result for the model to observe."""

    def to_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self, tools: list[Tool]):
        self._tools: dict[str, Tool] = {t.name: t for t in tools}

    def schemas(self) -> list[dict]:
        return [t.to_schema() for t in self._tools.values()]

    async def dispatch(self, call: ToolCall) -> ToolResult:
        tool = self._tools.get(call.name)

        if tool is None:
            return ToolResult(
                tool_call_id=call.id,
                name=call.name,
                content=f"Unknown tool: {call.name}",
                is_error=True,
            )

        try:
            content = await tool.execute(**call.arguments)
            return ToolResult(tool_call_id=call.id, name=call.name, content=content)
        except Exception as e:
            logger.error(f"Tool '{call.name}' failed: {e}")
            return ToolResult(
                tool_call_id=call.id,
                name=call.name,
                content=f"Tool '{call.name}' failed: {e}",
                is_error=True,
            )

    @staticmethod
    def parse_arguments(raw_arguments: str) -> dict:
        """Parse a tool call's raw JSON arguments string, tolerating empty input."""
        if not raw_arguments or not raw_arguments.strip():
            return {}
        try:
            return json.loads(raw_arguments)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid tool arguments JSON: {e}")
