import argparse
import os

from dotenv import load_dotenv
from openai import OpenAI


# Load variables from .env
load_dotenv()


# ============================================================
# Configuration
# ============================================================

API_KEY = os.getenv("DEEPSEEK_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "DEEPSEEK_API_KEY not found in .env"
    )

MODEL = "deepseek-v4-pro"

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
# DeepSeek client
# ============================================================

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)


# ============================================================
# LLM function
# ============================================================

def generate_response(user_input: str) -> str:

    if not user_input.strip():
        raise ValueError(
            "User input cannot be empty."
        )

    response = client.chat.completions.create(
        model=MODEL,

        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_input,
            },
        ],

        # DeepSeek V4 Pro reasoning
        reasoning_effort="high",

        # DeepSeek-specific parameter
        # must be passed through extra_body
        extra_body={
            "thinking": {
                "type": "enabled"
            }
        },

        stream=False,
    )

    return response.choices[0].message.content


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

    response = generate_response(
        args.input
    )

    print("\nResponse:")
    print(response)


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    main()