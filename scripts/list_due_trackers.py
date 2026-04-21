#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_search_assistant.tracker_scheduler import (  # noqa: E402
    SQLiteTrackerStateStore,
    TrackerScheduler,
    load_tracker_config,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List trackers that are currently due to run based on source_frequency and local run state."
    )
    parser.add_argument(
        "--config",
        default="config/trackers.toml",
        help="Path to trackers.toml.",
    )
    parser.add_argument(
        "--db",
        default="data/cache/tracker_scheduler.sqlite3",
        help="Path to the tracker scheduler SQLite database.",
    )
    parser.add_argument(
        "--now",
        help="Optional UTC timestamp override in ISO-8601 format, e.g. 2026-04-21T18:00:00Z.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_tracker_config(args.config)
    store = SQLiteTrackerStateStore(args.db)
    scheduler = TrackerScheduler(config, store)
    now = parse_utc_timestamp(args.now) if args.now else None
    payload = [item.to_payload() for item in scheduler.list_due_trackers(now=now)]
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def parse_utc_timestamp(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).replace(microsecond=0)


if __name__ == "__main__":
    main()
