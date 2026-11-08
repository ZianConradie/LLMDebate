"""Write the live HTML transcript."""

from __future__ import annotations

import html
import os
import shutil
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from debate_app.models import Debater, DebateSettings, DebateTurn

_PAGE_START = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Debate transcript</title>
<style>
:root { color-scheme: light; font-family: system-ui, sans-serif; color: #202124; background: #f5f6f8; }
body { max-width: 900px; margin: 0 auto; padding: 2rem 1.25rem 4rem; line-height: 1.6; }
h1 { font-size: 2rem; margin-bottom: 2rem; }
.debate { background: #fff; border: 1px solid #d9dde3; border-radius: 12px; margin: 1.5rem 0; padding: 1.5rem; }
.debate h2 { margin-top: 0; }
.meta { color: #62666d; font-size: .92rem; }
.turns { display: grid; gap: 1rem; margin-top: 1.5rem; }
.turn { background: #fff; border: 1px solid #e1e4e8; border-left: 5px solid var(--side-color); border-radius: 8px; padding: 1rem 1.25rem; }
.turn h3 { color: var(--side-color); margin: 0 0 .6rem; }
.argument { white-space: pre-wrap; }
.word-count { color: #717780; font-size: .85rem; margin-top: .75rem; text-align: right; }
.audio-controls { margin-top: .9rem; }
.play-button { background: var(--side-color); border: 0; border-radius: 6px; color: #fff; cursor: pointer; font: inherit; padding: .45rem .85rem; }
.play-button:disabled { background: #858b94; cursor: wait; }
</style>
</head>
<body data-server-no-reload data-debate-state="active">
<main>
<h1>Debate transcript</h1>
<script>
document.addEventListener("DOMContentLoaded", () => {
  const turnsContainer = document.querySelector(".turns");
  let syncInProgress = false;

  function bindTurn(turn) {
    const button = turn.querySelector(".play-button");
    const audio = turn.querySelector("audio");
    if (!button || !audio || button.disabled || button.dataset.bound) return;
    button.dataset.bound = "true";
    button.addEventListener("click", async () => {
      if (audio.paused) {
        document.querySelectorAll(".turn audio").forEach((other) => {
          if (other !== audio) other.pause();
        });
        try { await audio.play(); } catch (_) { button.textContent = "Play"; }
      } else {
        audio.pause();
      }
    });
    audio.addEventListener("play", () => { button.textContent = "Pause"; });
    audio.addEventListener("pause", () => {
      if (!audio.ended) button.textContent = "Play";
    });
    audio.addEventListener("ended", () => { button.textContent = "Play"; });
  }

  document.querySelectorAll(".turn").forEach(bindTurn);

  async function syncTranscript() {
    if (syncInProgress || document.body.dataset.debateState === "finished") return;
    syncInProgress = true;
    try {
      const url = new URL(window.location.href);
      url.searchParams.set("_transcript", Date.now());
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) return;

      const pageText = await response.text();
      const updatedPage = new DOMParser().parseFromString(pageText, "text/html");
      const updatedTurns = updatedPage.querySelector(".turns");
      if (!turnsContainer || !updatedTurns) return;

      updatedTurns.querySelectorAll(":scope > .turn").forEach((updatedTurn) => {
        const existingTurn = document.getElementById(updatedTurn.id);
        if (!existingTurn) {
          const newTurn = document.importNode(updatedTurn, true);
          turnsContainer.append(newTurn);
          bindTurn(newTurn);
          return;
        }

        const currentButton = existingTurn.querySelector(".play-button");
        const updatedButton = updatedTurn.querySelector(".play-button");
        if (currentButton?.dataset.state === "loading" &&
            updatedButton && updatedButton.dataset.state !== "loading") {
          const newControls = document.importNode(
            updatedTurn.querySelector(".audio-controls"), true
          );
          existingTurn.querySelector(".audio-controls").replaceWith(newControls);
          bindTurn(existingTurn);
        }
      });

      document.body.dataset.debateState = updatedPage.body.dataset.debateState;
      if (document.body.dataset.debateState === "finished") {
        window.clearInterval(syncTimer);
      }
    } catch (_) {
      // Keep retrying if Five Server is restarting or briefly cannot serve the file.
    } finally {
      syncInProgress = false;
    }
  }

  const syncTimer = window.setInterval(syncTranscript, 1500);
});
</script>
"""


@dataclass
class _TranscriptEntry:
    """One displayed argument and the current state of its audio."""

    turn_id: str
    turn: DebateTurn
    audio_state: str = "loading"
    audio_source: str | None = None


class HtmlTranscript:
    """Keep the HTML file current after every completed argument."""

    def __init__(self, settings: DebateSettings) -> None:
        self.settings = settings
        self.turns: list[_TranscriptEntry] = []
        self.started = False
        self.finished = False
        self._lock = threading.Lock()

    @property
    def audio_directory(self) -> Path:
        """Return the folder next to the HTML file that holds generated speech."""
        return self.settings.output_path.with_name(
            f"{self.settings.output_path.stem}_audio"
        )

    def start(self) -> None:
        """Start a new debate and replace the previous output file."""
        self.settings.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self.settings.output_path.unlink(missing_ok=True)
            shutil.rmtree(self.audio_directory, ignore_errors=True)
            self.turns.clear()
            self.started = True
            self.finished = False
            self._save()

    def finish(self) -> None:
        """Mark the debate as done so an open browser stops refreshing."""
        with self._lock:
            if not self.started:
                return
            self.finished = True
            self._save()

    def add_turn(self, turn: DebateTurn) -> str:
        """Add an argument with a loading button and save it right away."""
        with self._lock:
            if not self.started:
                raise RuntimeError("Start the transcript before adding an argument.")
            turn_id = f"turn-{len(self.turns) + 1:04d}"
            self.turns.append(_TranscriptEntry(turn_id=turn_id, turn=turn))
            self._save()
            return turn_id

    def audio_path(self, turn_id: str) -> Path:
        """Return where one argument's WAV file should be written."""
        return self.audio_directory / f"{turn_id}.wav"

    def mark_audio_ready(self, turn_id: str) -> None:
        """Enable playback after the WAV file is fully written."""
        with self._lock:
            entry = self._find_entry(turn_id)
            entry.audio_state = "ready"
            relative_path = os.path.relpath(
                self.audio_path(turn_id), self.settings.output_path.parent
            )
            entry.audio_source = quote(Path(relative_path).as_posix(), safe="/._-")
            self._save()

    def mark_audio_failed(self, turn_id: str) -> None:
        """Show that speech could not be generated for this argument."""
        with self._lock:
            self._find_entry(turn_id).audio_state = "failed"
            self._save()

    def _find_entry(self, turn_id: str) -> _TranscriptEntry:
        for entry in self.turns:
            if entry.turn_id == turn_id:
                return entry
        raise KeyError(f"Transcript turn not found: {turn_id}")

    def _render_turn(self, entry: _TranscriptEntry) -> str:
        turn = entry.turn
        speaker = html.escape(_speaker_label(turn.debater))
        text = html.escape(turn.text.strip()).replace("\n", "<br>\n")
        if entry.audio_state == "ready":
            button = '<button class="play-button" type="button">Play</button>'
            audio = f'<audio preload="none" src="{html.escape(entry.audio_source or "", quote=True)}"></audio>'
        elif entry.audio_state == "loading":
            button = '<button class="play-button" type="button" data-state="loading" disabled>Loading</button>'
            audio = '<audio preload="none"></audio>'
        else:
            button = '<button class="play-button" type="button" disabled>Unavailable</button>'
            audio = '<audio preload="none"></audio>'
        return (
            f'<article class="turn" id="{entry.turn_id}" style="--side-color: {turn.debater.color};">\n'
            f"<h3>{speaker} <small>(Round {turn.round_number}, argument "
            f"{turn.round_number} of {self.settings.argument_limit})</small></h3>\n"
            f'<div class="argument">{text}</div>\n'
            f'<div class="audio-controls" aria-live="polite">{button}{audio}</div>\n'
            f'<div class="word-count">Word count: {turn.word_count}</div>\n'
            "</article>\n"
        )

    def _render_page(self) -> str:
        settings = self.settings
        role_labels = "".join(
            f'<div style="color: {role.color};"><strong>'
            f"{html.escape(_speaker_label(role))}</strong></div>\n"
            for role in settings.roles
        )
        metadata = (
            '<section class="debate">\n'
            f"<h2>{html.escape(settings.topic)}</h2>\n"
            '<div class="meta">\n'
            f"<div><strong>Arguments per role:</strong> {settings.argument_limit}</div>\n"
            f"<div><strong>Time per argument:</strong> {settings.argument_time} seconds "
            f"(under {settings.word_limit} words)</div>\n" + role_labels + "</div>\n"
            '<div class="turns" id="transcript-turns">\n'
        )
        page_end = "</div>\n</section>\n</main>\n</body>\n</html>\n"
        rendered_turns = "".join(self._render_turn(entry) for entry in self.turns)
        page_start = _PAGE_START.replace(
            'data-debate-state="active"',
            f'data-debate-state="{"finished" if self.finished else "active"}"',
        )
        return page_start + metadata + rendered_turns + page_end

    def _save(self) -> None:
        _write_atomically(self.settings.output_path, self._render_page())


def _write_atomically(path: Path, text: str) -> None:
    """Replace the file in one step so it is never half-written."""
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(text)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _speaker_label(debater: Debater) -> str:
    """Return a readable voice name followed by its debate role."""
    return f"{debater.voice_name} ({debater.role})"
