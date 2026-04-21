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

from job_search_assistant.job_fit import analyze_job_fit, load_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze whether a job fits the candidate profile.")
    parser.add_argument("--job", required=True, help="Path to a job JSON file.")
    parser.add_argument("--profile", required=True, help="Path to an analysis profile JSON file.")
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output for easier reading.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    job = load_json(args.job)
    profile = load_json(args.profile)
    result = analyze_job_fit(job, profile)

    payload = {
        "job": {
            "title": job.get("title"),
            "company": job.get("company"),
            "location": job.get("location"),
        },
        "analysis": result.to_dict(),
    }

    if args.pretty:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()

