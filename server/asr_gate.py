"""
ASR gate: transcribe the same audio three ways and let a fast LLM decide what
was actually said.

The ASR model is run with the language forced to English, forced to Hindi, and
on auto-detect (serialized inside `transcribe`, since the speech server corrupts
overlapping requests). A forced transcript of the wrong language comes out
as phonetic garbage (Hindi audio forced to English) or a transliteration
(English audio forced to Hindi), so neither alone handles code-mixed Hinglish.
deepseek-flash reads all three and produces the final input text plus a mode:
english, hindi, hinglish, or other (any other language, taken from the auto
transcript).
"""

import argparse
import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Literal

from openai import AsyncOpenAI

from server.asr import transcribe
from server.config import settings
from server.language import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, detect_language

logger = logging.getLogger(__name__)

# ============================================================
# Configuration
# ============================================================

GATE_MODEL = "deepseek-flash"
BASE_URL = "https://api.deepseek.com"

Mode = Literal["english", "hindi", "hinglish", "other"]

GATE_PROMPT = """
You are the input gate of a voice assistant. The same spoken utterance was
transcribed three times by a speech recognizer:

- "english": recognizer forced to English. If the speech was Hindi, this is
  phonetic garbage.
- "hindi": recognizer forced to Hindi, in Devanagari. If the speech was English,
  this is an English sentence transliterated into Devanagari.
- "auto": recognizer on auto-detect. Use it mainly when the speech is neither
  Hindi nor English (e.g. Spanish, German, French, Italian, Vietnamese).

Decide what the user actually said and output it as the final transcript:

- Pure English: return clean English text. mode = "english".
- Pure Hindi: return Devanagari text. mode = "hindi".
- Hinglish (Hindi and English mixed in one utterance): merge the two
  transcripts, writing Hindi words in Devanagari and English words in Latin
  script, e.g. "कल मेरी office में important meeting है". mode = "hinglish".
  English words often appear transliterated in the "hindi" candidate
  (ऑफिस = office, मीटिंग = meeting, इम्पोर्टेंट = important, रिमाइंडर = reminder,
  वेदर = weather). A Hindi sentence containing such English words is Hinglish:
  write those words in Latin script. Ordinary Hindi vocabulary, including
  common Urdu/Sanskrit-origin words, stays in Devanagari and does not by itself
  make the utterance Hinglish.
- Any other language: return the auto transcript. mode = "other".

Never drop words. For Hindi and Hinglish speech the "hindi" candidate is
usually the most complete; the "english" candidate may cover only part of the
utterance or be garbled. Keep every word of the most complete candidate, only
changing the script of English words. Fix obvious recognition errors only when
the correct word is clear from the candidates. Do not answer, translate, summarize, or add anything. If no
candidate contains meaningful speech, return an empty transcript.

Respond with JSON only:
{"transcript": "<final text>", "mode": "english|hindi|hinglish|other", "language": "<ISO 639-1 code of the main language>"}
"""

MODE_LOCALES: dict[str, str] = {
    "english": SUPPORTED_LANGUAGES["en"][0],
    "hindi": SUPPORTED_LANGUAGES["hi"][0],
    "hinglish": SUPPORTED_LANGUAGES["hi"][0],
}

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.deepseek_api_key, base_url=BASE_URL)
    return _client


@dataclass
class GatedTranscript:
    text: str
    mode: Mode
    locale: str  # TTS locale the reply should be spoken in, e.g. "hi-IN"
    candidates: dict[str, str] = field(default_factory=dict)


# ============================================================
# Gate
# ============================================================

async def _merge(candidates: dict[str, str]) -> dict:
    response = await _get_client().chat.completions.create(
        model=GATE_MODEL,
        messages=[
            {"role": "system", "content": GATE_PROMPT},
            {"role": "user", "content": json.dumps(candidates, ensure_ascii=False)},
        ],
        temperature=0,
        max_tokens=500,
        response_format={"type": "json_object"},
        extra_body={"thinking": {"type": "disabled"}},
    )
    return json.loads(response.choices[0].message.content or "{}")


async def gated_transcribe(audio_path: str, fallback: str = DEFAULT_LANGUAGE) -> GatedTranscript:
    """Transcribe `audio_path` through the English/Hindi/auto gate.

    `fallback` is the locale to use when the language can't be determined
    (typically the previous turn's language).
    """
    results = await asyncio.gather(
        transcribe(audio_path, "en-US"),
        transcribe(audio_path, "hi-IN"),
        transcribe(audio_path, "auto"),
    )
    candidates = {
        name: result.get("text", "").strip()
        for name, result in zip(("english", "hindi", "auto"), results)
    }
    auto_hint = results[2].get("language")

    if not any(candidates.values()):
        return GatedTranscript(text="", mode="other", locale=fallback, candidates=candidates)

    try:
        decision = await _merge(candidates)
        text = str(decision.get("transcript", "")).strip()
        mode = decision.get("mode")
        if mode not in ("english", "hindi", "hinglish", "other"):
            raise ValueError(f"unexpected mode {mode!r}")
    except Exception as e:
        logger.warning(f"ASR gate failed, using auto transcript: {e}")
        text = candidates["auto"] or candidates["english"]
        return GatedTranscript(
            text=text,
            mode="other",
            locale=detect_language(text, asr_hint=auto_hint, fallback=fallback),
            candidates=candidates,
        )

    if mode in MODE_LOCALES:
        locale = MODE_LOCALES[mode]
    else:
        code = str(decision.get("language", "")).lower()
        locale = (
            SUPPORTED_LANGUAGES[code][0]
            if code in SUPPORTED_LANGUAGES
            else detect_language(text, asr_hint=auto_hint, fallback=fallback)
        )

    return GatedTranscript(text=text, mode=mode, locale=locale, candidates=candidates)


# ============================================================
# Command-line interface
# ============================================================

async def _run_cli(audio_path: str):
    result = await gated_transcribe(audio_path)
    for name, text in result.candidates.items():
        print(f"[{name:7}] {text}")
    print(f"\nmode={result.mode} locale={result.locale}")
    print(f"final: {result.text}")


def main():
    parser = argparse.ArgumentParser(description="English/Hindi/Hinglish ASR gate")
    parser.add_argument("audio", help="Path to WAV audio file")
    args = parser.parse_args()
    asyncio.run(_run_cli(args.audio))


if __name__ == "__main__":
    main()
