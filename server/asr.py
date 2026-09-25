import argparse
import asyncio
from pathlib import Path

import aiohttp

# hosting it on local server port 8080
NEMO_URL = "http://127.0.0.1:8080/v1/audio/transcriptions"


async def transcribe(
    audio_path: str,
    language: str = "auto",
) -> dict:

    audio_file = Path(audio_path)

    if not audio_file.exists():
        raise FileNotFoundError(
            f"Audio file not found: {audio_file}"
        )

    data = aiohttp.FormData()

    # Audio file
    data.add_field(
        "file",
        audio_file.open("rb"),
        filename=audio_file.name,
        content_type="audio/wav",
    )

    # Nemotron 3.5 language
    data.add_field("language", language)

    # Return structured JSON
    data.add_field("response_format", "verbose_json")

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:

        async with session.post(
            NEMO_URL,
            data=data,
        ) as response:

            if response.status != 200:
                error = await response.text()

                raise RuntimeError(
                    f"Nemotron ASR failed "
                    f"({response.status}): {error}"
                )

            result = await response.json()

            return result


async def main():

    parser = argparse.ArgumentParser(
        description="Local Nemotron 3.5 multilingual ASR"
    )

    parser.add_argument(
        "audio",
        help="Path to WAV audio file",
    )

    parser.add_argument(
        "--language",
        default="auto",
        help=(
            "Language code, e.g. en-US, hi-IN, "
            "es-ES, or auto"
        ),
    )

    args = parser.parse_args()

    result = await transcribe(
        args.audio,
        args.language,
    )

    print("\nTranscript:")
    print(result.get("text", ""))

    if "language" in result:
        print("\nLanguage:")
        print(result["language"])


if __name__ == "__main__":
    asyncio.run(main())