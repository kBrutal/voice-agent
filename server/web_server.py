import asyncio
import base64
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydub import AudioSegment

from .pipeline import process_audio
from .asr import transcribe
from .llm import generate_response
from .tts import synthesize
from .config import settings


# In-memory session storage (replace with Redis for production)
sessions: dict[str, dict] = {}


def convert_webm_to_wav(webm_data: bytes, target_sr: int = 16000) -> bytes:
    """Convert webm/opus audio to WAV (PCM 16-bit, mono, target_sr).
    
    Handles both complete webm files and concatenated MediaRecorder chunks.
    """
    with NamedTemporaryFile(suffix=".webm", delete=False) as webm_file:
        webm_file.write(webm_data)
        webm_path = webm_file.name
    
    try:
        # Load with pydub (uses ffmpeg) - try webm first
        try:
            audio = AudioSegment.from_file(webm_path, format="webm")
        except Exception:
            # If webm fails, try as raw opus/ogg
            audio = AudioSegment.from_file(webm_path, format="ogg")
        
        # Convert to target format
        audio = audio.set_frame_rate(target_sr).set_channels(1).set_sample_width(2)
        
        # Export to WAV bytes
        wav_path = webm_path.replace(".webm", ".wav")
        audio.export(wav_path, format="wav")
        
        with open(wav_path, "rb") as f:
            wav_data = f.read()
        
        Path(wav_path).unlink(missing_ok=True)
        return wav_data
    except Exception as e:
        Path(webm_path).unlink(missing_ok=True)
        raise RuntimeError(f"Audio conversion failed: {e}")
    finally:
        Path(webm_path).unlink(missing_ok=True)


def detect_audio_format(audio_data: bytes) -> str:
    """Detect audio format from header bytes.
    
    Returns:
        'webm' for webm/opus
        'wav' for WAV/PCM
        'raw' for raw PCM (no header)
    """
    if len(audio_data) < 4:
        return 'raw'
    
    # Check for webm/EBML header (starts with 0x1A 0x45 0xDF 0xA3)
    if audio_data[:4] == b'\x1a\x45\xdf\xa3':
        return 'webm'
    
    # Check for WAV header (RIFF)
    if audio_data[:4] == b'RIFF':
        return 'wav'
    
    # Check for OGG header
    if audio_data[:4] == b'OggS':
        return 'ogg'
    
    # Default: assume raw PCM
    return 'raw'


def ensure_wav_format(audio_data: bytes, sample_rate: int = 16000) -> bytes:
    """Ensure audio is in WAV format (PCM 16-bit, mono, 16kHz).
    
    Handles: webm/opus, WAV, raw PCM
    """
    fmt = detect_audio_format(audio_data)
    
    if fmt == 'webm':
        return convert_webm_to_wav(audio_data, target_sr=sample_rate)
    
    elif fmt == 'wav':
        # Already WAV - verify format and convert if needed
        with NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name
        
        try:
            audio = AudioSegment.from_file(tmp_path, format="wav")
            # Check if conversion needed
            if (audio.frame_rate != sample_rate or 
                audio.channels != 1 or 
                audio.sample_width != 2):
                audio = audio.set_frame_rate(sample_rate).set_channels(1).set_sample_width(2)
            
            wav_path = tmp_path.replace(".wav", "_converted.wav")
            audio.export(wav_path, format="wav")
            
            with open(wav_path, "rb") as f:
                wav_data = f.read()
            
            Path(wav_path).unlink(missing_ok=True)
            return wav_data
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    
    else:
        # Raw PCM - wrap in WAV container
        # Assume 16-bit mono at sample_rate
        import io
        import wave
        
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data)
        
        return wav_buffer.getvalue()


