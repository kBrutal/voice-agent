import argparse
import asyncio
from pathlib import Path

from .asr import transcribe
from .llm import generate_response
from .tts import synthesize


async def process_audio(
    audio_path: str,
    output_path: str | None = None,
    voice: str = "default",
) -> str:
    """
    Full pipeline: Audio -> ASR -> LLM -> TTS -> Audio

    Args:
        audio_path: Path to input WAV audio file.
        output_path: Optional output path. If not provided, uses "out_<input_name>.wav".
        voice: TTS voice name or speaker index.

    Returns:
        Path to the generated response audio file.
    """
    audio_file = Path(audio_path)

    if not audio_file.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_file}")

    if output_path is None:
        output_path = str(audio_file.parent / f"out_{audio_file.name}")

    # Step 1: ASR - Transcribe audio to text (always use en-US)
    asr_result = await transcribe(audio_path, "en-US")
    transcript = asr_result.get("text", "").strip()

    if not transcript:
        raise RuntimeError("ASR returned empty transcript")

    # Step 2: LLM - Generate response
    response_text = generate_response(transcript)

    if not response_text.strip():
        raise RuntimeError("LLM returned empty response")

    # Step 3: TTS - Synthesize response to audio (always use en-US)
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

    args = parser.parse_args()

    output = await process_audio(
        audio_path=args.audio,
        output_path=args.output,
        voice=args.voice,
    )

    print(f"\nGenerated response: {output}")


if __name__ == "__main__":
    asyncio.run(main())