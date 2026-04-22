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

from job_search_assistant.tracker_scheduler import (  # noqa: E402
    SQLiteTrackerStateStore,
    TrackerScheduler,
    load_tracker_config,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Canonicalize one browser-collected tracker batch and report which JD links are "
            "new vs already known."
        )
    )
    parser.add_argument("--config", default="config/trackers.toml", help="Path to trackers.toml.")
    parser.add_argument(
        "--db",
        default="data/cache/tracker_scheduler.sqlite3",
        help="Path to the tracker scheduler SQLite database.",
    )
    parser.add_argument("--tracker-id", required=True, help="Tracker id from trackers.toml.")
    parser.add_argument(
        "--raw-url",
        action="append",
        default=[],
        help="Raw browser-observed job URL. Repeat as needed.",
    )
    parser.add_argument(
        "--raw-urls-file",
        help="Optional path to a newline-delimited text file or JSON list of raw browser-observed job URLs.",
    )
    parser.add_argument(
        "--source-exhausted",
        action="store_true",
        help="Mark this batch as end-of-results for the current source.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_tracker_config(args.config)
    store = SQLiteTrackerStateStore(args.db)
    scheduler = TrackerScheduler(config, store)
    session = scheduler.start_browser_discovery_session(args.tracker_id)

    raw_urls = list(args.raw_url)
    if args.raw_urls_file:
        raw_urls.extend(load_urls(args.raw_urls_file))

    batch = session.ingest_raw_job_urls(
        raw_urls,
        source_exhausted=args.source_exhausted,
    )
    print(json.dumps(batch.to_payload(), ensure_ascii=False, indent=2))


def load_urls(path: str | Path) -> list[str]:
    input_path = Path(path)
    raw = input_path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    if input_path.suffix.lower() == ".json":
        payload = json.loads(raw)
        if not isinstance(payload, list):
            raise ValueError("JSON raw URL input must be a list.")
        return [str(item).strip() for item in payload if str(item).strip()]
    return [line.strip() for line in raw.splitlines() if line.strip()]


if __name__ == "__main__":
    main()
