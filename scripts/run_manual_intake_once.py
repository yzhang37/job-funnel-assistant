#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_search_assistant.integrations import NotionAnalysisReportClient, TelegramBotClient
from job_search_assistant.manual_flow import (
    build_manual_capture_bundle,
    build_notion_payload_fields,
    build_telegram_short_message,
    parse_manual_intake_text,
    run_analysis_for_capture_bundle,
)
from job_search_assistant.runtime import load_local_env


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one manual intake payload end-to-end.")
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--text", help="Manual intake text payload.")
    input_group.add_argument("--text-file", help="File containing the manual intake payload.")
    parser.add_argument("--source-channel", default="manual_cli")
    parser.add_argument("--profile-stack", default="profiles/default_stack.json")
    parser.add_argument("--provider", choices=["auto", "codex", "openai", "mock"], default="auto")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--analysis-mode", choices=["quick", "full"], default="full")
    parser.add_argument("--enable-web-search", action="store_true")
    parser.add_argument("--bundle-root", default="data/raw/manual_intake")
    parser.add_argument("--send-telegram", action="store_true")
    parser.add_argument("--write-notion", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_local_env(ROOT)
    raw_text = args.text or Path(args.text_file).read_text(encoding="utf-8")
    request = parse_manual_intake_text(raw_text, source_channel=args.source_channel)
    capture_bundle = build_manual_capture_bundle(
        repo_root=ROOT,
        request=request,
        output_root=ROOT / args.bundle_root,
    )
    analysis = run_analysis_for_capture_bundle(
        repo_root=ROOT,
        request=request,
        capture_bundle=capture_bundle,
        profile_stack_path=args.profile_stack,
        provider_name=args.provider,
        model=args.model,
        analysis_mode=args.analysis_mode,
        enable_web_search=args.enable_web_search,
    )
    notion_fields = build_notion_payload_fields(
        request=request,
        capture_bundle=capture_bundle,
        analysis_payload=analysis.payload,
    )
    notion_url = "local-only://analysis-report"
    if args.write_notion:
        notion = NotionAnalysisReportClient()
        page = notion.create_analysis_page(
            title=notion_fields["title"],
            company_name=notion_fields["company_name"],
            position_name=notion_fields["position_name"],
            job_url=notion_fields["job_url"],
            source_platform=notion_fields["source_platform"],
            input_method=notion_fields["input_method"],
            decision=notion_fields["decision"],
            fit_score=notion_fields["fit_score"],
            one_sentence=notion_fields["one_sentence"],
            core_reasons=notion_fields["core_reasons"],
            key_risk=notion_fields["key_risk"],
            recommended_action=notion_fields["recommended_action"],
            company_profile_summary=notion_fields["company_profile_summary"],
            analyzed_at=notion_fields["analyzed_at"],
            bundle_path=notion_fields["bundle_path"],
            report_markdown=notion_fields["report_markdown"],
            jd_markdown=notion_fields["jd_markdown"],
            company_profile_markdown=notion_fields["company_profile_markdown"],
        )
        notion_url = page.page_url
        print(f"Notion: {notion_url}")
    reply = build_telegram_short_message(
        analysis_payload=analysis.payload,
        notion_url=notion_url,
        company_name=notion_fields["company_name"],
        position_name=notion_fields["position_name"],
        job_url=request.job_url,
    )
    if args.send_telegram:
        telegram = TelegramBotClient()
        telegram.send_message(reply)
    print(reply)


if __name__ == "__main__":
    main()