async def send_json(websocket: WebSocket, lock: asyncio.Lock, payload: dict) -> None:
    """Send a JSON message without racing other writers on the same socket."""
    async with lock:
        if websocket.client_state.name == "CONNECTED":
            await websocket.send_text(json.dumps(payload))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(exist_ok=True)
    
    # Initialize memory store
    from .memory import get_memory_store
    memory = get_memory_store()
    await memory.connect()
    
    yield
    
    # Shutdown
    sessions.clear()
    from .memory import get_memory_store
    store = get_memory_store()
    if store:
        await store.close()


app = FastAPI(title="Voice Assistant", lifespan=lifespan)

# Track active WebSocket connections
active_websockets: dict[str, WebSocket] = {}

# Serve static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def index():
    return FileResponse(static_dir / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    send_lock = asyncio.Lock()
    active_websockets[session_id] = websocket
    print(f"WebSocket connected: {session_id}")

    # User ID (single user for now)
    user_id = settings.default_user_id

    sessions[session_id] = {
        "audio_buffer": bytearray(),
        "sample_rate": 16000,
        "channels": 1,
        "busy": False,
        "send_lock": asyncio.Lock(),
    }
    session = sessions[session_id]
    process_task: asyncio.Task | None = None

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")
            print(f"WS {session_id} recv: {msg_type}")

            # Client keepalives must be drained or the socket buffers fill
            # and Uvicorn drops the connection during long TTS.
            if msg_type in ("pong", "ping"):
                continue

            if msg_type == "audio_chunk":
                chunk = base64.b64decode(message["data"])
                session["audio_buffer"].extend(chunk)
                print(f"  audio chunk: {len(chunk)} bytes, total: {len(session['audio_buffer'])}")

            elif msg_type == "audio_end":
                print(f"WS {session_id} audio_end, processing...")
                if session["busy"]:
                    await send_json(websocket, session["send_lock"], {
                        "type": "error",
                        "message": "Already processing a request",
                    })
                    continue
                session["busy"] = True
                process_task = asyncio.create_task(
                    process_session_audio(websocket, session_id, session)
                )

            elif msg_type == "config":
                session["sample_rate"] = message.get("sample_rate", 16000)
                session["channels"] = message.get("channels", 1)
                print(f"WS {session_id} config: {session['sample_rate']}Hz, {session['channels']}ch")

            elif msg_type == "interrupt":
                print(f"WS {session_id} interrupt received")
                session["busy"] = False
                if session.get("process_task") and not session["process_task"].done():
                    session["process_task"].cancel()

    except WebSocketDisconnect:
        print(f"Session {session_id} disconnected")
    except Exception as e:
        print(f"Error in session {session_id}: {e}")
        import traceback
        traceback.print_exc()
        try:
            await send_json(websocket, session["send_lock"], {
                "type": "error",
                "message": str(e),
            })
        except Exception:
            pass
    finally:
        if active_websockets.get(session_id) is websocket:
            active_websockets.pop(session_id, None)
        sessions.pop(session_id, None)


@app.get("/v1/models")
async def models():
    """OpenAI-compatible models endpoint."""
    return {
        "object": "list",
        "data": [
            {"id": "voice-assistant", "object": "model", "owned_by": "local"}
        ]
    }


async def process_session_audio(websocket: WebSocket, session_id: str, session: dict):
    """Process accumulated audio through ASR -> LLM -> TTS pipeline using full pipeline with memory."""
    send_lock: asyncio.Lock = session["send_lock"]
    tmp_path = None
    output_path = None
    session["busy"] = True

    async def emit(payload: dict) -> None:
        async with send_lock:
            if websocket.client_state.name == "CONNECTED":
                await websocket.send_text(json.dumps(payload))

    try:
        print(f"WS {session_id} process_session_audio start")

        webm_data = bytes(session["audio_buffer"])
        session["audio_buffer"] = bytearray()
        if not webm_data:
            print(f"WS {session_id} ERROR: No audio data received")
            await emit({
                "type": "error",
                "message": "No audio data received",
            })
            return

        print(f"WS {session_id} audio buffer: {len(webm_data)} bytes")
        await emit({"type": "status", "message": "Converting audio..."})

        sample_rate = session.get("sample_rate", 16000)
        wav_data = await asyncio.to_thread(
            ensure_wav_format, webm_data, sample_rate
        )
        print(f"WS {session_id} converted to WAV: {len(wav_data)} bytes")

        with NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(wav_data)
            tmp_path = tmp.name
        print(f"WS {session_id} saved temp file: {tmp_path}")

        await emit({"type": "status", "message": "Processing audio..."})

        # Step 1: ASR
        print(f"WS {session_id} calling ASR...")
        asr_result = await transcribe(tmp_path, "en-US")
        transcript = asr_result.get("text", "").strip()
        print(f"WS {session_id} ASR result: '{transcript}'")

        if not transcript:
            await emit({
                "type": "error",
                "message": "Could not understand audio",
            })
            return

        await emit({"type": "transcript", "text": transcript})
        await emit({"type": "status", "message": "Generating response..."})

        # Get history and generate response
        user_id = settings.default_user_id
        from .memory import get_memory_store
        memory = get_memory_store()
        await memory.connect()
        
        history = await memory.get_history_as_messages(settings.default_user_id, session_id)
        
        print(f"WS {session_id} calling LLM with history...")
        from .llm import generate_response_with_history
        response_text = await asyncio.to_thread(generate_response_with_history, transcript, history)
        preview = (response_text or "")[:50]
        print(f"WS {session_id} LLM response: '{preview}...'")

        if not (response_text or "").strip():
            await emit({
                "type": "error",
                "message": "Empty response from LLM",
            })
            return

        # Store in memory
        await memory.add_turn(settings.default_user_id, session_id, "user", transcript)
        await memory.add_turn(settings.default_user_id, session_id, "assistant", response_text)

        # TTS Synthesis
        await emit({"type": "status", "message": "Synthesizing speech..."})

        output_path = f"/tmp/response_{session_id}.wav"
        print(f"WS {session_id} calling TTS...")
        from .tts import synthesize
        await synthesize(
            text=response_text,
            language="en-US",
            voice="default",
            output_path=output_path,
        )
        print(f"WS {session_id} TTS done: {output_path}")

        # Read audio data
        with open(output_path, "rb") as f:
            audio_data = f.read()

        print(f"WS {session_id} sending {len(audio_data)} bytes audio in chunks")

        # Split response text into sentences for synchronized streaming
        import re
        sentences = re.split(r'(?<=[.!?])\s+', response_text.strip())
        if not sentences:
            sentences = [response_text]
        
        # Calculate audio bytes per sentence (rough estimation)
        total_audio_bytes = len(audio_data)
        bytes_per_sentence = total_audio_bytes // max(len(sentences), 1)
        
        await emit({"type": "status", "message": "Speaking..."})
        
        # Stream text and audio together
        audio_offset = 0
        chunk_size = 16384
        
        for i, sentence in enumerate(sentences):
            # Send text chunk
            await emit({
                "type": "response_chunk",
                "text": sentence + (" " if i < len(sentences) - 1 else ""),
                "is_final": i == len(sentences) - 1
            })
            
            # Send corresponding audio chunks
            sentence_audio_bytes = min(bytes_per_sentence, total_audio_bytes - audio_offset)
            if sentence_audio_bytes <= 0:
                sentence_audio_bytes = min(chunk_size, total_audio_bytes - audio_offset)
            
            # Send audio in smaller chunks for smooth playback
            while sentence_audio_bytes > 0:
                send_chunk = min(chunk_size, sentence_audio_bytes)
                chunk = audio_data[audio_offset:audio_offset + send_chunk]
                await emit({
                    "type": "audio_chunk",
                    "data": base64.b64encode(chunk).decode(),
                    "is_final": False
                })
                audio_offset += send_chunk
                sentence_audio_bytes -= send_chunk
                await asyncio.sleep(0.01)  # Small delay for smooth streaming
        
        # Send any remaining audio
        while audio_offset < total_audio_bytes:
            send_chunk = min(chunk_size, total_audio_bytes - audio_offset)
            chunk = audio_data[audio_offset:audio_offset + send_chunk]
            await emit({
                "type": "audio_chunk",
                "data": base64.b64encode(chunk).decode(),
                "is_final": audio_offset + send_chunk >= total_audio_bytes
            })
            audio_offset += send_chunk
            await asyncio.sleep(0.01)

        await emit({"type": "audio_end"})
        await emit({"type": "status", "message": "Ready"})

    except asyncio.CancelledError:
        print(f"WS {session_id} processing cancelled")
        raise
    except Exception as e:
        print(f"WS {session_id} processing error: {e}")
        import traceback
        traceback.print_exc()
        try:
            await emit({
                "type": "error",
                "message": f"Processing error: {str(e)}",
            })
        except Exception:
            pass
    finally:
        session["busy"] = False
        # cleanup temp files
        import glob
        for f in glob.glob(f"/tmp/*{session_id}*.wav"):
            try:
                Path(f).unlink(missing_ok=True)
            except Exception:
                pass


# Streaming version (LLM tokens -> TTS streaming)
@app.websocket("/ws/stream/{session_id}")
async def websocket_stream_endpoint(websocket: WebSocket, session_id: str):
    """Streaming version: LLM tokens feed TTS incrementally."""
    await websocket.accept()
    
    try:
        # Receive complete audio first
        audio_chunks = []
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message["type"] == "audio_chunk":
                audio_chunks.append(base64.b64decode(message["data"]))
            elif message["type"] == "audio_end":
                break
        
        # Convert audio to WAV (handles webm, wav, raw PCM)
        webm_data = b"".join(audio_chunks)
        if not webm_data:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "No audio data received"
            }))
            return
        
        await websocket.send_text(json.dumps({
            "type": "status",
            "message": "Converting audio..."
        }))
        
        sample_rate = 16000  # default
        wav_data = ensure_wav_format(webm_data, sample_rate=sample_rate)
        
        # Save converted WAV to temp file
        with NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(wav_data)
            tmp_path = tmp.name
        
        # ASR (always use en-US)
        asr_result = await transcribe(tmp_path, "en-US")
        transcript = asr_result.get("text", "").strip()
        
        await websocket.send_text(json.dumps({
            "type": "transcript",
            "text": transcript
        }))
        
        # Streaming LLM -> TTS
        # Note: This requires modifying llm.py to support streaming
        # For now, use non-streaming but send TTS in chunks
        response_text = generate_response(transcript)
        
        await websocket.send_text(json.dumps({
            "type": "response_text",
            "text": response_text
        }))
        
        output_path = f"/tmp/response_{session_id}.wav"
        await synthesize(
            text=response_text,
            language="en-US",
            voice="default",
            output_path=output_path,
        )
        
        with open(output_path, "rb") as f:
            audio_data = f.read()
        
        chunk_size = 16384
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i + chunk_size]
            await websocket.send_text(json.dumps({
                "type": "audio_chunk",
                "data": base64.b64encode(chunk).decode(),
                "is_final": i + chunk_size >= len(audio_data)
            }))
            await asyncio.sleep(0.01)
        
        await websocket.send_text(json.dumps({"type": "audio_end"}))
        
        Path(tmp_path).unlink(missing_ok=True)
        Path(output_path).unlink(missing_ok=True)
        
    except Exception as e:
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": str(e)
        }))
    finally:
        await websocket.close()


@app.get("/v1/models")
async def models():
    """OpenAI-compatible models endpoint."""
    return {
        "object": "list",
        "data": [
            {"id": "voice-assistant", "object": "model", "owned_by": "local"}
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)