import argparse
import asyncio
from pathlib import Path

from .asr import transcribe
from .llm import generate_response_with_history
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

    # Get memory store
    memory = get_memory_store()
    await memory.connect()

    # Step 1: ASR - Transcribe audio to text (always use en-US)
    asr_result = await transcribe(audio_path, "en-US")
    transcript = asr_result.get("text", "").strip()

    if not transcript:
        raise RuntimeError("ASR returned empty transcript")

    # Step 2: Get conversation history from memory
    history = await memory.get_history_as_messages(user_id, session_id)

    # Step 3: LLM - Generate response with history
    response_text = generate_response_with_history(transcript, history)

    if not response_text.strip():
        raise RuntimeError("LLM returned empty response")

    # Step 4: Store in memory (user turn + assistant response)
    await memory.add_turn(user_id, session_id, "user", transcript)
    await memory.add_turn(user_id, session_id, "assistant", response_text)

    # Step 5: TTS - Synthesize response to audio (always use en-US)
    output = await synthesize(
        text=response_text,
        language="en-US",
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