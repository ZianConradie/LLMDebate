"""Small data objects shared by the debate app."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Debater:
    """One role, with its display color and the voice data used by TTS."""

    role: str
    color: str
    voice: str
    voice_reference: Path | None = None

    @property
    def voice_name(self) -> str:
        """Return the name associated with this role's voice."""
        if self.voice_reference is not None:
            return self.voice_reference.stem.replace("_", " ").title()
        voice_name = self.voice
        if voice_name.startswith(("af_", "am_", "bf_", "bm_")):
            voice_name = voice_name.split("_", maxsplit=1)[1]
        return voice_name.replace("_", " ").title()


@dataclass(frozen=True)
class DebateSettings:
    """All settings needed to run and save one debate."""

    topic: str
    argument_limit: int
    argument_time: int
    timeout_seconds: int
    output_path: Path
    api_base_url: str
    api_key_env: str
    api_model: str
    api_effort: str | None
    tts_model: str
    roles: tuple[Debater, ...]

    @property
    def word_limit(self) -> int:
        """Approximate maximum words, using 3 words for each second."""
        return self.argument_time * 3


@dataclass(frozen=True)
class DebateTurn:
    """One completed argument from one debater."""

    round_number: int
    debater: Debater
    text: str

    @property
    def word_count(self) -> int:
        """Count words separated by whitespace."""
        return len(self.text.split())
