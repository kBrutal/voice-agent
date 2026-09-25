# Voice Assistant Client

Python clients for the Voice Assistant WebSocket server.

## Installation (using uv)

```bash
# From project root
uv sync --extra client

# Or install client dependencies only
uv pip install -e ".[client]"
```

Requires:
- `pyaudio` - for microphone recording (CLI client)
- `websockets` - for WebSocket communication

## Quick Start

### 1. Start the Server

```bash
# Terminal 1: Start NeMo Speech Server
cd /path/to/va
uv run python -m server.start

# Terminal 2: Start WebSocket Server
uv run python -m server.web_server
```

### 2. Run CLI Client

```bash
# Terminal 3: Run CLI client
uv run python -m client.cli_client
```

Press **Enter** to start recording, speak, press **Enter** again to stop.

### 3. Use as Library

```bash
# Run a script using the client library
uv run python your_script.py
```

```python
import asyncio
from client import VoiceAssistantClient, quick_conversation

# Simple one-shot
async def main():
    with open("input.wav", "rb") as f:
        audio = f.read()
    
    transcript, response, audio_out = await quick_conversation(audio)
    print(f"You: {transcript}")
    print(f"Bot: {response}")
    
    with open("response.wav", "wb") as f:
        f.write(audio_out)

asyncio.run(main())
```

## Client Types

| Client | File | Use Case |
|--------|------|----------|
| **CLI Client** | `cli_client.py` | Interactive terminal use |
| **Library** | `voice_client.py` | Embed in your apps |
| **Examples** | `example_usage.py` | Learning/reference |

## CLI Client Options

```bash
uv run python -m client.cli_client --help

Options:
  --server URL       WebSocket server (default: ws://localhost:8000)
  --duration SECONDS Max recording time (default: 10)
  --rate HZ          Sample rate (default: 16000)
  --loop             Continuous conversation mode
```

## Library API

### `VoiceAssistantClient`

```python
client = VoiceAssistantClient(
    server_url="ws://localhost:8000",
    config=VoiceConfig(sample_rate=16000, channels=1),
    session_id="my_session"  # optional
)

await client.connect()

# Process complete audio
transcript, response_text, response_audio = await client.process_audio(audio_bytes)

# Or stream audio
await client.send_audio_stream(audio_chunk_iterator)

# Or callback-based
await client.receive_messages(
    on_transcript=lambda t: print(t),
    on_response_text=lambda r: print(r),
    on_audio_chunk=lambda a: play(a),
)

await client.disconnect()
```

### `quick_conversation()` - Convenience Function

```python
from client import quick_conversation

transcript, response, audio = await quick_conversation(audio_bytes)
```

## WebSocket Protocol

The client communicates with `server/web_server.py` using:

**Client → Server:**
```json
{ "type": "config", "sample_rate": 16000, "channels": 1 }
{ "type": "audio_chunk", "data": "base64..." }
{ "type": "audio_end" }
```

**Server → Client:**
```json
{ "type": "transcript", "text": "hello" }
{ "type": "response_text", "text": "Hi there!" }
{ "type": "audio_chunk", "data": "base64...", "is_final": false }
{ "type": "audio_end" }
{ "type": "status", "message": "Processing..." }
{ "type": "error", "message": "..." }
```

## Audio Format

- **Input**: 16-bit PCM, mono, 16kHz (raw bytes)
- **Output**: 16-bit PCM, mono, 22.05kHz (WAV from TTS)

## Debug Files

CLI client saves debug recordings to `/tmp/voice_assistant_debug/`:
- `input.wav` - What you recorded
- `output.wav` - Server response

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `pyaudio` install fails | `brew install portaudio` (macOS) or `apt install portaudio19-dev` (Linux), then `uv pip install pyaudio` |
| Connection refused | Ensure `server/web_server.py` is running on port 8000 (`uv run python -m server.web_server`) |
| No audio output | Check `response_audio` length > 0, verify TTS server running |
| High latency | See server optimization notes in `server/pipeline.py` |