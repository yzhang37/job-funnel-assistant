#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_search_assistant.runtime import format_kv, get_logger
from job_search_assistant.runtime.bootstrap import bootstrap_runtime, ensure_runtime_ready


logger = get_logger("runtime.init")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize local MySQL/Kafka runtime state.")
    parser.add_argument("--retries", type=int, default=30)
    parser.add_argument("--retry-delay-seconds", type=int, default=3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    last_error: Exception | None = None
    for attempt in range(1, args.retries + 1):
        try:
            runtime = bootstrap_runtime(ROOT, force_logging=True)
            try:
                ensure_runtime_ready(runtime)
            finally:
                runtime.close()
            logger.info(
                format_kv(
                    "runtime.init.done",
                    attempt=attempt,
                    retries=args.retries,
                )
            )
            return
        except Exception as exc:
            last_error = exc
            logger.warning(
                format_kv(
                    "runtime.init.retry",
                    attempt=attempt,
                    retries=args.retries,
                    error=str(exc),
                )
            )
            time.sleep(args.retry_delay_seconds)
    assert last_error is not None
    raise SystemExit(f"Runtime init failed after {args.retries} attempts: {last_error}")


if __name__ == "__main__":
    main()
