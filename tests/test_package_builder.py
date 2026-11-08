"""Tests for the portable debate package."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from debate_app.package_builder import PortablePackageBuilder


class PortablePackageBuilderTests(unittest.TestCase):
    def test_copies_transcript_and_audio_into_folder_and_zip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            transcript = root / "debate.html"
            transcript.write_text("<html>debate</html>", encoding="utf-8")
            audio_directory = root / "debate_audio"
            audio_directory.mkdir()
            (audio_directory / "turn-0001.wav").write_bytes(b"audio")

            package_directory, archive_path = PortablePackageBuilder(
                transcript
            ).create()

            self.assertEqual(
                (package_directory / "debate.html").read_text(encoding="utf-8"),
                "<html>debate</html>",
            )
            self.assertTrue(
                (package_directory / "debate_audio" / "turn-0001.wav").is_file()
            )
            with zipfile.ZipFile(archive_path) as archive:
                self.assertIn("package/debate.html", archive.namelist())
                self.assertIn("package/debate_audio/turn-0001.wav", archive.namelist())


if __name__ == "__main__":
    unittest.main()
