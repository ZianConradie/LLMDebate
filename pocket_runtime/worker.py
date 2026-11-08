"""Keep Pocket TTS loaded while the debate app sends speech jobs."""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


def _load_model():
    with contextlib.redirect_stdout(sys.stderr):
        from pocket_tts import TTSModel

        print("Loading Pocket TTS on CPU...", file=sys.stderr, flush=True)
        return TTSModel.load_model()


def _write_audio(model, voice_state, request: dict[str, Any]) -> None:
    import soundfile

    output_path = Path(request["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with contextlib.redirect_stdout(sys.stderr):
            samples = model.generate_audio(voice_state, request["text"])
        samples = samples.detach().squeeze().cpu().numpy()
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        soundfile.write(
            temporary_path,
            samples,
            model.sample_rate,
            format="WAV",
        )
        os.replace(temporary_path, output_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main() -> None:
    protocol_output = sys.stdout
    model = None
    voices = {}
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise TypeError("Request must be a JSON object.")
            command = request.get("command")
            if command == "prepare":
                model = _load_model()
                with contextlib.redirect_stdout(sys.stderr):
                    for voice in request.get("voices", []):
                        voices[voice] = model.get_state_for_audio_prompt(voice)
            elif command == "generate":
                if model is None:
                    model = _load_model()
                voice = request["voice"]
                if voice not in voices:
                    with contextlib.redirect_stdout(sys.stderr):
                        voices[voice] = model.get_state_for_audio_prompt(voice)
                _write_audio(model, voices[voice], request)
            elif command == "close":
                protocol_output.write('{"ok":true}\n')
                protocol_output.flush()
                return
            else:
                raise ValueError(f"Unknown worker command: {command}")
            result = {"ok": True}
        except Exception as exc:  # noqa: BLE001 - return every job failure over the worker protocol.
            result = {"ok": False, "error": str(exc)}
        protocol_output.write(json.dumps(result) + "\n")
        protocol_output.flush()


if __name__ == "__main__":
    main()
