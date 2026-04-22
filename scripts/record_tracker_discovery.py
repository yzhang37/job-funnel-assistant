#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_search_assistant.tracker_scheduler import (  # noqa: E402
    SQLiteTrackerStateStore,
    TrackerScheduler,
    canonicalize_job_urls,
    infer_job_platform,
    load_tracker_config,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record one tracker run and persist any discovered job links."
    )
    parser.add_argument("--config", default="config/trackers.toml", help="Path to trackers.toml.")
    parser.add_argument(
        "--db",
        default="data/cache/tracker_scheduler.sqlite3",
        help="Path to the tracker scheduler SQLite database.",
    )
    parser.add_argument("--tracker-id", required=True, help="Tracker id from trackers.toml.")
    parser.add_argument("--job-url", action="append", default=[], help="Discovered job URL. Repeat as needed.")
    parser.add_argument(
        "--raw-url",
        action="append",
        default=[],
        help="Raw browser-observed job URL. Repeat as needed; it will be canonicalized based on tracker platform.",
    )
    parser.add_argument(
        "--job-urls-file",
        help="Optional path to a newline-delimited text file or JSON list of job URLs.",
    )
    parser.add_argument(
        "--raw-urls-file",
        help="Optional path to a newline-delimited text file or JSON list of raw browser-observed job URLs.",
    )
    parser.add_argument(
        "--status",
        default="success",
        choices=["success", "failed"],
        help="Run status. Failed runs may record zero job URLs.",
    )
    parser.add_argument("--started-at", help="Optional UTC ISO-8601 start timestamp.")
    parser.add_argument("--finished-at", help="Optional UTC ISO-8601 finish timestamp.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_tracker_config(args.config)
    store = SQLiteTrackerStateStore(args.db)
    scheduler = TrackerScheduler(config, store)
    tracker = config.get_tracker(args.tracker_id)

    job_urls = list(args.job_url)
    if args.job_urls_file:
        job_urls.extend(load_job_urls(args.job_urls_file))
    raw_urls = list(args.raw_url)
    if args.raw_urls_file:
        raw_urls.extend(load_job_urls(args.raw_urls_file))
    if raw_urls:
        job_urls.extend(
            canonicalize_job_urls(
                raw_urls,
                platform=infer_job_platform(tracker.url),
            )
        )

    started_at = parse_utc_timestamp(args.started_at) if args.started_at else None
    finished_at = parse_utc_timestamp(args.finished_at) if args.finished_at else None

    summary = scheduler.record_discovery(
        tracker_id=args.tracker_id,
        job_urls=job_urls,
        status=args.status,
        started_at=started_at,
        finished_at=finished_at,
    )
    print(json.dumps(summary.to_payload(), ensure_ascii=False, indent=2))


def load_job_urls(path: str | Path) -> list[str]:
    input_path = Path(path)
    raw = input_path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    if input_path.suffix.lower() == ".json":
        payload = json.loads(raw)
        return _job_urls_from_json(payload)
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _job_urls_from_json(payload: Any) -> list[str]:
    if isinstance(payload, list):
        values: list[str] = []
        for item in payload:
            if isinstance(item, str) and item.strip():
                values.append(item.strip())
            elif isinstance(item, dict):
                job_url = str(item.get("job_url") or item.get("url") or "").strip()
                if job_url:
                    values.append(job_url)
        return values
    raise ValueError("JSON job URL input must be a list of strings or objects containing job_url/url.")


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
