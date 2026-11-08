"""Tests for portable API and role configuration."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from debate_app.settings import load_settings


def _write_config(directory: Path, *, base_url: str, effort: str = "high") -> Path:
    config_path = directory / "config.toml"
    config_path.write_text(
        f'''[debate]
output_file = "debate.html"

[api]
base_url = "{base_url}"
api_key_env = "TEST_API_KEY"
model = "test-model"
effort = "{effort}"

[tts]
model = "pocket-tts"

[[roles]]
role = "First"
color = "#123456"
voice = "anna"

[[roles]]
role = "Second"
color = "#654321"
voice = "paul"

[[roles]]
role = "Third"
color = "#abcdef"
voice = "vera"
''',
        encoding="utf-8",
    )
    return config_path


class LoadSettingsTests(unittest.TestCase):
    def test_reads_endpoint_and_multiple_roles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = _write_config(
                Path(temporary_directory),
                base_url="https://api.example.invalid/v1",
                effort="",
            )

            settings = load_settings(config_path)

        self.assertEqual(settings.api_base_url, "https://api.example.invalid/v1")
        self.assertEqual(settings.api_key_env, "TEST_API_KEY")
        self.assertEqual(settings.api_model, "test-model")
        self.assertIsNone(settings.api_effort)
        self.assertEqual(
            [role.role for role in settings.roles], ["First", "Second", "Third"]
        )

    def test_rejects_invalid_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = _write_config(Path(temporary_directory), base_url="not a url")

            with self.assertRaisesRegex(ValueError, "HTTP or HTTPS"):
                load_settings(config_path)

    def test_rejects_credentials_in_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = _write_config(
                Path(temporary_directory),
                base_url="https://user:pass@example.invalid/v1",
            )

            with self.assertRaisesRegex(ValueError, "must not contain credentials"):
                load_settings(config_path)

    def test_loads_dotenv_without_overriding_shell_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            config_path = _write_config(
                directory, base_url="https://api.example.invalid/v1"
            )
            (directory / ".env").write_text(
                "TEST_API_KEY=from-dotenv\n", encoding="utf-8"
            )

            with patch.dict(os.environ, {}, clear=True):
                load_settings(config_path)
                self.assertEqual(os.environ["TEST_API_KEY"], "from-dotenv")

            with patch.dict(os.environ, {"TEST_API_KEY": "from-shell"}, clear=True):
                load_settings(config_path)
                self.assertEqual(os.environ["TEST_API_KEY"], "from-shell")


if __name__ == "__main__":
    unittest.main()
