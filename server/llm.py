import argparse
import os

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

MODEL = "deepseek-v4-pro"
SUMMARIZE_MODEL = "deepseek-chat"  # cheaper model for summarization

BASE_URL = "https://api.deepseek.com"


SYSTEM_PROMPT = """
You are a helpful voice assistant.

Your responses will be converted directly into speech.

Therefore:

- Keep responses concise and natural.
- Do not use Markdown.
- Do not use tables.
- Avoid unnecessary formatting.
- Avoid very long explanations unless the user explicitly asks.
- Answer the user's request directly.
- You can understand and respond in multiple languages.
- Match the language used by the user whenever appropriate.
"""


# ============================================================
# DeepSeek clients
# ============================================================

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)

# Separate client for summarization (can use different params)
summarize_client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)


# ============================================================
# LLM functions
# ============================================================

def generate_response(user_input: str) -> str:
    """
    Generate response from user input (stateless, backward compatible).
    """
    return generate_response_with_history(user_input, [])


def generate_response_with_history(
    user_input: str, 
    history: list[dict] | None = None
) -> str:
    """
    Generate response with conversation history.
    
    Args:
        user_input: Current user message
        history: List of {"role": "user|assistant|system", "content": "..."} messages
                (excluding the current user input)
    """
    if not user_input.strip():
        raise ValueError("User input cannot be empty.")
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    if history:
        messages.extend(history)
    
    messages.append({"role": "user", "content": user_input})
    
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        reasoning_effort="high",
        extra_body={"thinking": {"type": "enabled"}},
        stream=False,
    )
    
    return response.choices[0].message.content


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


# ============================================================
# Command-line interface
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="DeepSeek V4 Pro LLM"
    )

    parser.add_argument(
        "input",
        help="Text received from ASR",
    )

    args = parser.parse_args()

    response = generate_response(args.input)

    print("\nResponse:")
    print(response)


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    main()