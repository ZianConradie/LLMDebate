"""Tests for the OpenAI-compatible HTTP client without network access."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from debate_app.openai_compatible_client import OpenAICompatibleClient


class OpenAICompatibleClientTests(unittest.TestCase):
    def test_posts_chat_completion_with_configured_key_and_effort(self) -> None:
        response_body = json.dumps(
            {"choices": [{"message": {"content": "  Hello from the mock.  "}}]}
        ).encode()
        with (
            patch.dict(os.environ, {"TEST_API_KEY": "fake-key"}),
            patch("debate_app.openai_compatible_client.urlopen") as urlopen,
        ):
            urlopen.return_value.__enter__.return_value.read.return_value = (
                response_body
            )
            urlopen.return_value.__enter__.return_value.status = 200
            client = OpenAICompatibleClient(
                base_url="https://example.invalid/v1/",
                api_key_env="TEST_API_KEY",
                model="example-model",
                effort="medium",
            )

            answer = client.generate("question", "instructions")

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(answer, "Hello from the mock.")
        self.assertEqual(
            request.full_url, "https://example.invalid/v1/chat/completions"
        )
        self.assertEqual(request.get_header("Authorization"), "Bearer fake-key")
        self.assertEqual(payload["model"], "example-model")
        self.assertEqual(payload["reasoning_effort"], "medium")
        self.assertEqual(payload["messages"][0]["content"], "instructions")
        self.assertEqual(payload["messages"][1]["content"], "question")

    def test_omits_effort_when_provider_does_not_support_it(self) -> None:
        response_body = b'{"choices":[{"message":{"content":"ok"}}]}'
        with (
            patch.dict(os.environ, {"TEST_API_KEY": "fake-key"}),
            patch("debate_app.openai_compatible_client.urlopen") as urlopen,
        ):
            urlopen.return_value.__enter__.return_value.read.return_value = (
                response_body
            )
            client = OpenAICompatibleClient(
                api_key_env="TEST_API_KEY",
                effort=None,
            )
            client.generate("question", "instructions")

        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertNotIn("reasoning_effort", payload)

    def test_missing_key_has_clear_error(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            client = OpenAICompatibleClient(api_key_env="MISSING_API_KEY")
            with self.assertRaisesRegex(RuntimeError, "MISSING_API_KEY"):
                client.generate("question", "instructions")


if __name__ == "__main__":
    unittest.main()
