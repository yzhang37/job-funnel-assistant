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

from job_search_assistant.capture import (  # noqa: E402
    CompanyProfileContent,
    JobPostingContent,
    build_job_capture_bundle,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a reusable job-capture bundle containing jd markdown, optional company profile, and manifest."
    )
    parser.add_argument("--job-input", required=True, help="Path to a JSON file containing structured job capture data.")
    parser.add_argument("--company-profile-input", help="Optional JSON file containing structured company profile data.")
    parser.add_argument("--output-dir", required=True, help="Bundle output directory.")
    parser.add_argument("--job-url", help="Optional job URL override.")
    parser.add_argument("--company-name", help="Optional company name override.")
    parser.add_argument("--platform", help="Optional source platform override for the job payload.")
    parser.add_argument("--attachment", action="append", default=[], help="Optional attachment file path. Repeat as needed.")
    parser.add_argument("--note", action="append", default=[], help="Optional bundle note. Repeat as needed.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    job_payload = json.loads(Path(args.job_input).read_text(encoding="utf-8"))
    if args.job_url:
        job_payload["source_url"] = args.job_url
    if args.company_name:
        job_payload["company"] = args.company_name
    if args.platform:
        job_payload["source_platform"] = args.platform
    posting = JobPostingContent.from_dict(job_payload)

    company_profile = None
    if args.company_profile_input:
        company_payload = json.loads(Path(args.company_profile_input).read_text(encoding="utf-8"))
        if args.company_name:
            company_payload["company_name"] = args.company_name
        company_profile = CompanyProfileContent.from_dict(company_payload)

    manifest_path = build_job_capture_bundle(
        output_dir=args.output_dir,
        posting=posting,
        company_profile=company_profile,
        attachments=args.attachment,
        source_inputs={"requested_job_url": args.job_url} if args.job_url else None,
        notes=args.note,
    )
    print(manifest_path)


if __name__ == "__main__":
    main()
