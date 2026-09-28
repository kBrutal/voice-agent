"""
Web search tool backed by DuckDuckGo (via the `ddgs` package). No API key required.
"""

import asyncio
import logging

from ddgs import DDGS

from . import Tool

logger = logging.getLogger(__name__)


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Search the web for current information, such as recent events, facts, "
        "prices, weather, or anything the assistant may not already know. "
        "Returns a short list of results with titles, snippets, and URLs."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return.",
            },
        },
        "required": ["query"],
    }

    def __init__(self, max_results: int = 5):
        self.max_results = max_results

    async def execute(self, query: str, max_results: int | None = None) -> str:
        if not query.strip():
            raise ValueError("query cannot be empty")

        limit = max_results or self.max_results

        results = await asyncio.to_thread(self._search, query, limit)

        if not results:
            return f"No search results found for: {query}"

        lines = []
        for i, r in enumerate(results, start=1):
            title = r.get("title", "").strip()
            snippet = r.get("body", "").strip()
            url = r.get("href", "").strip()
            lines.append(f"{i}. {title} — {snippet} ({url})")

        return "\n".join(lines)

    def _search(self, query: str, max_results: int) -> list[dict]:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
