"""Generate local Kokoro speech files for debate arguments."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import urllib.request
from pathlib import Path
from typing import Protocol

from debate_app.models import Debater

_MODEL_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.1/kokoro-v1.0.int8.onnx"
)
_VOICES_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.1/voices-v1.0.bin"
)


class SpeechGenerator(Protocol):
    """The small interface shared by local speech engines."""

    def prepare(self) -> None: ...

    def generate(self, text: str, debater: Debater, output_path: Path) -> None: ...

    def close(self) -> None: ...


def make_speech_generator(
    model: str, model_directory: Path, pocket_voices: tuple[str, ...] = ()
) -> SpeechGenerator:
    """Build the selected local speech engine."""
    if model == "kokoro":
        return KokoroSpeechGenerator(model_directory)
    if model == "chatterbox-nano":
        return ChatterboxNanoSpeechGenerator()
    if model == "pocket-tts":
        return PocketTtsSpeechGenerator(pocket_voices)
    raise ValueError(f"Unknown TTS model: {model}")


class KokoroSpeechGenerator:
    """Load Kokoro once, then save each spoken argument as a WAV file."""

    def __init__(self, model_directory: Path) -> None:
        self.model_directory = model_directory
        self.model_path = model_directory / "kokoro-v1.0.int8.onnx"
        self.voices_path = model_directory / "voices-v1.0.bin"
        self._engine = None

    def prepare(self) -> None:
        """Download assets and load Kokoro before the first argument arrives."""
        self._ensure_models()
        self._load_engine()

    def generate(self, text: str, debater: Debater, output_path: Path) -> None:
        """Create speech with the chosen voice and atomically save the WAV."""
        self.prepare()
        samples, sample_rate = self._engine.create(
            text,
            voice=debater.voice,
            speed=1.0,
            lang="en-gb" if debater.voice.startswith(("bf_", "bm_")) else "en-us",
        )
        _write_wav(output_path, samples, sample_rate)

    def close(self) -> None:
        """Kokoro has no separate worker process to close."""

    def _ensure_models(self) -> None:
        self.model_directory.mkdir(parents=True, exist_ok=True)
        self._download_if_missing(self.model_path, _MODEL_URL)
        self._download_if_missing(self.voices_path, _VOICES_URL)

    @staticmethod
    def _download_if_missing(path: Path, url: str) -> None:
        if path.is_file():
            return

        temporary_path = path.with_name(f".{path.name}.download")
        print(f"Downloading local Kokoro asset: {path.name}", flush=True)
        try:
            with (
                urllib.request.urlopen(url, timeout=120) as response,
                temporary_path.open("wb") as destination,
            ):
                shutil.copyfileobj(response, destination)
                destination.flush()
                os.fsync(destination.fileno())
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)

    def _load_engine(self):
        if self._engine is None:
            from kokoro_onnx import Kokoro

            self._engine = Kokoro(str(self.model_path), str(self.voices_path))
        return self._engine


class ChatterboxNanoSpeechGenerator:
    """Talk to a separate Chatterbox environment with one reference per role."""

    def __init__(self) -> None:
        self._runtime_project = (
            Path(__file__).resolve().parent.parent / "chatterbox_runtime"
        )
        self._worker_path = self._runtime_project / "worker.py"
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    def prepare(self) -> None:
        """Load the isolated runtime and Chatterbox weights before a debate."""
        if self._process is not None:
            return
        print("Starting Chatterbox-Nano's isolated Python runtime...", flush=True)
        self._process = subprocess.Popen(
            [
                "uv",
                "run",
                "--project",
                str(self._runtime_project),
                "python",
                str(self._worker_path),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        try:
            self._request({"command": "prepare"})
        except Exception:
            self.close()
            raise

    def generate(self, text: str, debater: Debater, output_path: Path) -> None:
        """Speak with Nano's built-in voice or this role's reference recording."""
        if (
            debater.voice_reference is not None
            and not debater.voice_reference.is_file()
        ):
            raise FileNotFoundError(
                f"Voice reference file not found: {debater.voice_reference}"
            )
        self.prepare()
        request = {
            "command": "generate",
            "text": text,
            "output_path": str(output_path),
        }
        if debater.voice_reference is not None:
            request["voice_reference"] = str(debater.voice_reference)
        self._request(request)

    def close(self) -> None:
        """Stop the worker after all queued speech has finished."""
        with self._lock:
            process = self._process
            if process is None:
                return
            self._process = None
            if process.poll() is None and process.stdin is not None:
                try:
                    process.stdin.write('{"command":"close"}\n')
                    process.stdin.flush()
                    process.stdin.close()
                    process.wait(timeout=10)
                except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            if process.stdout is not None:
                process.stdout.close()
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()

    def _request(self, payload: dict[str, object]) -> None:
        """Send one job to the persistent worker and wait for its result."""
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None:
                raise RuntimeError("The Chatterbox-Nano worker is not running.")
            if process.stdin is None or process.stdout is None:
                raise RuntimeError("The Chatterbox-Nano worker pipes are unavailable.")

            process.stdin.write(json.dumps(payload) + "\n")
            process.stdin.flush()
            result_line = process.stdout.readline()
            if not result_line:
                raise RuntimeError("The Chatterbox-Nano worker stopped unexpectedly.")
            try:
                result = json.loads(result_line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "The Chatterbox-Nano worker returned invalid data."
                ) from exc
            if not isinstance(result, dict) or not result.get("ok"):
                message = result.get("error") if isinstance(result, dict) else None
                raise RuntimeError(
                    message or "Chatterbox-Nano could not finish the request."
                )


class PocketTtsSpeechGenerator:
    """Keep Pocket TTS and its preset voice states warm in a local worker."""

    def __init__(self, voices: tuple[str, ...]) -> None:
        self._runtime_project = (
            Path(__file__).resolve().parent.parent / "pocket_runtime"
        )
        self._worker_path = self._runtime_project / "worker.py"
        self._voices = tuple(dict.fromkeys(voices))
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    def prepare(self) -> None:
        """Load Pocket TTS and cache each configured preset voice before debate."""
        if self._process is not None:
            return
        print("Starting Pocket TTS's isolated Python runtime...", flush=True)
        self._process = subprocess.Popen(
            [
                "uv",
                "run",
                "--project",
                str(self._runtime_project),
                "python",
                str(self._worker_path),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        try:
            self._request({"command": "prepare", "voices": list(self._voices)})
        except Exception:
            self.close()
            raise

    def generate(self, text: str, debater: Debater, output_path: Path) -> None:
        """Generate speech with the configured built-in Pocket TTS voice."""
        self.prepare()
        self._request(
            {
                "command": "generate",
                "text": text,
                "voice": debater.voice,
                "output_path": str(output_path),
            }
        )

    def close(self) -> None:
        """Stop the Pocket TTS worker after all queued speech has finished."""
        with self._lock:
            process = self._process
            if process is None:
                return
            self._process = None
            if process.poll() is None and process.stdin is not None:
                try:
                    process.stdin.write('{"command":"close"}\n')
                    process.stdin.flush()
                    process.stdin.close()
                    process.wait(timeout=10)
                except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            if process.stdout is not None:
                process.stdout.close()
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()

    def _request(self, payload: dict[str, object]) -> None:
        """Send one job to the persistent worker and wait for its result."""
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None:
                raise RuntimeError("The Pocket TTS worker is not running.")
            if process.stdin is None or process.stdout is None:
                raise RuntimeError("The Pocket TTS worker pipes are unavailable.")

            process.stdin.write(json.dumps(payload) + "\n")
            process.stdin.flush()
            result_line = process.stdout.readline()
            if not result_line:
                raise RuntimeError("The Pocket TTS worker stopped unexpectedly.")
            try:
                result = json.loads(result_line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "The Pocket TTS worker returned invalid data."
                ) from exc
            if not isinstance(result, dict) or not result.get("ok"):
                message = result.get("error") if isinstance(result, dict) else None
                raise RuntimeError(
                    message or "Pocket TTS could not finish the request."
                )


def _write_wav(output_path: Path, samples, sample_rate: int) -> None:
    """Atomically write audio so the browser sees only complete WAV files."""
    import soundfile

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f".{output_path.name}.tmp")
    try:
        soundfile.write(temporary_path, samples, sample_rate, format="WAV")
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
