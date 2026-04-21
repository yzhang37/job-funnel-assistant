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

from job_search_assistant.capture import JobPostingContent, render_jd_markdown


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a structured capture payload into jd markdown.")
    parser.add_argument("--input", required=True, help="Path to a JSON file containing extracted job sections.")
    parser.add_argument("--output", help="Optional output path for the generated markdown.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    posting = JobPostingContent.from_dict(payload)
    markdown = render_jd_markdown(posting)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main()

