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

from job_search_assistant.capture import CompanyProfileContent, build_company_profile_bundle  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a reusable company-profile bundle containing markdown, normalized json, and manifest."
    )
    parser.add_argument("--input", required=True, help="Path to a JSON file containing structured company profile data.")
    parser.add_argument("--output-dir", required=True, help="Bundle output directory.")
    parser.add_argument("--company-name", help="Optional company name override.")
    parser.add_argument("--url", help="Optional source URL override.")
    parser.add_argument("--attachment", action="append", default=[], help="Optional attachment file path. Repeat as needed.")
    parser.add_argument("--note", action="append", default=[], help="Optional bundle note. Repeat as needed.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if args.company_name:
        payload["company_name"] = args.company_name
    if args.url:
        payload["source_url"] = args.url
    company_profile = CompanyProfileContent.from_dict(payload)

    manifest_path = build_company_profile_bundle(
        output_dir=args.output_dir,
        company_profile=company_profile,
        attachments=args.attachment,
        source_inputs={"requested_company_name": args.company_name} if args.company_name else None,
        notes=args.note,
    )
    print(manifest_path)


if __name__ == "__main__":
    main()
