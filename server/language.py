"""
Spoken-language detection for the voice pipeline.

The ASR's own language tag is unreliable (e.g. Spanish comes back as "es-US",
Hindi as "auto"), so the language is detected from the transcript text and
mapped onto the locales the Magpie TTS model can speak.
"""

import argparse
import re

from fast_langdetect import detect

# Base language code -> (TTS locale, name used in LLM instructions)
SUPPORTED_LANGUAGES: dict[str, tuple[str, str]] = {
    "en": ("en-US", "English"),
    "es": ("es-ES", "Spanish"),
    "de": ("de-DE", "German"),
    "fr": ("fr-FR", "French"),
    "it": ("it-IT", "Italian"),
    "vi": ("vi-VN", "Vietnamese"),
    "hi": ("hi-IN", "Hindi"),
}

DEFAULT_LANGUAGE = "en-US"

MIN_CONFIDENCE = 0.5

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def _base(code: str | None) -> str | None:
    if not code:
        return None
    return code.split("-")[0].split("_")[0].lower()


def detect_language(
    text: str,
    asr_hint: str | None = None,
    fallback: str = DEFAULT_LANGUAGE,
) -> str:
    """Return the TTS locale (e.g. "es-ES") for the language of `text`.

    Falls back to the ASR's hint, then to `fallback` (typically the previous
    turn's language), when the text is too short to classify confidently.
    Languages the TTS can't speak resolve to `fallback`.
    """
    if _DEVANAGARI.search(text):
        return SUPPORTED_LANGUAGES["hi"][0]

    cleaned = " ".join(text.split())
    if cleaned:
        top = detect(cleaned, model="lite", k=1)[0]
        if top["score"] >= MIN_CONFIDENCE and top["lang"] in SUPPORTED_LANGUAGES:
            return SUPPORTED_LANGUAGES[top["lang"]][0]
        if top["score"] >= MIN_CONFIDENCE:
            return fallback

    hint = _base(asr_hint)
    if hint in SUPPORTED_LANGUAGES:
        return SUPPORTED_LANGUAGES[hint][0]

    return fallback


def language_name(locale: str) -> str:
    """Human-readable name for a TTS locale, e.g. "es-ES" -> "Spanish"."""
    base = _base(locale) or ""
    return SUPPORTED_LANGUAGES.get(base, SUPPORTED_LANGUAGES["en"])[1]


def reply_instruction(locale: str, mode: str | None = None) -> str:
    """Instruction telling the agent which language (and script) to reply in.

    Hindi and Hinglish replies must be pure Devanagari: the Hindi TTS voice
    mispronounces Latin-script English words and can't read romanized Hindi.
    """
    devanagari_only = (
        "Write the entire reply in Devanagari script, transliterating any English "
        "words or names (e.g. 'मीटिंग', 'ऑफिस', 'गूगल'), because the speech engine "
        "can only pronounce Devanagari."
    )
    if mode == "hinglish":
        return (
            "The user is speaking Hinglish, a casual mix of Hindi and English. Reply in "
            "the same natural Hinglish style, keeping common English words where a "
            f"Hinglish speaker would. {devanagari_only}"
        )

    name = language_name(locale)
    instruction = (
        f"The user is speaking {name}. Write your entire reply in {name}, "
        "even if earlier turns or search results are in another language."
    )
    if _base(locale) == "hi":
        instruction += f" {devanagari_only}"
    return instruction


def main():
    parser = argparse.ArgumentParser(description="Detect spoken language from text")
    parser.add_argument("text", help="Transcript text")
    parser.add_argument("--hint", default=None, help="ASR language hint, e.g. es-US")
    args = parser.parse_args()

    locale = detect_language(args.text, args.hint)
    print(f"{locale} ({language_name(locale)})")


if __name__ == "__main__":
    main()
