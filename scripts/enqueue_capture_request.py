#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_search_assistant.manual_flow import parse_manual_intake_text
from job_search_assistant.runtime import format_kv, get_logger
from job_search_assistant.runtime.bootstrap import bootstrap_runtime


logger = get_logger("runtime.enqueue_capture")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish one capture.requested event to Kafka.")
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--text", help="Manual intake text payload.")
    input_group.add_argument("--text-file", help="File containing the manual intake payload.")
    parser.add_argument("--source-channel", default="manual_cli")
    parser.add_argument("--source-component", default="manual_intake")
    parser.add_argument("--send-telegram-reply", action="store_true")
    parser.add_argument("--reply-chat-id", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runtime = bootstrap_runtime(ROOT, force_logging=True)
    try:
        raw_text = args.text or Path(args.text_file).read_text(encoding="utf-8")
        request = parse_manual_intake_text(raw_text, source_channel=args.source_channel)
        request_id = str(uuid.uuid4())
        payload = {
            "request_id": request_id,
            "source_component": args.source_component,
            "source_channel": request.source_channel,
            "raw_text": request.raw_text,
            "job_url": request.job_url,
            "jd_text": request.jd_text,
            "company_name": request.company_name,
            "notes": request.notes,
            "reply_chat_id": args.reply_chat_id,
            "send_telegram_reply": args.send_telegram_reply,
        }
        runtime.bus.publish(
            topic=runtime.settings.topics.capture_requested,
            event_type="capture.requested",
            payload=payload,
            producer_name="manual_intake_cli",
            key=request_id,
            correlation_id=request_id,
        )
        logger.info(
            format_kv(
                "runtime.enqueue_capture.done",
                request_id=request_id,
                job_url=request.job_url,
                has_jd_text=bool(request.jd_text),
                source_channel=request.source_channel,
            )
        )
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
