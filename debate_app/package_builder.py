"""Build a portable folder and ZIP archive from a finished debate."""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path


class PortablePackageBuilder:
    """Copy a transcript and its local audio into a portable package."""

    def __init__(self, transcript_path: Path) -> None:
        self.transcript_path = transcript_path
        self.package_directory = transcript_path.parent / "package"
        self.archive_path = transcript_path.parent / "package.zip"

    def create(self) -> tuple[Path, Path]:
        """Create or replace the package folder and ZIP archive."""
        if not self.transcript_path.is_file():
            raise FileNotFoundError(
                f"Debate transcript not found: {self.transcript_path}"
            )
        if self.transcript_path.parent.name == "package":
            raise ValueError(
                "The debate output file cannot be inside the package folder."
            )

        staging_directory = Path(
            tempfile.mkdtemp(prefix=".package-", dir=self.transcript_path.parent)
        )
        try:
            shutil.copy2(
                self.transcript_path,
                staging_directory / self.transcript_path.name,
            )
            audio_directory = self.transcript_path.with_name(
                f"{self.transcript_path.stem}_audio"
            )
            if audio_directory.is_dir():
                shutil.copytree(
                    audio_directory,
                    staging_directory / audio_directory.name,
                )
            else:
                (staging_directory / audio_directory.name).mkdir()

            (staging_directory / "README.txt").write_text(
                "Portable debate transcript\n\n"
                f"Open {self.transcript_path.name} in a web browser.\n"
                "The audio folder beside it contains the generated argument audio.\n",
                encoding="utf-8",
            )
            self._replace_directory(staging_directory)
            self._write_archive()
        finally:
            if staging_directory.exists():
                shutil.rmtree(staging_directory, ignore_errors=True)

        return self.package_directory, self.archive_path

    def _replace_directory(self, staging_directory: Path) -> None:
        """Replace the previous package only after the new copy is complete."""
        previous_directory = self.package_directory.with_name(".package-previous")
        shutil.rmtree(previous_directory, ignore_errors=True)
        if self.package_directory.exists():
            self.package_directory.replace(previous_directory)
        try:
            staging_directory.replace(self.package_directory)
        except OSError:
            if previous_directory.exists():
                previous_directory.replace(self.package_directory)
            raise
        shutil.rmtree(previous_directory, ignore_errors=True)

    def _write_archive(self) -> None:
        """Write the complete package folder into a ZIP with a top-level folder."""
        temporary_archive = self.archive_path.with_name(".package.zip.tmp")
        try:
            with zipfile.ZipFile(
                temporary_archive,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
            ) as archive:
                for path in sorted(self.package_directory.rglob("*")):
                    if path.is_file():
                        archive.write(
                            path,
                            Path(self.package_directory.name)
                            / path.relative_to(self.package_directory),
                        )
            temporary_archive.replace(self.archive_path)
        finally:
            temporary_archive.unlink(missing_ok=True)
