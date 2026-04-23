#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run stable predeploy checks: compile validation, fixed unit tests, and optional live runtime smoke."
    )
    parser.add_argument(
        "--run-live-smoke",
        action="store_true",
        help="After fixed tests pass, run one live runtime smoke test.",
    )
    parser.add_argument(
        "--job-url",
        help="Required when --run-live-smoke is set.",
    )
    parser.add_argument(
        "--reply-chat-id",
        type=int,
        help="Optional Telegram chat id for the live smoke test.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    python = sys.executable
    _run([python, "-m", "compileall", "-q", "src", "scripts", "tests"], label="compile")
    _run([python, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"], label="unit-and-fixed-e2e")

    if args.run_live_smoke:
        if not args.job_url:
            raise SystemExit("--job-url is required when --run-live-smoke is set.")
        command = [python, "scripts/runtime_smoke_test.py", "--job-url", args.job_url]
        if args.reply_chat_id is not None:
            command.extend(["--reply-chat-id", str(args.reply_chat_id)])
        else:
            command.append("--skip-output")
        _run(command, label="live-runtime-smoke")


def _run(command: list[str], *, label: str) -> None:
    print(f"[predeploy] {label}: {' '.join(command)}")
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
