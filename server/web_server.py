import asyncio
import base64
import json
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydub import AudioSegment
from pymongo.errors import PyMongoError

from .asr import transcribe
from .agent import get_agent, AgentStep
from .language import DEFAULT_LANGUAGE, detect_language, language_name
from .tts import split_for_tts, synthesize
from .memory import get_memory_store
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


def short_error(e: Exception, limit: int = 160) -> str:
    """First line of an exception message, truncated — pymongo errors can be kilobytes long."""
    first_line = str(e).splitlines()[0] if str(e) else type(e).__name__
    first_line = first_line.split(",SSL handshake failed")[0]
    return first_line if len(first_line) <= limit else first_line[:limit] + "…"


async def send_json(websocket: WebSocket, lock: asyncio.Lock, payload: dict) -> None:
    """Send a JSON message without racing other writers on the same socket."""
    async with lock:
        if websocket.client_state.name == "CONNECTED":
            await websocket.send_text(json.dumps(payload))


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await get_memory_store().connect()
    except PyMongoError as e:
        print(f"WARNING: MongoDB unavailable, running without conversation memory: {short_error(e)}")

    yield

    # Shutdown
    sessions.clear()
    await get_memory_store().close()


app = FastAPI(title="Voice Assistant", lifespan=lifespan)

# Track active WebSocket connections
active_websockets: dict[str, WebSocket] = {}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    active_websockets[session_id] = websocket
    print(f"WebSocket connected: {session_id}")

    sessions[session_id] = {
        "audio_buffer": bytearray(),
        "sample_rate": 16000,
        "channels": 1,
        "busy": False,
        "send_lock": asyncio.Lock(),
    }
    session = sessions[session_id]

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
                session["process_task"] = asyncio.create_task(
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
        asr_result = await transcribe(tmp_path, "auto")
        transcript = asr_result.get("text", "").strip()
        print(f"WS {session_id} ASR result: '{transcript}'")

        user_language = detect_language(
            transcript,
            asr_hint=asr_result.get("language"),
            fallback=session.get("language", DEFAULT_LANGUAGE),
        )
        session["language"] = user_language
        print(f"WS {session_id} detected language: {user_language}")

        if not transcript:
            await emit({
                "type": "error",
                "message": "Could not understand audio",
            })
            return

        await emit({"type": "transcript", "text": transcript})
        await emit({"type": "status", "message": "Generating response..."})

        # Memory is best-effort: if MongoDB is unreachable, answer without history
        # rather than failing the whole turn.
        memory = get_memory_store()
        memory_ok = True
        try:
            await memory.connect()
            history = await memory.get_history_as_messages(settings.default_user_id, session_id)
        except PyMongoError as e:
            memory_ok = False
            history = []
            print(f"WS {session_id} WARNING: memory unavailable, continuing without history: {short_error(e)}")

        print(f"WS {session_id} running agent with history...")

        async def emit_step(step: AgentStep) -> None:
            await emit({
                "type": "agent_step",
                "kind": step.kind,
                "content": step.content,
                "tool_name": step.tool_name,
                "tool_args": step.tool_args,
            })

        agent = get_agent()
        agent_result = await agent.run(
            transcript, history, on_step=emit_step, language=language_name(user_language)
        )
        response_text = agent_result.final_response
        preview = (response_text or "")[:50]
        print(f"WS {session_id} agent response: '{preview}...'")

        if not (response_text or "").strip():
            await emit({
                "type": "error",
                "message": "Empty response from LLM",
            })
            return

        if memory_ok:
            try:
                await memory.add_turn(settings.default_user_id, session_id, "user", transcript)
                await memory.add_turn(settings.default_user_id, session_id, "assistant", response_text)
            except PyMongoError as e:
                print(f"WS {session_id} WARNING: failed to save turn to memory: {short_error(e)}")

        # TTS runs slower than real time and the speech server only returns
        # whole clips, so synthesize chunk by chunk: the client plays chunk i
        # while chunk i+1 is being generated.
        await emit({"type": "status", "message": "Synthesizing speech..."})

        tts_language = detect_language(response_text, fallback=user_language)
        chunks = split_for_tts(response_text)
        print(f"WS {session_id} TTS ({tts_language}) in {len(chunks)} chunk(s)")

        for i, chunk in enumerate(chunks):
            output_path = f"/tmp/response_{session_id}_{i}.wav"
            await synthesize(
                text=chunk,
                language=tts_language,
                voice="default",
                output_path=output_path,
            )
            audio_data = Path(output_path).read_bytes()
            Path(output_path).unlink(missing_ok=True)

            await emit({
                "type": "audio_segment",
                "index": i,
                "text": chunk,
                "data": base64.b64encode(audio_data).decode(),
                "is_last": i == len(chunks) - 1,
            })
            if i == 0:
                await emit({"type": "status", "message": "Speaking..."})

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
                "message": f"Processing error: {short_error(e)}",
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)