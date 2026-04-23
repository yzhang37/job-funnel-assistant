#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import plistlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_search_assistant.runtime import configure_logging, format_kv, get_logger
from job_search_assistant.runtime.bootstrap import bootstrap_runtime, ensure_runtime_ready


LEGACY_LABEL = "com.yzhang.jobfunnel.telegram-manual-intake"
DEFAULT_LABEL_PREFIX = "com.yzhang.jobfunnel.runtime"
DEFAULT_PATH = (
    "/Applications/Codex.app/Contents/Resources:"
    f"{ROOT / '.venv' / 'bin'}:"
    "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
)

logger = get_logger("deploy.runtime_launch_agents")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install or update launch agents for the queue-driven runtime workers.")
    parser.add_argument("--label-prefix", default=DEFAULT_LABEL_PREFIX)
    parser.add_argument("--venv-python", default=str(ROOT / ".venv" / "bin" / "python"))
    parser.add_argument("--path-env", default=DEFAULT_PATH)
    parser.add_argument(
        "--legacy-state-file",
        default="data/processed/telegram_manual_state.json",
        help="Legacy manual-intake offset file to migrate into MySQL runtime state.",
    )
    parser.add_argument(
        "--disable-legacy-telegram-intake",
        action="store_true",
        default=True,
        help="Disable the legacy synchronous Telegram poller before enabling runtime workers.",
    )
    parser.add_argument(
        "--keep-legacy-telegram-intake",
        dest="disable_legacy_telegram_intake",
        action="store_false",
        help="Do not disable the legacy synchronous Telegram poller.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(force=True)

    venv_python = Path(args.venv_python)
    if not venv_python.exists():
        raise SystemExit(
            f"Runtime virtualenv python not found: {venv_python}. "
            "Run ./scripts/bootstrap_runtime_env.sh first."
        )

    runtime = bootstrap_runtime(ROOT, force_logging=False)
    try:
        ensure_runtime_ready(runtime)
        migrated_offset = _migrate_legacy_offset(runtime, ROOT / args.legacy_state_file)
    finally:
        runtime.close()

    launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
    launch_agents_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = ROOT / "data" / "logs" / "runtime"
    logs_dir.mkdir(parents=True, exist_ok=True)

    domain_target = f"gui/{_current_uid()}"

    if args.disable_legacy_telegram_intake:
        _disable_legacy_launch_agent(domain_target, launch_agents_dir / f"{LEGACY_LABEL}.plist")

    services = [
        RuntimeLaunchService(
            name="manual-intake",
            script="run_manual_intake_service.py",
        ),
        RuntimeLaunchService(
            name="capture",
            script="run_capture_service.py",
        ),
        RuntimeLaunchService(
            name="analyzer",
            script="run_analyzer_service.py",
        ),
        RuntimeLaunchService(
            name="output",
            script="run_output_service.py",
        ),
        RuntimeLaunchService(
            name="tracker",
            script="run_tracker_service.py",
            extra_args=["--config", "config/trackers.toml"],
        ),
    ]

    installed_labels: list[str] = []
    for service in services:
        label = f"{args.label_prefix}.{service.name}"
        plist_path = launch_agents_dir / f"{label}.plist"
        stdout_path = logs_dir / f"{service.name}.out.log"
        stderr_path = logs_dir / f"{service.name}.err.log"
        plist_payload = {
            "Label": label,
            "ProgramArguments": [
                str(venv_python),
                str(ROOT / "scripts" / service.script),
                *service.extra_args,
            ],
            "WorkingDirectory": str(ROOT),
            "EnvironmentVariables": {
                "PATH": args.path_env,
                "PYTHONUNBUFFERED": "1",
            },
            "RunAtLoad": True,
            "KeepAlive": True,
            "ProcessType": "Background",
            "ThrottleInterval": 5,
            "StandardOutPath": str(stdout_path),
            "StandardErrorPath": str(stderr_path),
        }
        plist_path.write_bytes(plistlib.dumps(plist_payload, sort_keys=False))
        subprocess.run(["launchctl", "bootout", domain_target, str(plist_path)], check=False, capture_output=True, text=True)
        subprocess.run(["launchctl", "bootstrap", domain_target, str(plist_path)], check=True, capture_output=True, text=True)
        subprocess.run(["launchctl", "enable", f"{domain_target}/{label}"], check=False, capture_output=True, text=True)
        subprocess.run(["launchctl", "kickstart", "-k", f"{domain_target}/{label}"], check=True, capture_output=True, text=True)
        installed_labels.append(label)

    logger.info(
        format_kv(
            "runtime.launch_agents.installed",
            labels=",".join(installed_labels),
            migrated_legacy_offset=migrated_offset if migrated_offset is not None else "",
            path_env=args.path_env,
            venv_python=venv_python,
            disable_legacy=args.disable_legacy_telegram_intake,
        )
    )


class RuntimeLaunchService:
    def __init__(self, *, name: str, script: str, extra_args: list[str] | None = None) -> None:
        self.name = name
        self.script = script
        self.extra_args = list(extra_args or [])


def _migrate_legacy_offset(runtime, legacy_state_path: Path) -> int | None:
    runtime_offset = runtime.runtime_store.get_offset("telegram:last_update_id", default=0)
    if not legacy_state_path.exists():
        return None
    payload = json.loads(legacy_state_path.read_text(encoding="utf-8"))
    legacy_offset = int(payload.get("last_update_id") or 0)
    if legacy_offset > runtime_offset:
        runtime.runtime_store.set_offset("telegram:last_update_id", legacy_offset)
        logger.info(
            format_kv(
                "runtime.offset.migrated",
                source="legacy_json",
                legacy_state_path=legacy_state_path,
                previous_runtime_offset=runtime_offset,
                new_runtime_offset=legacy_offset,
            )
        )
        return legacy_offset
    logger.info(
        format_kv(
            "runtime.offset.migration_skipped",
            legacy_state_path=legacy_state_path,
            legacy_offset=legacy_offset,
            runtime_offset=runtime_offset,
        )
    )
    return None


def _disable_legacy_launch_agent(domain_target: str, plist_path: Path) -> None:
    if plist_path.exists():
        subprocess.run(["launchctl", "bootout", domain_target, str(plist_path)], check=False, capture_output=True, text=True)
        subprocess.run(["launchctl", "disable", f"{domain_target}/{LEGACY_LABEL}"], check=False, capture_output=True, text=True)
    subprocess.run(["pkill", "-f", str(ROOT / "scripts" / "process_telegram_manual_intake.py")], check=False, capture_output=True, text=True)
    logger.info(
        format_kv(
            "runtime.legacy_telegram_intake.disabled",
            label=LEGACY_LABEL,
            plist_path=plist_path,
        )
    )


def _current_uid() -> str:
    result = subprocess.run(["id", "-u"], check=True, capture_output=True, text=True)
    return result.stdout.strip()


if __name__ == "__main__":
    main()
