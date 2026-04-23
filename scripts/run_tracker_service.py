#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_search_assistant.runtime.bootstrap import bootstrap_runtime
from job_search_assistant.tracker_scheduler import load_tracker_config
from job_search_assistant.workers.tracker_service import TrackerService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Tracker worker.")
    parser.add_argument("--once", action="store_true", help="Schedule due trackers and consume at most one discovery request.")
    parser.add_argument("--config", default="config/trackers.toml", help="Tracker config file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runtime = bootstrap_runtime(ROOT, force_logging=True)
    service = None
    try:
        tracker_config = load_tracker_config(ROOT / args.config)
        service = TrackerService(
            settings=runtime.settings,
            bus=runtime.bus,
            runtime_store=runtime.runtime_store,
            tracker_config=tracker_config,
            browser_broker=runtime.browser_broker,
        )
        if args.once:
            service.run_once()
            return
        service.run_forever()
    finally:
        if service is not None:
            service.close()
        runtime.close()


if __name__ == "__main__":
    main()
