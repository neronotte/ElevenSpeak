#!/usr/bin/env python
"""Riproduce on-the-fly un testo con ElevenLabs (streaming), con cache a tempo dell'ultima nota per voce.

Esempi:
    python eleven_say.py "Ciao mondo" --voice Rachel
    python eleven_say.py "Ciao mondo" --voice 21m00Tcm4TlvDq8ikWAM --model eleven_v3
    python eleven_say.py --replay --voice Rachel
    python eleven_say.py --list-voices
    echo "testo da stdin" | python eleven_say.py --voice Rachel
"""

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
import threading
import time
import wave
from contextlib import contextmanager
from pathlib import Path

import portalocker
import sounddevice as sd
from elevenlabs.client import ElevenLabs

SAMPLE_RATE = 24000
OUTPUT_FORMAT = f"pcm_{SAMPLE_RATE}"  # PCM 16-bit mono little-endian
DEFAULT_VOICE = "21m00Tcm4TlvDq8ikWAM"
DEFAULT_MODEL = "eleven_v4"
DEFAULT_TTL_MIN = 30
CACHE_DIR = Path(os.environ.get("ELEVEN_SAY_CACHE", Path(os.environ.get("LOCALAPPDATA", Path.home())) / "eleven_say" / "cache"))
LOCK_PATH = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "eleven_say" / "playback.lock"


def positive_seconds(value: str) -> float:
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("Il timeout deve essere un numero positivo e finito.")
    return seconds


@contextmanager
def operation_watchdog(timeout: float):
    cancelled = threading.Event()

    def expire() -> None:
        if not cancelled.wait(timeout):
            message = f"Timeout: operazione vocale oltre {timeout:g} secondi; processo interrotto.\n"
            try:
                os.write(2, message.encode("utf-8"))
            finally:
                os._exit(124)

    watchdog = threading.Thread(target=expire, name="eleven-say-watchdog", daemon=True)
    watchdog.start()
    try:
        yield
    finally:
        cancelled.set()
        watchdog.join()


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def cache_path(voice_key: str) -> Path:
    return CACHE_DIR / f"{hashlib.sha1(voice_key.lower().encode()).hexdigest()[:16]}.wav"


def purge_cache(ttl_min: float) -> None:
    if not CACHE_DIR.exists():
        return
    limit = time.time() - ttl_min * 60
    for f in CACHE_DIR.iterdir():
        if f.suffix not in (".wav", ".tmp") and f.name != "voices.json":
            continue
        try:
            if f.suffix == ".tmp" or f.stat().st_mtime < limit:
                f.unlink()
        except OSError as exc:
            print(f"Impossibile pulire la cache {f.name}: {exc}", file=sys.stderr)


