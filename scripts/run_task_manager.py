#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_search_assistant.task_manager import run_task_manager_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local Job Funnel Task Manager web UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_task_manager_server(repo_root=ROOT, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
