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

from job_search_assistant.runtime import format_kv, get_logger
from job_search_assistant.runtime.bootstrap import bootstrap_runtime, ensure_runtime_ready
from job_search_assistant.workers.analyzer_service import AnalyzerService
from job_search_assistant.workers.capture_service import CaptureService
from job_search_assistant.workers.output_service import OutputService


logger = get_logger("runtime.smoke_test")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a one-shot runtime smoke test.")
    parser.add_argument("--job-url", required=True, help="Job URL to capture and analyze.")
    parser.add_argument("--source-channel", default="manual_cli")
    parser.add_argument("--reply-chat-id", type=int, help="Optional Telegram chat id for output reply.")
    parser.add_argument("--skip-output", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runtime = bootstrap_runtime(ROOT, force_logging=True)
    capture_service = None
    analyzer_service = None
    output_service = None
    try:
        ensure_runtime_ready(runtime)
        request_id = str(uuid.uuid4())
        payload = {
            "request_id": request_id,
            "source_component": "smoke_test",
            "source_channel": args.source_channel,
            "raw_text": args.job_url,
            "job_url": args.job_url,
            "jd_text": None,
            "company_name": None,
            "notes": "runtime_smoke_test",
            "reply_chat_id": args.reply_chat_id,
            "send_telegram_reply": False,
        }
        runtime.bus.publish(
            topic=runtime.settings.topics.capture_requested,
            event_type="capture.requested",
            payload=payload,
            producer_name="runtime_smoke_test",
            key=request_id,
            correlation_id=request_id,
        )

        capture_service = CaptureService(
            settings=runtime.settings,
            bus=runtime.bus,
            runtime_store=runtime.runtime_store,
            browser_broker=runtime.browser_broker,
        )
        capture_count = capture_service.run_once()

        analyzer_service = AnalyzerService(
            settings=runtime.settings,
            bus=runtime.bus,
            runtime_store=runtime.runtime_store,
        )
        analyzer_count = analyzer_service.run_once()

        output_count = 0
        if not args.skip_output:
            output_service = OutputService(
                settings=runtime.settings,
                bus=runtime.bus,
                runtime_store=runtime.runtime_store,
            )
            output_count = output_service.run_once()

        logger.info(
            format_kv(
                "runtime.smoke_test.done",
                request_id=request_id,
                capture_count=capture_count,
                analyzer_count=analyzer_count,
                output_count=output_count,
            )
        )
    finally:
        if capture_service is not None:
            capture_service.close()
        if analyzer_service is not None:
            analyzer_service.close()
        if output_service is not None:
            output_service.close()
        runtime.close()


if __name__ == "__main__":
    main()