@contextmanager
def atomic_cache_file(destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f"{destination.stem}-", suffix=".tmp", dir=destination.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        yield temporary
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def resolve_voice(client: ElevenLabs, voice: str) -> str:
    """Accetta un voice_id o un nome di voce; restituisce il voice_id."""
    idx_file = CACHE_DIR / "voices.json"
    idx = json.loads(idx_file.read_text(encoding="utf-8")) if idx_file.exists() else {}
    if voice.lower() in idx:
        return idx[voice.lower()]
    res = client.voices.search(search=voice, page_size=50, request_options={"max_retries": 0})
    for v in res.voices:
        if voice in (v.voice_id,) or v.name.lower() == voice.lower() or v.name.lower().startswith(voice.lower()):
            idx[voice.lower()] = v.voice_id
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with atomic_cache_file(idx_file) as temporary:
                temporary.write_text(json.dumps(idx), encoding="utf-8")
            return v.voice_id
    return voice  # presumibilmente già un voice_id


def speak(client: ElevenLabs, text: str, voice_id: str, model: str, cache_file: Path, use_cache: bool) -> None:
    audio = client.text_to_speech.stream(voice_id=voice_id, text=text, model_id=model, output_format=OUTPUT_FORMAT, request_options={"max_retries": 0})
    buffer = bytearray()
    pending = b""
    with sd.RawOutputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as out:
        for chunk in audio:
            if not chunk:
                continue
            data = pending + chunk
            cut = len(data) - (len(data) % 2)  # allinea ai campioni a 16 bit
            data, pending = data[:cut], data[cut:]
            if data:
                out.write(data)
                if use_cache:
                    buffer.extend(data)
    if pending:
        raise ValueError("Stream audio incompleto: campione PCM troncato.")
    if use_cache and buffer:
        with atomic_cache_file(cache_file) as tmp:
            with wave.open(str(tmp), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SAMPLE_RATE)
                w.writeframes(bytes(buffer))


def replay(cache_file: Path, voice: str) -> int:
    if not cache_file.exists():
        print(f"Nessuna nota in cache (o scaduta) per la voce '{voice}'.", file=sys.stderr)
        return 1
    with wave.open(str(cache_file), "rb") as w:
        rate, frames = w.getframerate(), w.readframes(w.getnframes())
    with sd.RawOutputStream(samplerate=rate, channels=1, dtype="int16") as out:
        out.write(frames)
    return 0


def run_operation(args: argparse.Namespace, text: str, api_key: str | None) -> int:
    purge_cache(args.ttl)
    if args.replay:
        idx_file = CACHE_DIR / "voices.json"
        idx = json.loads(idx_file.read_text(encoding="utf-8")) if idx_file.exists() else {}
        return replay(cache_path(idx.get(args.voice.lower(), args.voice)), args.voice)

    client = ElevenLabs(api_key=api_key, timeout=args.http_timeout)
    if args.list_voices:
        for v in client.voices.search(page_size=100, request_options={"max_retries": 0}).voices:
            print(f"{v.voice_id}  {v.name}")
        return 0

    voice_id = resolve_voice(client, args.voice)
    speak(client, text.strip(), voice_id, args.model, cache_path(voice_id), not args.no_cache)
    return 0


def main() -> int:
    off_file = Path(__file__).resolve().with_name(".off")
    if off_file.is_file():
        print("ElevenLabs disattivato: file .off presente.", file=sys.stderr)
        return 0

    p = argparse.ArgumentParser(description="Text-to-speech on-the-fly con ElevenLabs.")
    p.add_argument("text", nargs="?", help="Testo da riprodurre (se omesso, letto da stdin).")
    p.add_argument("-v", "--voice", default=os.environ.get("ELEVENLABS_VOICE", DEFAULT_VOICE), help="Nome o ID della voce.")
    p.add_argument("-m", "--model", default=os.environ.get("ELEVENLABS_MODEL", DEFAULT_MODEL), help=f"Modello (default {DEFAULT_MODEL}; es. eleven_v3, eleven_multilingual_v2).")
    p.add_argument("-r", "--replay", action="store_true", help="Riproduce l'ultima nota generata con la voce indicata.")
    p.add_argument("--ttl", type=float, default=float(os.environ.get("ELEVEN_SAY_TTL_MIN", DEFAULT_TTL_MIN)), help=f"Durata cache in minuti (default {DEFAULT_TTL_MIN}).")
    p.add_argument("--no-cache", action="store_true", help="Non salvare l'audio in cache.")
    p.add_argument("--list-voices", action="store_true", help="Elenca le voci disponibili.")
    p.add_argument("--api-key", help="API key (altrimenti ELEVENLABS_API_KEY o file .env.local/.env).")
    p.add_argument("--lock-timeout", type=positive_seconds, default=120.0, help="Attesa massima del turno in secondi (default 120; ordine FIFO non garantito).")
    p.add_argument("--operation-timeout", type=positive_seconds, default=180.0, help="Limite generazione e riproduzione in secondi, dopo il lock (default 180).")
    p.add_argument("--http-timeout", type=positive_seconds, default=30.0, help="Timeout delle operazioni HTTP in secondi (default 30).")
    args = p.parse_args()

    for env in (Path.cwd() / ".env.local", Path.cwd() / ".env", Path(__file__).with_name(".env.local"), Path(__file__).with_name(".env")):
        load_env_file(env)

    api_key = args.api_key or os.environ.get("ELEVENLABS_API_KEY")
    if not args.replay and not api_key:
        p.error("API key mancante: usa --api-key o ELEVENLABS_API_KEY.")

    text = ""
    if not args.replay and not args.list_voices:
        if args.text is None and sys.stdin.isatty():
            p.error("Specifica il testo oppure passalo tramite stdin.")
        text = args.text if args.text is not None else sys.stdin.read()
        if not text.strip():
            p.error("Nessun testo da riprodurre.")

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock = portalocker.Lock(str(LOCK_PATH), mode="a", timeout=args.lock_timeout, check_interval=0.1)
    try:
        lock.acquire()
    except portalocker.exceptions.LockException:
        print(f"Timeout: turno audio non disponibile entro {args.lock_timeout:g} secondi.", file=sys.stderr)
        return 75
    try:
        if off_file.is_file():
            print("ElevenLabs disattivato: file .off presente.", file=sys.stderr)
            return 0
        with operation_watchdog(args.operation_timeout):
            return run_operation(args, text, api_key)
    finally:
        lock.release()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
