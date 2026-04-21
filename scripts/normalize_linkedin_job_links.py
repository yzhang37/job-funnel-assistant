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

from job_search_assistant.tracker_scheduler import canonicalize_linkedin_job_urls  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert raw LinkedIn tracker/search-results URLs into canonical "
            "JD links such as https://www.linkedin.com/jobs/view/<job_id>/."
        )
    )
    parser.add_argument("--url", action="append", default=[], help="Raw LinkedIn URL. Repeat as needed.")
    parser.add_argument(
        "--input-file",
        help="Optional text file with one raw LinkedIn URL per line.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raw_urls = list(args.url)
    if args.input_file:
        raw_urls.extend(load_urls(args.input_file))

    payload = canonicalize_linkedin_job_urls(raw_urls)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def load_urls(path: str | Path) -> list[str]:
    raw = Path(path).read_text(encoding="utf-8")
    return [line.strip() for line in raw.splitlines() if line.strip()]


if __name__ == "__main__":
    main()
