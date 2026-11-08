"""Take turns asking both debaters to argue."""

from __future__ import annotations

import sys
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from debate_app.models import Debater, DebateSettings, DebateTurn
from debate_app.openai_compatible_client import OpenAICompatibleClient
from debate_app.package_builder import PortablePackageBuilder
from debate_app.prompts import (
    build_instructions,
    build_tts_edit_input,
    build_tts_edit_instructions,
    build_turn_input,
    is_safe_tts_edit,
)
from debate_app.transcript import HtmlTranscript
from debate_app.tts import SpeechGenerator, make_speech_generator


class DebateRunner:
    """Run the debate one argument at a time."""

    def __init__(
        self,
        settings: DebateSettings,
        client: OpenAICompatibleClient | None = None,
        transcript: HtmlTranscript | None = None,
        speech_generator: SpeechGenerator | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or OpenAICompatibleClient(
            timeout_seconds=settings.timeout_seconds,
            base_url=settings.api_base_url,
            api_key_env=settings.api_key_env,
            model=settings.api_model,
            effort=settings.api_effort,
        )
        self.transcript = transcript or HtmlTranscript(settings)
        model_directory = Path(__file__).resolve().parent.parent / "models"
        self.speech_generator = speech_generator or make_speech_generator(
            settings.tts_model,
            model_directory,
            pocket_voices=tuple(role.voice for role in settings.roles),
        )
        self.history: list[DebateTurn] = []
        self._speech_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="kokoro-speech"
        )

    def run(self) -> None:
        """Prepare speech before starting a fresh debate, then alternate roles."""
        try:
            print(
                f"Preparing {self.settings.tts_model} before the debate starts...",
                flush=True,
            )
            self.speech_generator.prepare()
            print(f"{self.settings.tts_model} is ready.", flush=True)

            self.transcript.start()
            for round_number in range(1, self.settings.argument_limit + 1):
                for role_index, debater in enumerate(self.settings.roles):
                    opponents = tuple(
                        role
                        for index, role in enumerate(self.settings.roles)
                        if index != role_index
                    )
                    self._run_turn(round_number, debater, opponents)
        finally:
            try:
                self._speech_executor.shutdown(wait=True)
            finally:
                try:
                    self.speech_generator.close()
                finally:
                    if self.transcript.started:
                        self.transcript.finish()
                        package_directory, archive_path = PortablePackageBuilder(
                            self.settings.output_path
                        ).create()
                        print(
                            f"Portable package saved to {package_directory}", flush=True
                        )
                        print(f"ZIP archive saved to {archive_path}", flush=True)

    def _run_turn(
        self,
        round_number: int,
        debater: Debater,
        opponents: tuple[Debater, ...],
    ) -> None:
        print(
            f"Round {round_number}/{self.settings.argument_limit}: "
            f"generating {debater.role}...",
            flush=True,
        )
        answer = self.client.generate(
            prompt=build_turn_input(
                settings=self.settings,
                debater=debater,
                opponents=opponents,
                round_number=round_number,
                history=self.history,
            ),
            instructions=build_instructions(self.settings, debater, opponents),
        )
        turn = DebateTurn(round_number=round_number, debater=debater, text=answer)
        turn_id = self.transcript.add_turn(turn)
        future = self._speech_executor.submit(
            self._make_speech,
            turn,
            opponents,
            self.transcript.audio_path(turn_id),
        )
        future.add_done_callback(
            lambda completed, current_id=turn_id, current_role=debater.role: (
                self._finish_speech(completed, current_id, current_role)
            )
        )
        self.history.append(turn)
        print(
            f"Saved {debater.role}'s argument to {self.settings.output_path}",
            flush=True,
        )

    def _make_speech(
        self,
        turn: DebateTurn,
        opponents: tuple[Debater, ...],
        output_path: Path,
    ) -> None:
        """Optionally add Chatterbox tags, then synthesize without blocking debate."""
        speech_text = turn.text
        if self.settings.tts_model == "chatterbox-nano":
            print(f"Preparing {turn.debater.role}'s speech script...", flush=True)
            try:
                edited_text = self.client.generate(
                    prompt=build_tts_edit_input(
                        self.settings,
                        turn.debater,
                        opponents,
                        turn.text,
                    ),
                    instructions=build_tts_edit_instructions(self.settings),
                ).strip()
                if edited_text and is_safe_tts_edit(turn.text, edited_text):
                    speech_text = edited_text
                elif edited_text:
                    print(
                        f"Speech tagging changed {turn.debater.role}'s words; using the original argument.",
                        file=sys.stderr,
                        flush=True,
                    )
            except Exception as exc:  # noqa: BLE001 - fall back to the original argument on any edit failure.
                print(
                    f"Speech tagging failed for {turn.debater.role}; using original text: {exc}",
                    file=sys.stderr,
                    flush=True,
                )

        self.speech_generator.generate(speech_text, turn.debater, output_path)

    def _finish_speech(self, future: Future[None], turn_id: str, role: str) -> None:
        """Replace the loading button when one background audio job finishes."""
        try:
            future.result()
            self.transcript.mark_audio_ready(turn_id)
        except Exception as exc:  # noqa: BLE001 - report any speech backend failure in the transcript.
            self.transcript.mark_audio_failed(turn_id)
            print(
                f"Speech generation failed for {role}: {exc}",
                file=sys.stderr,
                flush=True,
            )
