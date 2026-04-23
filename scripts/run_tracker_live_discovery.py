#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_search_assistant.runtime import configure_logging, load_local_env  # noqa: E402
from job_search_assistant.tracker_scheduler import (  # noqa: E402
    SQLiteTrackerStateStore,
    TrackerScheduler,
    load_tracker_config,
    run_live_tracker_discovery,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one live tracker discovery pass using Codex + Computer Use."
    )
    parser.add_argument("--config", default="config/trackers.toml", help="Path to trackers.toml.")
    parser.add_argument(
        "--db",
        default="data/cache/tracker_scheduler.sqlite3",
        help="Path to the tracker scheduler SQLite database.",
    )
    parser.add_argument("--tracker-id", required=True, help="Tracker id from trackers.toml.")
    parser.add_argument("--model", default="gpt-5.4", help="Model name passed to codex exec.")
    parser.add_argument("--max-attempts", type=int, default=2, help="Max Codex attempts for this run.")
    parser.add_argument(
        "--target-new-jobs",
        type=int,
        help="Optional runtime-only override for target_new_jobs, useful for testing.",
    )
    parser.add_argument(
        "--no-record",
        action="store_true",
        help="Do not persist tracker run state or discovered jobs.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Structured log level (DEBUG, INFO, WARN, ERROR).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_local_env(ROOT)
    configure_logging(args.log_level)
    config = load_tracker_config(args.config)
    store = SQLiteTrackerStateStore(args.db)
    scheduler = TrackerScheduler(config, store)

    result = run_live_tracker_discovery(
        scheduler=scheduler,
        tracker_id=args.tracker_id,
        model=args.model,
        max_attempts=args.max_attempts,
        target_new_jobs_override=args.target_new_jobs,
        record_run=not args.no_record,
    )
    print(json.dumps(result.to_payload(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
