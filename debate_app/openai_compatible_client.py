"""Call an OpenAI-compatible chat-completions endpoint with an API key."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-6-luna"
DEFAULT_TIMEOUT_SECONDS = 300


class OpenAICompatibleClient:
    """Send chat-completions requests to OpenAI or a compatible provider."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        api_key_env: str = "OPENAI_API_KEY",
        model: str = DEFAULT_MODEL,
        effort: str | None = "high",
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.model = model
        self.effort = effort
        self.timeout_seconds = timeout_seconds

    def generate(self, prompt: str, instructions: str) -> str:
        """Ask the configured model for one text response."""
        api_key = os.environ.get(self.api_key_env)
        if not api_key or not api_key.strip():
            raise RuntimeError(
                f"API key environment variable {self.api_key_env!r} is not set. "
                "Add it to .env or your environment."
            )

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
        }
        if self.effort:
            payload["reasoning_effort"] = self.effort

        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return self._read_response(response)
        except HTTPError as exc:
            message = self._api_error_message(exc.read())
            raise RuntimeError(f"API HTTP {exc.code}: {message}") from exc
        except URLError as exc:
            raise RuntimeError(
                f"Could not reach the API endpoint: {exc.reason}"
            ) from exc

    @classmethod
    def _read_response(cls, response: Any) -> str:
        body = response.read()
        if not body.strip():
            raise RuntimeError(
                f"API returned an empty HTTP {response.status} response."
            )
        try:
            result = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError("API returned a non-JSON response.") from exc

        if not isinstance(result, dict):
            raise TypeError("API returned an unexpected response.")
        if result.get("error"):
            error = result["error"]
            message = error.get("message") if isinstance(error, dict) else None
            raise RuntimeError(message or "API returned an error.")

        choices = result.get("choices")
        if (
            not isinstance(choices, list)
            or not choices
            or not isinstance(choices[0], dict)
        ):
            raise RuntimeError("API response did not contain any choices.")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise TypeError("API response did not contain a message object.")

        content = cls._message_content(message.get("content"))
        if not content.strip():
            raise RuntimeError("API returned no answer text.")
        return content.strip()

    @staticmethod
    def _message_content(content: Any) -> str:
        """Read text returned as a string or a list of text blocks."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    parts.append(block["text"])
            return "".join(parts)
        return ""

    @staticmethod
    def _api_error_message(body: bytes) -> str:
        try:
            parsed = json.loads(body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return "no error details returned"
        error = parsed.get("error", parsed) if isinstance(parsed, dict) else {}
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"]
        return "no error details returned"
