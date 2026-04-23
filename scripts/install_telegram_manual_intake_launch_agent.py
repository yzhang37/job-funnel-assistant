#!/usr/bin/env python3
from __future__ import annotations

import argparse
import plistlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LABEL = "com.yzhang.jobfunnel.telegram-manual-intake"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install or update the Telegram manual-intake launch agent.")
    parser.add_argument("--label", default=DEFAULT_LABEL)
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--provider", choices=["auto", "codex", "openai", "mock"], default="auto")
    parser.add_argument("--analysis-mode", choices=["quick", "full"], default="full")
    parser.add_argument("--state-file", default="data/processed/telegram_manual_state.json")
    parser.add_argument("--bundle-root", default="data/raw/manual_intake")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
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

    print(f"Installed launch agent: {plist_path}")
    print(f"Label: {args.label}")
    print(f"Stdout log: {stdout_path}")
    print(f"Stderr log: {stderr_path}")


def _current_uid() -> str:
    result = subprocess.run(["id", "-u"], check=True, capture_output=True, text=True)
    return result.stdout.strip()


if __name__ == "__main__":
    main()
