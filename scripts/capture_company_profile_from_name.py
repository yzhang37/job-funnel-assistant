#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_search_assistant.capture import (
    CompanyProfileContent,
    build_company_profile_bundle,
    codex_live_capture_company_name,
)
from job_search_assistant.runtime import configure_logging, format_kv, get_logger, load_local_env


logger = get_logger("capture.company_name")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture a company profile bundle from a company name using Codex + Computer Use.")
    parser.add_argument("--company-name", required=True)
    parser.add_argument("--job-url")
    parser.add_argument("--jd-text-file")
    parser.add_argument("--output-root", default="data/raw/company_profile_capture")
    parser.add_argument("--model", default="gpt-5.4")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(force=True)
    load_local_env(ROOT)
    jd_text = Path(args.jd_text_file).read_text(encoding="utf-8") if args.jd_text_file else None

    logger.info(
        format_kv(
            "capture.company_name.start",
            company_name=args.company_name,
            job_url=args.job_url,
            has_jd_text=bool(jd_text),
            model=args.model,
        )
    )
    payload = codex_live_capture_company_name(
        company_name=args.company_name,
        job_url=args.job_url,
        jd_text=jd_text,
        model=args.model,
    )
    profile = CompanyProfileContent.from_dict(payload)
    run_stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bundle_dir = ROOT / args.output_root / f"{run_stamp}-{_slugify(args.company_name)}"
    manifest_path = build_company_profile_bundle(
        output_dir=bundle_dir,
        company_profile=profile,
        repo_root=ROOT,
        source_inputs={
            "input_kind": "company_name_capture",
            "company_name": args.company_name,
            "job_url": args.job_url,
        },
    )
    logger.info(
        format_kv(
            "capture.company_name.done",
            company_name=args.company_name,
            bundle_dir=bundle_dir,
            manifest=manifest_path,
        )
    )
    print(json.dumps({"bundle_dir": str(bundle_dir), "manifest": str(manifest_path)}, ensure_ascii=False, indent=2))


def _slugify(text: str) -> str:
    return "-".join(part for part in "".join(ch.lower() if ch.isalnum() else "-" for ch in text).split("-") if part) or "company"


if __name__ == "__main__":
    main()
