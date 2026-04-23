#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
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
    normalize_manual_intake_request,
    parse_manual_intake_text,
    run_analysis_for_capture_bundle,
)
from job_search_assistant.runtime import configure_logging, format_kv, get_logger, load_local_env


logger = get_logger("manual_intake.once")


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
    configure_logging(force=True)
    load_local_env(ROOT)
    started = time.monotonic()
    raw_text = args.text or Path(args.text_file).read_text(encoding="utf-8")
    request = parse_manual_intake_text(raw_text, source_channel=args.source_channel)
    request = normalize_manual_intake_request(
        repo_root=ROOT,
        request=request,
        model=args.model,
    )
    logger.info(
        format_kv(
            "manual_intake.once.start",
            source_channel=args.source_channel,
            input_kind="job_url" if request.job_url and not request.jd_text else "job_url_and_jd_text" if request.job_url and request.jd_text else "jd_text",
            job_url=request.job_url,
            provider=args.provider,
            model=args.model,
            analysis_mode=args.analysis_mode,
            write_notion=args.write_notion,
            send_telegram=args.send_telegram,
        )
    )
    capture_bundle = build_manual_capture_bundle(
        repo_root=ROOT,
        request=request,
        output_root=ROOT / args.bundle_root,
        model=args.model,
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
        notion_started = time.monotonic()
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
        logger.info(
            format_kv(
                "notion.write.done",
                page_id=page.page_id,
                page_url=page.page_url,
                duration_ms=int((time.monotonic() - notion_started) * 1000),
            )
        )
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
        logger.info(format_kv("telegram.reply.sent", reply_chars=len(reply), notion_url=notion_url))
    logger.info(
        format_kv(
            "manual_intake.once.done",
            bundle_dir=capture_bundle.bundle_dir,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    )
    logger.info(format_kv("manual_intake.once.reply", reply_preview=reply[:240]))


if __name__ == "__main__":
    main()
