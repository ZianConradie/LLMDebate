"""Keep Chatterbox-Nano in a separate environment from Kokoro's NumPy stack."""

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
        from chatterbox.tts_turbo import ChatterboxTurboTTS

        print("Loading Chatterbox-Nano on CPU...", file=sys.stderr, flush=True)
        return ChatterboxTurboTTS.from_pretrained(device="cpu", nano=True)


def _generate(model, request: dict[str, Any]) -> None:
    import soundfile

    output_path = Path(request["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with contextlib.redirect_stdout(sys.stderr):
            generation_options = {}
            if request.get("voice_reference"):
                generation_options["audio_prompt_path"] = request["voice_reference"]
            waveform = model.generate(request["text"], **generation_options)
        samples = waveform.detach().squeeze().cpu().numpy()
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        soundfile.write(temporary_path, samples, model.sr, format="WAV")
        os.replace(temporary_path, output_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main() -> None:
    protocol_output = sys.stdout
    model = None
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise TypeError("Request must be a JSON object.")
            command = request.get("command")
            if command == "prepare":
                model = _load_model()
            elif command == "generate":
                if model is None:
                    model = _load_model()
                _generate(model, request)
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
