# Voice Assistant

Real-time voice AI chat with conversation memory and an agentic loop. Speak to an AI and hear it respond, with full context from previous conversations and the ability to search the web when it needs current information.

## Features

- **Voice Interface**: Record → transcribe (ASR) → agent response (LLM + tools) → synthesize speech (TTS)
- **Agent Loop**: Observe → Reason → Act → Observe → ... → Finish, with tool calling (web search) and plain conversational replies for simple turns
- **Multilingual + Hinglish**: An ASR gate transcribes each utterance as English, Hindi, and auto-detect, then `deepseek-flash` merges them into the final input (English, Hindi, code-mixed Hinglish, or another language). Replies come back in the user's language — English, Spanish, German, French, Italian, Vietnamese, Hindi, or Hinglish (written in Devanagari so the Hindi voice can pronounce it)
- **Conversation Memory**: MongoDB Atlas stores history with auto-summarization
- **Session Management**: Multiple conversations with history sidebar
- **Interrupt Anytime**: Stop recording, processing, or playback mid-stream

## Tech Stack

| Layer | Technology |
|-------|-----------|
| ASR | NeMo Speech (Nemotron 3.5) |
| Agent / LLM | DeepSeek V4 Pro (tool calling) + DuckDuckGo web search |
| TTS | NeMo Speech (Magpie Multilingual) |
| Database | MongoDB Atlas |
| Server | FastAPI + WebSocket |
| Client | React + Vite |

## Project Structure

```
va/
├── server/
│   ├── asr.py          # ASR client (serialized; the speech server corrupts overlapping requests)
│   ├── asr_gate.py     # en/hi/auto transcripts → deepseek-flash → final input + mode
│   ├── llm.py          # DeepSeek client + summarization (used by memory)
│   ├── tts.py          # TTS client
│   ├── language.py     # Spoken-language detection → TTS locale
│   ├── agent/          # Single-agent Observe/Reason/Act/Finish loop + tools
│   │   ├── agent.py    # Agent class, get_agent(), CLI
│   │   └── tools/      # Tool base/registry, web_search (DuckDuckGo)
│   ├── pipeline.py     # Full pipeline (CLI)
│   ├── web_server.py   # WebSocket server
│   ├── config.py       # Settings from .env
│   └── memory/         # MongoDB memory with summarization
├── client-react/       # React frontend
└── client/             # Python CLI client
```

## Quick Start

### 1. Setup

Create `.env` in project root:

```bash
DEEPSEEK_API_KEY=your_key_here
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/voice_assistant
```

### 2. Install Dependencies

```bash
# Python
uv sync --extra client

# React client
cd client-react && npm install
```

### 3. Run

```bash
# Terminal 1: NeMo Speech Server (takes ~30s to start)
uv run python -m server.start

# Terminal 2: WebSocket Server
uv run python -m server.web_server

# Terminal 3: React Client
cd client-react && npm run dev
```

Open http://localhost:5173

## Run from Project Root Only

Use `--directory` if you want to avoid `cd`:

```bash
cd /path/to/va        # from client-react/
npm run dev --directory client-react
```

## CLI Usage

```bash
# Single audio file (with session memory), runs through the agent
uv run python -m server.pipeline samples/audio.wav --session-id my_session

# Interactive recording
uv run python -m client.cli_client --loop

# Agent only (text in, text out) — no ASR/TTS/Mongo required
uv run python -m server.agent.agent "what's today's date and any major tech news?"
```

The agent CLI auto-detects the input language too, e.g.
`uv run python -m server.agent.agent "¿Cuál es la capital de Australia?"` replies in Spanish.
To check detection on its own: `uv run python -m server.language "Wie spät ist es?"`.
To see what the ASR gate makes of a recording: `uv run python -m server.asr_gate path/to/audio.wav`.

The agent CLI prints each step of the Observe → Reason → Act → Finish loop as it
runs (e.g. `[tool_call] Calling web_search(...)`, `[tool_result] ...`), followed
by the final response — useful for testing the web search tool in isolation.

## Configuration

Edit `server/config.py` or set environment variables:

| Var | Default | Description |
|-----|---------|-------------|
| `MEMORY_MAX_TURNS` | 10 | History turns injected into LLM |
| `MEMORY_SUMMARIZE_THRESHOLD` | 20 | Auto-summarize after N turns |
| `AGENT_MAX_ITERATIONS` | 6 | Max Reason/Act loop iterations before forcing a final answer |
| `AGENT_SEARCH_MAX_RESULTS` | 5 | Max results returned per web search |