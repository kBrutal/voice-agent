import argparse
import asyncio
from pathlib import Path

import aiohttp


NEMO_TTS_URL = "http://127.0.0.1:8080/v1/audio/speech"


async def synthesize(
    text: str,
    language: str = "en-US",
    voice: str = "default",
    output_path: str = "output.wav",
) -> str:
    """
    Convert text to speech using local NVIDIA Magpie TTS.

    Args:
        text: Text to synthesize.
        language: Language code, e.g. en-US, hi-IN.
        voice: Local Magpie voice name or speaker index.
        output_path: Where to save the generated WAV.

    Returns:
        Path to the generated audio file.
    """

    if not text.strip():
        raise ValueError("Text cannot be empty.")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "model": "magpie",
        "input": text,
        "voice": voice,
        "language": language,
        "response_format": "wav",
    }

    timeout = aiohttp.ClientTimeout(total=600, sock_read=600)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            NEMO_TTS_URL,
            json=payload,
        ) as response:

            if response.status != 200:
                error = await response.text()

                raise RuntimeError(
                    f"Magpie TTS failed "
                    f"({response.status}): {error}"
                )

            audio = await response.read()

    output.write_bytes(audio)

    return str(output)


async def main():

    parser = argparse.ArgumentParser(
        description="Local Magpie Multilingual TTS"
    )

    parser.add_argument(
        "text",
        help="Text to synthesize",
    )

    parser.add_argument(
        "--language",
        default="en-US",
        help="Language code, e.g. en-US or hi-IN",
    )

    parser.add_argument(
        "--voice",
        default="default",
        help="Magpie voice name or speaker index",
    )

    parser.add_argument(
        "--output",
        default="output.wav",
        help="Output WAV file",
    )

    args = parser.parse_args()

    output = await synthesize(
        text=args.text,
        language=args.language,
        voice=args.voice,
        output_path=args.output,
    )

    print(f"Generated: {output}")


if __name__ == "__main__":
    asyncio.run(main())