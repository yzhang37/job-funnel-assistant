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
from job_search_assistant.workers.output_service import OutputService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Output worker.")
    parser.add_argument("--once", action="store_true", help="Consume at most one Kafka batch and exit.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runtime = bootstrap_runtime(ROOT, force_logging=True)
    service = None
    try:
        service = OutputService(
            settings=runtime.settings,
            bus=runtime.bus,
            runtime_store=runtime.runtime_store,
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
