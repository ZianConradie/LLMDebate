"""Exercise the debate flow with fake API and speech clients."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from debate_app.models import Debater
from debate_app.runner import DebateRunner
from debate_app.settings import load_settings
from debate_app.transcript import HtmlTranscript


class FakeApiClient:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str, instructions: str) -> str:
        self.prompts.append(prompt)
        return f"Argument {len(self.prompts)}."


class FakeSpeechGenerator:
    def prepare(self) -> None:
        pass

    def generate(self, text: str, debater: Debater, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(text.encode("utf-8"))

    def close(self) -> None:
        pass


class DebateRunnerTests(unittest.TestCase):
    def test_runs_all_roles_and_builds_portable_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            config_path = root / "config.toml"
            config_path.write_text(
                """[debate]
argument_limit = 1
output_file = "debate.html"

[api]
base_url = "https://api.example.invalid/v1"
api_key_env = "UNUSED_TEST_KEY"
model = "fake-model"
effort = ""

[tts]
model = "kokoro"

[[roles]]
role = "First"
color = "#123456"
voice = "af_heart"

[[roles]]
role = "Second"
color = "#654321"
voice = "am_adam"

[[roles]]
role = "Third"
color = "#abcdef"
voice = "bf_emma"
""",
                encoding="utf-8",
            )
            settings = load_settings(config_path)
            client = FakeApiClient()
            transcript = HtmlTranscript(settings)
            runner = DebateRunner(
                settings,
                client=client,
                transcript=transcript,
                speech_generator=FakeSpeechGenerator(),
            )

            runner.run()

            self.assertEqual(len(client.prompts), 3)
            self.assertIn("First (Heart)", client.prompts[1])
            self.assertIn("Third (Emma)", client.prompts[1])
            self.assertIn("Argument 1.", client.prompts[1])
            html = settings.output_path.read_text(encoding="utf-8")
            self.assertIn("Heart (First)", html)
            self.assertIn("Adam (Second)", html)
            self.assertIn("Emma (Third)", html)
            self.assertTrue((root / "package" / "debate.html").is_file())
            self.assertTrue((root / "package.zip").is_file())


if __name__ == "__main__":
    unittest.main()
