# LLMDebate

LLMDebate runs multi-role AI debates with an OpenAI-compatible API, local text-to-speech, and portable HTML transcripts. Each configured role speaks once per round.

## Features

- Ordered debates with the full earlier conversation included in each request.
- Configurable API endpoint, model, effort, and API-key environment variable.
- Local text-to-speech using Kokoro, Pocket TTS, or Chatterbox-Nano.
- Live HTML transcript with role colors, audio controls, and word counts.
- Portable transcript and audio package after each debate.

## Requirements

- Python 3.11 or newer.
- [uv](https://docs.astral.sh/uv/).
- An API key for the selected OpenAI-compatible service.
- Internet access on first run to download selected speech model files.

## Install

```sh
uv sync --locked
cp .env.example .env
```

Put your API key in `.env` using the variable name configured by `[api].api_key_env` (default: `OPENAI_API_KEY`):

```dotenv
OPENAI_API_KEY=your-key-here
```

`.env` is ignored by Git. Never commit a real API key.

## Configure

Edit `config.toml`. Set `[api].base_url` to the API root, such as `https://api.openai.com/v1`; the app adds `/chat/completions`. Choose a model supported by that endpoint. If the provider does not accept `reasoning_effort`, set `effort = ""`.

Add one `[[roles]]` table for each participant. Each role has a display name, color, and voice. Voice options for each TTS engine are listed at the top of `config.toml`. Set `[tts].model` to `"kokoro"`, `"pocket-tts"`, or `"chatterbox-nano"`.

## Run

```sh
uv run debate.py
```

The app writes the live transcript to the configured HTML output path. Audio files go in a matching `<name>_audio/` folder. When the debate and queued speech finish, it creates `package/` and `package.zip` beside the transcript. Open the HTML inside `package/` to play the included audio.

To send a short API check, run:

```sh
uv run ping_api.py
```

This sends a real request to your configured API and may incur a charge.

## Tests

Run the offline unit tests; they use mocked API and speech clients and do not need an API key:

```sh
uv run python -m unittest discover -s tests -v
```

To check that the command-line entry point loads:

```sh
uv run debate.py --help
```

## GitHub

For a GitHub Actions job that runs the app, add the key as an Actions repository secret and expose it under the name configured by `[api].api_key_env`. Do not add a workflow that runs debates automatically unless you want its API requests and local TTS setup to run in CI.

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
