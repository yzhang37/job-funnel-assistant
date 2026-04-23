from __future__ import annotations

import json
import time
from pathlib import Path

from job_search_assistant.integrations import NotionAnalysisReportClient, TelegramBotClient
from job_search_assistant.manual_flow import build_telegram_short_message, load_capture_bundle_result
from job_search_assistant.runtime import format_kv, get_logger
from job_search_assistant.runtime.config import RuntimeSettings
from job_search_assistant.runtime.kafka_bus import KafkaEventBus
from job_search_assistant.runtime.mysql_runtime import MySQLRuntimeStore


logger = get_logger("service.output")


class OutputService:
    def __init__(self, *, settings: RuntimeSettings, bus: KafkaEventBus, runtime_store: MySQLRuntimeStore) -> None:
        self.settings = settings
        self.bus = bus
        self.runtime_store = runtime_store
        self.consumer = self.bus.build_consumer(
            topics=[self.settings.topics.output_requested],
            group_id=self.settings.output.consumer_group,
        )
        self.notion = NotionAnalysisReportClient() if bool(self.settings.output.extras.get("write_notion", True)) else None
        self.telegram = TelegramBotClient() if bool(self.settings.output.extras.get("send_telegram", True)) else None

    def run_once(self) -> int:
        events = self.bus.poll(self.consumer, timeout_ms=5000, max_records=1)
        if not events:
            return 0
        for event in events:
            payload = dict(event.envelope.payload)
            output_id = str(payload["output_id"])
            analysis_id = str(payload["analysis_id"])
            request_payload = dict(payload["request"])
            bundle_dir = Path(str(payload["bundle_dir"]))
            notion_fields = dict(payload["notion_fields"])
            self.runtime_store.record_output_job(
                output_id=output_id,
                analysis_id=analysis_id,
                status="running",
                payload=payload,
                telegram_chat_id=request_payload.get("reply_chat_id"),
            )
            try:
                notion_url = "dry-run://notion"
                notion_page_id = None
                if self.notion is not None and bool(self.settings.output.extras.get("write_notion", True)):
                    page = self.notion.create_analysis_page(
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
                    notion_page_id = page.page_id
                if self.telegram is not None and request_payload.get("reply_chat_id"):
                    analysis_payload = json.loads((bundle_dir / "analysis_report.json").read_text(encoding="utf-8"))
                    reply = build_telegram_short_message(
                        analysis_payload=analysis_payload,
                        notion_url=notion_url,
                        company_name=notion_fields["company_name"],
                        position_name=notion_fields["position_name"],
                        job_url=request_payload.get("job_url"),
                    )
                    self.telegram.send_message(reply, chat_id=request_payload["reply_chat_id"])
                self.runtime_store.record_output_job(
                    output_id=output_id,
                    analysis_id=analysis_id,
                    status="succeeded",
                    payload=payload,
                    notion_page_id=notion_page_id,
                    notion_page_url=notion_url,
                    telegram_chat_id=request_payload.get("reply_chat_id"),
                )
                logger.info(format_kv("service.output.done", output_id=output_id, notion_url=notion_url))
            except Exception as exc:
                self.runtime_store.record_output_job(
                    output_id=output_id,
                    analysis_id=analysis_id,
                    status="failed",
                    payload=payload,
                    telegram_chat_id=request_payload.get("reply_chat_id"),
                    last_error=str(exc),
                )
                logger.error(format_kv("service.output.failed", output_id=output_id, error=str(exc)))
            self.bus.commit(self.consumer)
        return len(events)

    def run_forever(self) -> None:
        interval = self.settings.output.poll_interval_seconds
        while True:
            try:
                processed = self.run_once()
                sleep_seconds = 1 if processed else interval
            except Exception as exc:  # pragma: no cover - service guard
                logger.error(format_kv("service.output.crashed", error=str(exc)))
                sleep_seconds = interval
            time.sleep(sleep_seconds)

    def close(self) -> None:
        self.consumer.close()
