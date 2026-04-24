#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_search_assistant.runtime import format_kv, get_logger
from job_search_assistant.runtime.bootstrap import bootstrap_runtime, ensure_runtime_ready


logger = get_logger("service.tracker.control")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Set worker-scoped Tracker control state.")
    parser.add_argument(
        "--state",
        choices=("running", "drain-current", "stopped"),
        required=True,
        help="running clears drain behavior; drain-current finishes only current in-flight message; stopped exits idle workers.",
    )
    parser.add_argument("--worker-id", default="default")
    parser.add_argument("--node-id", default="")
    parser.add_argument("--reason", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runtime = bootstrap_runtime(ROOT, force_logging=True)
    try:
        ensure_runtime_ready(runtime)
        node_id = args.node_id or runtime.settings.browser_broker.node_id
        runtime.runtime_store.set_worker_control(
            component_name="tracker",
            node_id=node_id,
            worker_id=args.worker_id,
            desired_state=args.state,
            shutdown_mode="drain-current" if args.state == "drain-current" else None,
            reason=args.reason or "manual control",
        )
        logger.info(
            format_kv(
                "service.tracker.control.updated",
                node_id=node_id,
                worker_id=args.worker_id,
                state=args.state,
            )
        )
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
