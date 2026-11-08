#!/usr/bin/env python3
"""Send one short ping request to the configured chat model."""

from pathlib import Path

from debate_app.openai_compatible_client import OpenAICompatibleClient
from debate_app.settings import load_settings


def ping() -> str:
    """Send a small request using the project's configured API settings."""
    settings = load_settings(Path(__file__).resolve().with_name("config.toml"))
    client = OpenAICompatibleClient(
        base_url=settings.api_base_url,
        api_key_env=settings.api_key_env,
        model=settings.api_model,
        effort=settings.api_effort,
        timeout_seconds=settings.timeout_seconds,
    )
    return client.generate(
        prompt="ping",
        instructions="Reply with a brief ping acknowledgement.",
    )


def main() -> None:
    print(ping())


if __name__ == "__main__":
    main()
