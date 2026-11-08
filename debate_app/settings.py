"""Read config.toml and check that its settings make sense."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

from debate_app.models import Debater, DebateSettings

_CSS_COLOR = re.compile(r"(?:#[0-9a-fA-F]{3,8}|[A-Za-z]+)\Z")
_TTS_MODELS = {"kokoro", "chatterbox-nano", "pocket-tts"}
_API_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
_DEFAULT_COLORS = ("#c62828", "#1565c0", "#2e7d32", "#ef6c00", "#6a1b9a")
_DEFAULT_KOKORO_VOICES = ("af_heart", "am_adam", "bf_emma", "bm_george")
_DEFAULT_POCKET_VOICES = ("anna", "paul", "alba", "marius")


@dataclass(frozen=True)
class SettingsOverrides:
    """Optional command-line values that replace config.toml values."""

    topic: str | None = None
    role1: str | None = None
    role2: str | None = None
    argument_limit: int | None = None
    argument_time: int | None = None
    output_path: str | Path | None = None


def load_settings(
    config_path: Path, overrides: SettingsOverrides | None = None
) -> DebateSettings:
    """Load a TOML file, apply command-line overrides, and return checked settings."""
    overrides = overrides or SettingsOverrides()
    config_path = config_path.expanduser().resolve()
    load_dotenv(config_path.parent / ".env", override=False)

    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Config file not found: {config_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Could not parse {config_path}: {exc}") from exc

    debate = _table(config, "debate")
    api = _table(config, "api")
    tts = _table(config, "tts")
    api_base_url = _text(api, "base_url", "https://api.openai.com/v1").rstrip("/")
    parsed_base_url = urlparse(api_base_url)
    if parsed_base_url.scheme not in {"http", "https"} or not parsed_base_url.netloc:
        raise ValueError("[api].base_url must be an HTTP or HTTPS base URL.")
    if (
        parsed_base_url.username
        or parsed_base_url.password
        or parsed_base_url.query
        or parsed_base_url.fragment
    ):
        raise ValueError(
            "[api].base_url must not contain credentials, a query, or a fragment."
        )
    api_key_env = _text(api, "api_key_env", "OPENAI_API_KEY")
    api_model = _text(api, "model", "gpt-6-luna")
    effort_value = api.get("effort", "high")
    if (
        effort_value is None
        or isinstance(effort_value, str)
        and not effort_value.strip()
    ):
        api_effort = None
    elif isinstance(effort_value, str):
        api_effort = effort_value.strip().lower()
        if api_effort not in _API_EFFORTS:
            choices = ", ".join(sorted(_API_EFFORTS))
            raise ValueError(f"[api].effort must be one of: {choices}, or empty.")
    else:
        raise ValueError("[api].effort must be a string or empty.")
    tts_model = _text(tts, "model", "kokoro").lower()
    if tts_model not in _TTS_MODELS:
        choices = ", ".join(sorted(_TTS_MODELS))
        raise ValueError(f"tts.model must be one of: {choices}.")

    role_tables = _role_tables(config)
    if len(role_tables) < 2:
        raise ValueError("Configure at least two entries in [[roles]].")

    topic = _override_text(overrides.topic, debate, "topic", "Is the Earth flat?")
    argument_limit = _override_number(
        overrides.argument_limit, debate, "argument_limit", default=10
    )
    argument_time = _override_number(
        overrides.argument_time, debate, "argument_time", default=60
    )
    timeout_seconds = _positive_integer(
        debate.get("timeout_seconds", 300), "timeout_seconds"
    )

    output_value = overrides.output_path
    if output_value is None:
        output_value = _text(debate, "output_file", "debate.html")
    output_path = Path(output_value).expanduser()
    if output_path.suffix.lower() != ".html":
        raise ValueError("output_file must use the .html extension.")
    if not output_path.is_absolute():
        output_path = config_path.parent / output_path

    default_voices = (
        _DEFAULT_POCKET_VOICES if tts_model == "pocket-tts" else _DEFAULT_KOKORO_VOICES
    )
    roles = tuple(
        _debater(
            role_table,
            default_role=f"Role {index + 1}",
            default_color=_DEFAULT_COLORS[index % len(_DEFAULT_COLORS)],
            default_voice=default_voices[index % len(default_voices)],
            role_override=(
                overrides.role1
                if index == 0
                else overrides.role2
                if index == 1
                else None
            ),
            config_directory=config_path.parent,
        )
        for index, role_table in enumerate(role_tables)
    )

    return DebateSettings(
        topic=topic,
        argument_limit=argument_limit,
        argument_time=argument_time,
        timeout_seconds=timeout_seconds,
        output_path=output_path,
        api_base_url=api_base_url,
        api_key_env=api_key_env,
        api_model=api_model,
        api_effort=api_effort,
        tts_model=tts_model,
        roles=roles,
    )


def _table(config: dict[str, Any], name: str) -> dict[str, Any]:
    value = config.get(name, {})
    if not isinstance(value, dict):
        raise TypeError(f"[{name}] must be a TOML table.")
    return value


def _role_tables(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Read ordered role tables, while accepting the earlier two-table format."""
    if "roles" not in config:
        return [_table(config, "role1"), _table(config, "role2")]

    roles = config["roles"]
    if not isinstance(roles, list):
        raise TypeError("Define debate roles with one or more [[roles]] tables.")
    if any(not isinstance(role, dict) for role in roles):
        raise TypeError("Each [[roles]] entry must be a TOML table.")
    return roles


def _text(table: dict[str, Any], key: str, default: str) -> str:
    value = table.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string.")
    return value.strip()


def _override_text(
    override: str | None,
    table: dict[str, Any],
    key: str,
    default: str,
) -> str:
    value = override.strip() if override is not None else _text(table, key, default)
    if not value:
        raise ValueError(f"{key} must be a non-empty string.")
    return value


def _positive_integer(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive whole number.")
    return value


def _override_number(
    override: int | None,
    table: dict[str, Any],
    key: str,
    *,
    default: int,
) -> int:
    value = override if override is not None else table.get(key, default)
    return _positive_integer(value, key)


def _debater(
    table: dict[str, Any],
    *,
    default_role: str,
    default_color: str,
    default_voice: str,
    role_override: str | None,
    config_directory: Path,
) -> Debater:
    role = (
        role_override.strip()
        if role_override is not None
        else _text(table, "role", default_role)
    )
    color = _text(table, "color", default_color)
    voice = _text(table, "voice", default_voice)
    reference_value = table.get("voice_reference")
    if reference_value is None:
        voice_reference = None
    elif not isinstance(reference_value, str) or not reference_value.strip():
        raise ValueError(f"voice_reference for role {role} must be a non-empty path.")
    else:
        voice_reference = Path(reference_value).expanduser()
        if not voice_reference.is_absolute():
            voice_reference = config_directory / voice_reference
        voice_reference = voice_reference.resolve()
    if not role:
        raise ValueError("Role must not be empty.")
    if not _CSS_COLOR.fullmatch(color):
        raise ValueError(f"Invalid CSS color for role {role}: {color!r}.")
    if voice_reference is not None and not voice_reference.is_file():
        raise ValueError(
            f"Voice reference file not found for role {role}: {voice_reference}"
        )
    return Debater(
        role=role,
        color=color,
        voice=voice,
        voice_reference=voice_reference,
    )
