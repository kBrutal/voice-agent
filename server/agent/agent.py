"""
Single-agent Observe -> Reason -> Act -> Observe -> ... -> Finish loop with tool calling.
"""

import argparse
import asyncio
import logging
import re
from typing import Awaitable, Callable

from openai import AsyncOpenAI

from server.config import settings
from server.language import detect_language, reply_instruction
from server.llm import SYSTEM_PROMPT

from .tools import ToolRegistry
from .tools.web_search import WebSearchTool
from .types import AgentResult, AgentStep, ToolCall

logger = logging.getLogger(__name__)

# ============================================================
# Configuration
# ============================================================

MODEL = "deepseek-v4-pro"
BASE_URL = "https://api.deepseek.com"

AGENT_SYSTEM_PROMPT = (
    SYSTEM_PROMPT
    + """

## Tools
You have access to a `web_search` tool. Use it when the request needs current
information you would not reliably know: recent events, live data (weather,
prices, scores), or specific facts worth double-checking. For simple
conversational turns (greetings, opinions, things you already know), answer
directly without searching.

## Length
Every reply is spoken aloud, and long replies take a long time to synthesize.
Keep answers to at most two or three short sentences (about fifty words).
Lead with the answer itself. Only go longer when the user explicitly asks for
more detail.
"""
)

OnStep = Callable[[AgentStep], Awaitable[None]]


class Agent:
    """Runs the Observe/Reason/Act/Finish loop against a tool-calling LLM."""

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        tools: ToolRegistry,
        system_prompt: str,
        max_iterations: int = 6,
    ):
        self.client = client
        self.model = model
        self.tools = tools
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations

    async def run(
        self,
        user_input: str,
        history: list[dict] | None = None,
        on_step: OnStep | None = None,
        language_instruction: str | None = None,
    ) -> AgentResult:
        """Observe -> Reason -> Act -> Observe -> ... -> Finish.

        Args:
            user_input: Current user message (the initial Observation).
            history: Prior conversation turns as {"role", "content"} dicts.
            on_step: Optional async callback invoked with each AgentStep as it
                happens, so callers (e.g. a WebSocket handler) can surface the
                agent's live activity without the Agent knowing about them.
            language_instruction: Which language/script to reply in, from
                `server.language.reply_instruction`.
        """
        if not user_input.strip():
            raise ValueError("User input cannot be empty.")

        system_prompt = self.system_prompt
        if language_instruction:
            system_prompt += f"\n\n## Response Language\n{language_instruction}"

        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        steps: list[AgentStep] = []

        async def emit(step: AgentStep) -> None:
            steps.append(step)
            if on_step:
                await on_step(step)

        for _ in range(self.max_iterations):
            # ---- Reason ----
            message = await self._reason(messages, use_tools=True)

            if not message.tool_calls:
                # ---- Finish ----
                content = message.content or ""
                await emit(AgentStep(kind="finish", content=content))
                return AgentResult(final_response=content, steps=steps, messages=messages)

            await emit(AgentStep(
                kind="reason",
                content=message.content or "(deciding to use a tool)",
            ))

            # ---- Act ----
            messages.append(self._assistant_tool_call_message(message))

            for raw_call in message.tool_calls:
                call = ToolCall(
                    id=raw_call.id,
                    name=raw_call.function.name,
                    arguments=self._safe_parse_arguments(raw_call.function.arguments),
                )
                await emit(AgentStep(
                    kind="tool_call",
                    content=f"Calling {call.name}({call.arguments})",
                    tool_name=call.name,
                    tool_args=call.arguments,
                ))

                result = await self.tools.dispatch(call)

                await emit(AgentStep(
                    kind="tool_result",
                    content=result.content,
                    tool_name=call.name,
                ))

                # ---- Observe ----
                messages.append({
                    "role": "tool",
                    "tool_call_id": result.tool_call_id,
                    "content": result.content,
                })

        # Guard rail: ran out of iterations without a natural Finish.
        # Force one last answer with tools disabled.
        message = await self._reason(messages, use_tools=False)
        content = message.content or "I wasn't able to finish that within my step limit."
        await emit(AgentStep(kind="finish", content=content))
        return AgentResult(final_response=content, steps=steps, messages=messages)

    async def _reason(self, messages: list[dict], use_tools: bool):
        kwargs = {}
        if use_tools:
            kwargs["tools"] = self.tools.schemas()
            kwargs["tool_choice"] = "auto"

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            reasoning_effort="high",
            extra_body={"thinking": {"type": "enabled"}},
            stream=False,
            **kwargs,
        )
        return response.choices[0].message

    @staticmethod
    def _assistant_tool_call_message(message) -> dict:
        return {
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ],
        }

    @staticmethod
    def _safe_parse_arguments(raw_arguments: str) -> dict:
        try:
            return ToolRegistry.parse_arguments(raw_arguments)
        except ValueError as e:
            logger.warning(f"Failed to parse tool arguments: {e}")
            return {}


# ============================================================
# Singleton accessor
# ============================================================

_agent: Agent | None = None


def get_agent() -> Agent:
    """Get or create the global Agent instance."""
    global _agent
    if _agent is None:
        client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=BASE_URL,
        )
        _agent = Agent(
            client=client,
            model=MODEL,
            tools=ToolRegistry([WebSearchTool(max_results=settings.agent_search_max_results)]),
            system_prompt=AGENT_SYSTEM_PROMPT,
            max_iterations=settings.agent_max_iterations,
        )
    return _agent


# ============================================================
# Command-line interface
# ============================================================

async def _run_cli(user_input: str):
    async def print_step(step: AgentStep) -> None:
        print(f"[{step.kind}] {step.content}")

    locale = detect_language(user_input)
    is_hinglish = bool(re.search(r"[ऀ-ॿ]", user_input) and re.search(r"[A-Za-z]", user_input))
    mode = "hinglish" if is_hinglish else None
    print(f"[language] {locale}{' (hinglish)' if is_hinglish else ''}")

    agent = get_agent()
    result = await agent.run(
        user_input, on_step=print_step, language_instruction=reply_instruction(locale, mode)
    )

    print("\nResponse:")
    print(result.final_response)


def main():
    parser = argparse.ArgumentParser(description="Single-agent loop (DeepSeek + tools)")
    parser.add_argument("input", help="User message")
    args = parser.parse_args()

    asyncio.run(_run_cli(args.input))


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    main()
