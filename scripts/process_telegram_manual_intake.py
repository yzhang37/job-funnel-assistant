#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
    looks_like_job_input,
    normalize_manual_intake_request,
    parse_manual_intake_text,
    run_analysis_for_capture_bundle,
)
from job_search_assistant.runtime import configure_logging, format_kv, get_logger, load_local_env


logger = get_logger("telegram.manual_intake")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process one Telegram manual-intake message end-to-end.")
    parser.add_argument("--state-file", default="data/processed/telegram_manual_state.json")
    parser.add_argument("--profile-stack", default="profiles/default_stack.json")
    parser.add_argument("--provider", choices=["auto", "codex", "openai", "mock"], default="auto")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--analysis-mode", choices=["quick", "full"], default="full")
    parser.add_argument("--enable-web-search", action="store_true")
    parser.add_argument("--bundle-root", default="data/raw/manual_intake")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(force=True)
    load_local_env(ROOT)
    state_path = ROOT / args.state_file
    state = _load_state(state_path)
    logger.info(
        format_kv(
            "telegram.poll.start",
            state_file=state_path,
            last_update_id=state.get("last_update_id", 0),
            provider=args.provider,
            model=args.model,
            analysis_mode=args.analysis_mode,
            dry_run=args.dry_run,
        )
    )

    telegram = TelegramBotClient()
    updates = telegram.get_updates(offset=state.get("last_update_id", 0) + 1)
    if not updates:
        logger.debug(format_kv("telegram.poll.empty", last_update_id=state.get("last_update_id", 0)))
        return
    logger.info(format_kv("telegram.poll.received", update_count=len(updates)))

    notion = None if args.dry_run else NotionAnalysisReportClient()

    for message in updates:
        message_started = time.monotonic()
        if not telegram.is_owner_message(message):
            logger.warning(
                format_kv(
                    "telegram.poll.ignored_non_owner",
                    update_id=message.update_id,
                    chat_id=message.chat_id,
                    from_user_id=message.from_user_id,
                    from_is_bot=message.from_is_bot,
                )
            )
            state["last_update_id"] = message.update_id
            _save_state(state_path, state)
            continue
        logger.info(
            format_kv(
                "telegram.poll.accepted",
                update_id=message.update_id,
                chat_id=message.chat_id,
                message_id=message.message_id,
                text_preview=message.text[:160],
            )
        )
        request = parse_manual_intake_text(message.text, source_channel="telegram")
        if not looks_like_job_input(request):
            reply = "这条 Telegram 消息看起来不像岗位输入。请直接发 JD 正文、岗位链接，或“岗位链接 + JD 正文”。"
            if not args.dry_run:
                telegram.send_message(reply, chat_id=message.chat_id)
            logger.warning(
                format_kv(
                    "telegram.poll.invalid_input",
                    update_id=message.update_id,
                    chat_id=message.chat_id,
                    message_id=message.message_id,
                )
            )
            state["last_update_id"] = message.update_id
            _save_state(state_path, state)
            continue
        request = normalize_manual_intake_request(
            repo_root=ROOT,
            request=request,
            model=args.model,
        )

        notion_started = None
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

        notion_url = "dry-run://notion"
        if notion is not None:
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
                    update_id=message.update_id,
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
        if not args.dry_run:
            telegram.send_message(reply, chat_id=message.chat_id)
            logger.info(
                format_kv(
                    "telegram.reply.sent",
                    update_id=message.update_id,
                    chat_id=message.chat_id,
                    notion_url=notion_url,
                    reply_chars=len(reply),
                )
            )
        logger.info(
            format_kv(
                "telegram.poll.done",
                update_id=message.update_id,
                input_kind="job_url" if request.job_url and not request.jd_text else "job_url_and_jd_text" if request.job_url and request.jd_text else "jd_text",
                bundle_dir=capture_bundle.bundle_dir,
                duration_ms=int((time.monotonic() - message_started) * 1000),
            )
        )
        state["last_update_id"] = message.update_id
        _save_state(state_path, state)


def _load_state(path: Path) -> dict[str, int]:
    if not path.exists():
        return {"last_update_id": 0}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_state(path: Path, payload: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
