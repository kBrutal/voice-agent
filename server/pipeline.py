import argparse
import asyncio
from pathlib import Path

from pymongo.errors import PyMongoError

from .asr import transcribe
from .agent import get_agent, AgentStep
from .language import detect_language, language_name
from .tts import synthesize
from .memory import get_memory_store
from .config import settings


async def process_audio(
    audio_path: str,
    output_path: str | None = None,
    voice: str = "default",
    user_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """
    Full pipeline: Audio -> ASR -> LLM (with memory) -> TTS -> Audio

    Args:
        audio_path: Path to input WAV audio file.
        output_path: Optional output path. If not provided, uses "out_<input_name>.wav".
        voice: TTS voice name or speaker index.
        user_id: User identifier (defaults to config default_user_id).
        session_id: Session identifier (auto-generated if not provided).

    Returns:
        Path to the generated response audio file.
    """
    audio_file = Path(audio_path)

    if not audio_file.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_file}")

    if output_path is None:
        output_path = str(audio_file.parent / f"out_{audio_file.name}")

    # Use defaults if not provided
    user_id = user_id or settings.default_user_id
    session_id = session_id or "default"

    memory = get_memory_store()

    # Step 1: ASR - Transcribe audio to text, auto-detecting the spoken language
    asr_result = await transcribe(audio_path, "auto")
    transcript = asr_result.get("text", "").strip()

    if not transcript:
        raise RuntimeError("ASR returned empty transcript")

    user_language = detect_language(transcript, asr_hint=asr_result.get("language"))
    print(f"[language] {user_language}")

    # Step 2: Get conversation history from memory (best-effort)
    memory_ok = True
    try:
        await memory.connect()
        history = await memory.get_history_as_messages(user_id, session_id)
    except PyMongoError as e:
        memory_ok = False
        history = []
        print(f"[warning] memory unavailable, continuing without history: {str(e).splitlines()[0][:160]}")

    # Step 3: Agent - Observe -> Reason -> Act -> ... -> Finish (with tool calling)
    async def print_step(step: AgentStep) -> None:
        print(f"[{step.kind}] {step.content}")

    agent = get_agent()
    result = await agent.run(
        transcript, history, on_step=print_step, language=language_name(user_language)
    )
    response_text = result.final_response

    if not response_text.strip():
        raise RuntimeError("LLM returned empty response")

    # Step 4: Store in memory (user turn + assistant response)
    if memory_ok:
        try:
            await memory.add_turn(user_id, session_id, "user", transcript)
            await memory.add_turn(user_id, session_id, "assistant", response_text)
        except PyMongoError as e:
            print(f"[warning] failed to save turn to memory: {str(e).splitlines()[0][:160]}")

    # Step 5: TTS - Synthesize response in the language it was written in
    output = await synthesize(
        text=response_text,
        language=detect_language(response_text, fallback=user_language),
        voice=voice,
        output_path=output_path,
    )

    return output


async def main():
    parser = argparse.ArgumentParser(
        description="Voice Assistant Pipeline: ASR -> LLM -> TTS"
    )

    parser.add_argument(
        "audio",
        help="Path to input WAV audio file",
    )

    parser.add_argument(
        "--voice",
        default="default",
        help="TTS voice name or speaker index",
    )

    parser.add_argument(
        "--output",
        help="Output WAV file (default: out_<input_name>.wav)",
    )

    parser.add_argument(
        "--user-id",
        default=None,
        help="User ID (defaults to config default_user_id)",
    )

    parser.add_argument(
        "--session-id",
        default=None,
        help="Session ID (defaults to 'default')",
    )

    args = parser.parse_args()

    output = await process_audio(
        audio_path=args.audio,
        output_path=args.output,
        voice=args.voice,
        user_id=args.user_id,
        session_id=args.session_id,
    )

    print(f"\nGenerated response: {output}")


if __name__ == "__main__":
    asyncio.run(main())