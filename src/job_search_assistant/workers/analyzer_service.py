from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from job_search_assistant.manual_flow import (
    ManualIntakeRequest,
    build_notion_payload_fields,
    load_capture_bundle_result,
    run_analysis_for_capture_bundle,
)
from job_search_assistant.runtime import format_kv, get_logger
from job_search_assistant.runtime.config import RuntimeSettings
from job_search_assistant.runtime.kafka_bus import KafkaEventBus
from job_search_assistant.runtime.mysql_runtime import MySQLRuntimeStore


logger = get_logger("service.analyzer")


class AnalyzerService:
    def __init__(self, *, settings: RuntimeSettings, bus: KafkaEventBus, runtime_store: MySQLRuntimeStore) -> None:
        self.settings = settings
        self.bus = bus
        self.runtime_store = runtime_store
        self.consumer = self.bus.build_consumer(
            topics=[self.settings.topics.analysis_requested],
            group_id=self.settings.analyzer.consumer_group,
        )

    def run_once(self) -> int:
        events = self.bus.poll(self.consumer, timeout_ms=5000, max_records=1)
        if not events:
            return 0
        for event in events:
            payload = dict(event.envelope.payload)
            analysis_id = str(payload["analysis_id"])
            capture_id = str(payload["capture_id"])
            request_payload = dict(payload["request"])
            bundle_dir = Path(str(payload["bundle_dir"]))
            request = ManualIntakeRequest(
                source_channel=str(request_payload.get("source_channel") or "other"),
                raw_text=str(request_payload.get("raw_text") or ""),
                job_url=request_payload.get("job_url"),
                jd_text=request_payload.get("jd_text"),
                company_name=request_payload.get("company_name"),
                notes=request_payload.get("notes"),
            )
            self.runtime_store.record_analysis_job(
                analysis_id=analysis_id,
                capture_id=capture_id,
                bundle_dir=str(bundle_dir),
                status="running",
                payload=payload,
            )
            try:
                capture_bundle = load_capture_bundle_result(bundle_dir)
                result = run_analysis_for_capture_bundle(
                    repo_root=self.settings.repo_root,
                    request=request,
                    capture_bundle=capture_bundle,
                    profile_stack_path=str(self.settings.analyzer.extras.get("profile_stack")),
                    provider_name=str(self.settings.analyzer.extras.get("provider", "auto")),
                    model=str(self.settings.analyzer.extras.get("model", "gpt-5.4")),
                    analysis_mode=str(self.settings.analyzer.extras.get("analysis_mode", "full")),
                    enable_web_search=bool(self.settings.analyzer.extras.get("enable_web_search", False)),
                )
                notion_fields = build_notion_payload_fields(
                    request=request,
                    capture_bundle=capture_bundle,
                    analysis_payload=result.payload,
                )
                self.runtime_store.record_analysis_job(
                    analysis_id=analysis_id,
                    capture_id=capture_id,
                    bundle_dir=str(bundle_dir),
                    status="succeeded",
                    payload=payload,
                    decision=str(notion_fields["decision"]),
                    fit_score=notion_fields["fit_score"],
                )
                ready_payload = {
                    "output_id": str(uuid.uuid4()),
                    "analysis_id": analysis_id,
                    "capture_id": capture_id,
                    "request": request_payload,
                    "bundle_dir": str(bundle_dir),
                    "notion_fields": notion_fields,
                }
                self.bus.publish(
                    topic=self.settings.topics.analysis_ready,
                    event_type="analysis.ready",
                    payload=ready_payload,
                    producer_name="analyzer",
                    key=analysis_id,
                    correlation_id=str(request_payload.get("request_id") or analysis_id),
                )
                self.bus.publish(
                    topic=self.settings.topics.output_requested,
                    event_type="output.requested",
                    payload=ready_payload,
                    producer_name="analyzer",
                    key=analysis_id,
                    correlation_id=str(request_payload.get("request_id") or analysis_id),
                )
                logger.info(format_kv("service.analyzer.ready", analysis_id=analysis_id, bundle_dir=bundle_dir))
            except Exception as exc:
                self.runtime_store.record_analysis_job(
                    analysis_id=analysis_id,
                    capture_id=capture_id,
                    bundle_dir=str(bundle_dir),
                    status="failed",
                    payload=payload,
                    last_error=str(exc),
                )
                logger.error(format_kv("service.analyzer.failed", analysis_id=analysis_id, error=str(exc)))
            self.bus.commit(self.consumer)
        return len(events)

    def run_forever(self) -> None:
        interval = self.settings.analyzer.poll_interval_seconds
        while True:
            try:
                processed = self.run_once()
                sleep_seconds = 1 if processed else interval
            except Exception as exc:  # pragma: no cover - service guard
                logger.error(format_kv("service.analyzer.crashed", error=str(exc)))
                sleep_seconds = interval
            time.sleep(sleep_seconds)

    def close(self) -> None:
        self.consumer.close()
