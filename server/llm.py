from dotenv import load_dotenv
from openai import OpenAI

from server.config import settings

# Load variables from .env
load_dotenv()

# ============================================================
# Configuration
# ============================================================

API_KEY = settings.deepseek_api_key

if not API_KEY:
    raise RuntimeError(
        "DEEPSEEK_API_KEY not found in .env"
    )

SUMMARIZE_MODEL = "deepseek-chat"  # cheaper model for summarization

BASE_URL = "https://api.deepseek.com"


SYSTEM_PROMPT = """
You are a helpful voice assistant.

## Input Context (ASR)
Your input comes from a speech-to-text transcription system. Transcriptions may contain errors:
- Words may be misheard, substituted, or omitted
- Homophones may be confused (e.g., "their" vs "there")
- Punctuation may be missing or incorrect
- Technical terms may be transcribed phonetically

Therefore:
- Interpret intent over literal text
- Ask for clarification if input is unclear or ambiguous
- Politely correct obvious transcription errors when relevant
- Use context from conversation history to disambiguate

## Output Context (TTS)
Your responses will be converted to speech via text-to-speech. Write for the ear, not the eye:
- Use short sentences and natural phrasing
- Write numbers as words when spoken (e.g., "twenty-five percent" not "25%")
- Avoid symbols, abbreviations, and complex punctuation
- Pause appropriately with commas and periods for natural rhythm
- Avoid overly complex terminology unless asked
- Keep responses concise—listeners cannot reread

## Response Guidelines
- Be concise and direct
- Use simple, conversational language
- Avoid: Markdown, tables, code blocks, URLs, email addresses
- If listing items, use natural speech patterns ("First..., then..., finally...")
- Ask follow-up questions when helpful
- Match the user's language and tone

## Examples
User (ASR): "What is the weather like in New youk?"
Assistant: "Did you mean New York? Let me check the weather there..."

User (ASR): "Tell me about the T F T's."
Assistant: "I'll tell you about ETFs—exchange-traded funds..."
"""


# ============================================================
# DeepSeek client
# ============================================================

summarize_client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)


# ============================================================
# LLM functions
# ============================================================

async def summarize_with_deepseek(text: str) -> str:
    """
    Summarize text using DeepSeek (cheaper model).
    Used for conversation summarization.
    """
    if not text.strip():
        return ""
    
    response = summarize_client.chat.completions.create(
        model=SUMMARIZE_MODEL,
        messages=[
            {"role": "system", "content": "You are a concise summarizer."},
            {"role": "user", "content": text}
        ],
        max_tokens=200,
        temperature=0.3,
        stream=False,
    )
    
    return response.choices[0].message.content.strip()