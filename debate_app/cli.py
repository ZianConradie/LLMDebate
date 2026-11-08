"""Command-line entry point for the debate app."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from debate_app.runner import DebateRunner
from debate_app.settings import SettingsOverrides, load_settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a multi-role debate.")
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "config.toml",
        help="Settings file (default: config.toml).",
    )
    parser.add_argument("--topic", help="Replace the topic from the config file.")
    parser.add_argument("--role1", help="Replace the first role.")
    parser.add_argument("--role2", help="Replace the second role.")
    parser.add_argument(
        "--argument-limit",
        "--round-limit",
        dest="argument_limit",
        type=int,
        help="Arguments each side makes.",
    )
    parser.add_argument(
        "--argument-time",
        type=int,
        help="Seconds allowed for each argument (3 words per second).",
    )
    parser.add_argument("--output", help="Replace the HTML output path.")
    return parser


def main() -> int:
    parser = _make_parser()
    args = parser.parse_args()
    overrides = SettingsOverrides(
        topic=args.topic,
        role1=args.role1,
        role2=args.role2,
        argument_limit=args.argument_limit,
        argument_time=args.argument_time,
        output_path=args.output,
    )

    try:
        settings = load_settings(args.config, overrides)
    except (OSError, TypeError, ValueError) as exc:
        parser.error(str(exc))

    try:
        DebateRunner(settings).run()
    except (OSError, RuntimeError) as exc:
        print(f"Debate stopped: {exc}", file=sys.stderr)
        print(f"Completed turns are saved in {settings.output_path}", file=sys.stderr)
        return 1

    print(f"Debate complete. Transcript: {settings.output_path}")
    return 0
