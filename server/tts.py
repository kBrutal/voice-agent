import argparse
import asyncio
import re
from pathlib import Path

import aiohttp


NEMO_TTS_URL = "http://127.0.0.1:8080/v1/audio/speech"

_SENTENCE_END = re.compile(r"(?<=[.!?।])\s+")
_CLAUSE_BREAK = re.compile(r"(?<=[,;:])\s+")
MIN_CHUNK_CHARS = 20


def _split_at_clauses(text: str, limit: int) -> list[str]:
    """Pack comma/semicolon clauses into pieces of at most `limit` chars where possible."""
    if len(text) <= limit:
        return [text]
    pieces: list[str] = []
    current = ""
    for clause in _CLAUSE_BREAK.split(text):
        if current and len(current) + 1 + len(clause) > limit:
            pieces.append(current)
            current = clause
        else:
            current = f"{current} {clause}".strip()
    if current:
        pieces.append(current)
    return pieces


def split_for_tts(text: str, first_max: int = 45, max_len: int = 220) -> list[str]:
    """Split a reply into chunks that can be synthesized and played one by one.

    TTS time grows with text length, so the first chunk is kept short to get
    audio playing quickly; later chunks are whole sentences (split at commas
    if very long). Tiny fragments are merged so playback isn't choppy.
    """
    text = " ".join(text.split())
    sentences = [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]

    chunks: list[str] = []
    for sentence in sentences:
        chunks.extend(_split_at_clauses(sentence, max_len))

    merged: list[str] = []
    carry = ""
    for chunk in chunks:
        chunk = f"{carry} {chunk}".strip() if carry else chunk
        if len(chunk) < MIN_CHUNK_CHARS:
            carry = chunk
            continue
        merged.append(chunk)
        carry = ""
    if carry:
        if merged:
            merged[-1] = f"{merged[-1]} {carry}"
        else:
            merged.append(carry)

    if merged and len(merged[0]) > first_max:
        first = merged[0]
        parts = _split_at_clauses(first, first_max)
        head = parts[0]
        if len(head) < MIN_CHUNK_CHARS and len(parts) > 1:
            head = f"{head} {parts[1]}"
        if len(head) > first_max:
            # No usable comma: cut the first chunk at a word boundary instead,
            # trading a little prosody for a much faster first audio.
            cut = first.rfind(" ", MIN_CHUNK_CHARS, first_max + 1)
            if cut != -1:
                head = first[:cut]
        rest = first[len(head):].strip()
        if len(rest) >= MIN_CHUNK_CHARS:
            merged[0:1] = [head, rest]

    return merged


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