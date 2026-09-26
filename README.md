# Voice Assistant

Real-time voice AI chat with conversation memory. Speak to an AI and hear it respond, with full context from previous conversations.

## Features

- **Voice Interface**: Record → transcribe (ASR) → generate response (LLM) → synthesize speech (TTS)
- **Conversation Memory**: MongoDB Atlas stores history with auto-summarization
- **Session Management**: Multiple conversations with history sidebar
- **Interrupt Anytime**: Stop recording, processing, or playback mid-stream

## Tech Stack

| Layer | Technology |
|-------|-----------|
| ASR | NeMo Speech (Nemotron 3.5) |
| LLM | DeepSeek V4 Pro |
| TTS | NeMo Speech (Magpie Multilingual) |
| Database | MongoDB Atlas |
| Server | FastAPI + WebSocket |
| Client | React + Vite |

## Project Structure

```
va/
├── server/
│   ├── asr.py          # ASR client
│   ├── llm.py          # DeepSeek LLM with memory
│   ├── tts.py          # TTS client
│   ├── pipeline.py     # Full pipeline (CLI)
│   ├── web_server.py   # WebSocket server
│   ├── config.py       # Settings from .env
│   ├── memory/         # MongoDB memory with summarization
│   └── static/         # Old HTML client
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
# Single audio file (with session memory)
uv run python -m server.pipeline samples/audio.wav --session-id my_session

# Interactive recording
uv run python -m client.cli_client --loop
```

## Configuration

Edit `server/config.py` or set environment variables:

| Var | Default | Description |
|-----|---------|-------------|
| `MEMORY_MAX_TURNS` | 10 | History turns injected into LLM |
| `MEMORY_SUMMARIZE_THRESHOLD` | 20 | Auto-summarize after N turns |