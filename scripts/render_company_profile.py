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

from job_search_assistant.capture import (
    CompanyProfileContent,
    render_company_profile_markdown,
    write_company_profile_cache,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a loosely structured company profile capture into markdown and optional cache rows."
    )
    parser.add_argument("--input", required=True, help="Path to a JSON file containing captured company profile data.")
    parser.add_argument("--output", help="Optional output path for the generated markdown.")
    parser.add_argument("--url", help="Optional source URL override.")
    parser.add_argument("--company-name", help="Optional company name override.")
    parser.add_argument("--cache-db", help="Optional SQLite cache database path.")
    parser.add_argument(
        "--cache-config",
        default=str(ROOT / "config" / "cache_policy.toml"),
        help="Cache policy config path. Used when --cache-db is provided.",
    )
    parser.add_argument(
        "--print-cache-summary",
        action="store_true",
        help="Print namespace and field counts after writing cache entries.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if args.url:
        payload["source_url"] = args.url
    if args.company_name:
        payload["company_name"] = args.company_name
    profile = CompanyProfileContent.from_dict(payload)
    markdown = render_company_profile_markdown(profile)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")

    print(markdown)

    if args.cache_db:
        cache_summary = write_company_profile_cache(
            profile,
            repo_root=ROOT,
            cache_db=Path(args.cache_db),
            cache_config=Path(args.cache_config),
        )
        if args.print_cache_summary:
            for namespace, field_count in cache_summary.items():
                print(f"[cache] {namespace}: {field_count} fields")


if __name__ == "__main__":
    main()
