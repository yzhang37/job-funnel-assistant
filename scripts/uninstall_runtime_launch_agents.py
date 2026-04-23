#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LABEL_PREFIX = "com.yzhang.jobfunnel.runtime"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unload runtime worker launch agents.")
    parser.add_argument("--label-prefix", default=DEFAULT_LABEL_PREFIX)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
    domain_target = f"gui/{_current_uid()}"
    for suffix in ("manual-intake", "capture", "analyzer", "output", "tracker"):
        label = f"{args.label_prefix}.{suffix}"
        plist_path = launch_agents_dir / f"{label}.plist"
        if plist_path.exists():
            subprocess.run(["launchctl", "bootout", domain_target, str(plist_path)], check=False, capture_output=True, text=True)
            subprocess.run(["launchctl", "disable", f"{domain_target}/{label}"], check=False, capture_output=True, text=True)


def _current_uid() -> str:
    result = subprocess.run(["id", "-u"], check=True, capture_output=True, text=True)
    return result.stdout.strip()


if __name__ == "__main__":
    main()
