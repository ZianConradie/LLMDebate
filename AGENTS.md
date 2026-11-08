# Project Guide

This project runs a local debate with two or more roles. Each configured role speaks once per round. The app saves each argument to a live HTML transcript and generates speech with the selected local TTS engine. Speakers appear as `Voice name (Role)` in their configured colors.

## Run and check

- Install the locked root dependencies: `uv sync --locked`.
- Start a debate: `uv run debate.py`.
- Send a real API ping: `uv run ping_api.py` (requires a key and may incur a charge).
- Run the offline unit suite: `uv run python -m unittest discover -s tests -v`.
- Use repeated `[[roles]]` tables in `config.toml` to add participants.

The project requires Python 3.11 or newer and `uv`. The root environment contains the API client and Kokoro dependencies. Pocket TTS and Chatterbox-Nano run in separate `uv` projects under their respective runtime directories to isolate their PyTorch and NumPy dependencies.

## Code map

- `debate.py` and `ping_api.py` are the command-line entry points.
- `debate_app/cli.py` parses debate options and starts the runner.
- `debate_app/settings.py` loads and validates `config.toml`; it reads `.env` without overriding variables already set by the shell or CI.
- `debate_app/models.py` defines the shared `Debater`, `DebateSettings`, and `DebateTurn` data objects.
- `debate_app/prompts.py` builds role instructions and turn prompts. Prompts name the other roles and voices, include the full prior debate, and specify the word limit from `argument_time`.
- `debate_app/openai_compatible_client.py` sends bearer-key authenticated Chat Completions requests using the configured endpoint, model, and optional reasoning effort.
- `debate_app/runner.py` runs roles in config order, saves each answer, and queues its speech while the next API response is generated.
- `debate_app/tts.py` selects Kokoro, Pocket TTS, or Chatterbox-Nano and manages the speech workers.
- `pocket_runtime/worker.py` and `chatterbox_runtime/worker.py` implement the isolated CPU speech workers; each runtime directory has its own dependency manifest and lockfile.
- `debate_app/transcript.py` writes the live HTML, audio controls, role colors, and word counts.
- `debate_app/package_builder.py` copies the transcript, matching audio folder, and a short README into `package/`, then writes `package.zip`.
- `tests/` contains offline tests; tests mock API and speech generation and must not make network requests.

Keep each responsibility in its own module. Put settings in `settings.py`, prompt text in `prompts.py`, API work in `openai_compatible_client.py`, speech engines in `tts.py`, debate flow in `runner.py`, and HTML output in `transcript.py`.

## Current behavior

- `[api]` in `config.toml` sets the base URL, API-key environment variable, model, and effort. The client calls `{base_url}/chat/completions`.
- `.env` is local-only. Keep it private; commit only `.env.example`. API keys must never be printed or copied into transcripts or packages.
- A new debate replaces the configured HTML output and clears its matching `<name>_audio/` folder. The transcript is saved after every argument and when its speech becomes ready.
- The browser updates the transcript in place without a full page reload. Audio controls show a loading state until each WAV is ready.
- Speech models are prepared before the first debate turn. Missing Kokoro files are saved under ignored `models/`; speech WAVs are saved beside the HTML file.
- With Chatterbox-Nano, the configured API model may add sparse speech tags to a copy of the argument. The displayed argument and debate history remain unchanged; unsafe edits fall back to the original text.
- Chatterbox-Nano can use its bundled voice or a role-specific reference recording. Pocket TTS uses the configured preset voice for each role.
- The app does not request or display model reasoning.
- The finished package keeps the HTML file beside its matching `<name>_audio/` directory because the page uses relative audio paths.

## Keep this guide current

When a change moves a responsibility, adds a module, changes how the app runs, or changes where settings live, update this guide in the same change. Any AI model or agent working in the project must keep `AGENTS.md` aligned with the code.
