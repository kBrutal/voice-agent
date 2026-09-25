import subprocess


HOST = "127.0.0.1"
PORT = "8080"
DEVICE = "metal"

ASR_MODEL = "nemotron-3.5"

TTS_MODEL = (
    "/Users/avinandan/Library/Caches/NeMoSpeech/models/"
    "nvidia/magpie_tts_multilingual_357m/"
    "452ef560f972c38d5fc16476259aac9456453547/"
    "magpie_tts_multilingual_357m.v2602.f16.gguf"
)

CODEC_MODEL = (
    "/Users/avinandan/Library/Caches/NeMoSpeech/models/"
    "nvidia/nemo-nano-codec-22khz-1.89kbps-21.5fps/"
    "fc00890b604aa2de298d2641ffc6c5f6caf8c4d7/"
    "nemo_nano_codec_22khz_1.89kbps_21.5fps.decoder.f16.gguf"
)

TOKENIZER_DIR = (
    "/Users/avinandan/Library/Caches/NeMoSpeech/models/"
    "nvidia/magpie_tts_multilingual_357m/"
    "452ef560f972c38d5fc16476259aac9456453547/"
    "tokenizer"
)


def main():
    command = [
        "nemo-speech",
        "serve",
        "--asr-model", ASR_MODEL,
        "--tts-model", TTS_MODEL,
        "--codec-model", CODEC_MODEL,
        "--tokenizer-dir", TOKENIZER_DIR,
        "--device", DEVICE,
        "--host", HOST,
        "--port", PORT,
        # Magpie can take longer than the default 30s socket timeout
        # to synthesize a full LLM reply.
        "--read-timeout", "600",
        "--write-timeout", "600",
    ]

    print("Starting NeMo Speech Server...")
    print(f"ASR:    {ASR_MODEL}")
    print("TTS:    Magpie Multilingual 357M")
    print("Codec:  NanoCodec")
    print(f"Device: {DEVICE}")
    print(f"URL:    http://{HOST}:{PORT}")
    print()

    try:
        subprocess.run(command, check=True)

    except KeyboardInterrupt:
        print("\nServer stopped.")

    except subprocess.CalledProcessError as e:
        print(f"\nServer exited with code {e.returncode}")


if __name__ == "__main__":
    main()