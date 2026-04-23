#!/usr/bin/env python3
from __future__ import annotations

import argparse
import plistlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LABEL = "com.yzhang.jobfunnel.telegram-manual-intake"
DEFAULT_PATH = "/Applications/Codex.app/Contents/Resources:/opt/anaconda3/bin:/usr/bin:/bin:/usr/sbin:/sbin"
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_search_assistant.runtime import configure_logging, format_kv, get_logger


logger = get_logger("deploy.telegram_launch_agent")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install or update the Telegram manual-intake launch agent.")
    parser.add_argument("--label", default=DEFAULT_LABEL)
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--provider", choices=["auto", "codex", "openai", "mock"], default="auto")
    parser.add_argument("--analysis-mode", choices=["quick", "full"], default="full")
    parser.add_argument("--state-file", default="data/processed/telegram_manual_state.json")
    parser.add_argument("--bundle-root", default="data/raw/manual_intake")
    parser.add_argument("--path-env", default=DEFAULT_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(force=True)
    launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
    launch_agents_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = ROOT / "data" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    plist_path = launch_agents_dir / f"{args.label}.plist"
    stdout_path = logs_dir / "telegram_manual_intake.out.log"
    stderr_path = logs_dir / "telegram_manual_intake.err.log"

    program_arguments = [
        sys.executable,
        str(ROOT / "scripts" / "process_telegram_manual_intake.py"),
        "--provider",
        args.provider,
        "--model",
        args.model,
        "--analysis-mode",
        args.analysis_mode,
        "--state-file",
        args.state_file,
        "--bundle-root",
        args.bundle_root,
    ]

    plist_payload = {
        "Label": args.label,
        "ProgramArguments": program_arguments,
        "WorkingDirectory": str(ROOT),
        "EnvironmentVariables": {
            "PATH": args.path_env,
        },
        "RunAtLoad": True,
        "StartInterval": args.interval_seconds,
        "StandardOutPath": str(stdout_path),
        "StandardErrorPath": str(stderr_path),
        "ProcessType": "Background",
    }

    plist_path.write_bytes(plistlib.dumps(plist_payload, sort_keys=False))

    domain_target = f"gui/{_current_uid()}"
    subprocess.run(["launchctl", "bootout", domain_target, str(plist_path)], check=False, capture_output=True, text=True)
    subprocess.run(["launchctl", "bootstrap", domain_target, str(plist_path)], check=True, capture_output=True, text=True)
    subprocess.run(["launchctl", "enable", f"{domain_target}/{args.label}"], check=False, capture_output=True, text=True)
    subprocess.run(["launchctl", "kickstart", "-k", f"{domain_target}/{args.label}"], check=True, capture_output=True, text=True)

    logger.info(
        format_kv(
            "launch_agent.installed",
            label=args.label,
            plist_path=plist_path,
            stdout_log=stdout_path,
            stderr_log=stderr_path,
            interval_seconds=args.interval_seconds,
            path_env=args.path_env,
            provider=args.provider,
            model=args.model,
            analysis_mode=args.analysis_mode,
        )
    )


def _current_uid() -> str:
    result = subprocess.run(["id", "-u"], check=True, capture_output=True, text=True)
    return result.stdout.strip()


if __name__ == "__main__":
    main()
