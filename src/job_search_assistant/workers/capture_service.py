from __future__ import annotations

import time
import uuid

from job_search_assistant.manual_flow import ManualIntakeRequest, build_manual_capture_bundle
from job_search_assistant.runtime import format_kv, get_logger
from job_search_assistant.runtime.browser_broker import BrowserExecutionBroker
from job_search_assistant.runtime.config import RuntimeSettings
from job_search_assistant.runtime.kafka_bus import KafkaEventBus
from job_search_assistant.runtime.mysql_runtime import MySQLRuntimeStore


logger = get_logger("service.capture")


class CaptureService:
    def __init__(
        self,
        *,
        settings: RuntimeSettings,
        bus: KafkaEventBus,
        runtime_store: MySQLRuntimeStore,
        browser_broker: BrowserExecutionBroker,
    ) -> None:
        self.settings = settings
        self.bus = bus
        self.runtime_store = runtime_store
        self.browser_broker = browser_broker
        self.consumer = self.bus.build_consumer(
            topics=[self.settings.topics.capture_requested],
            group_id=self.settings.capture.consumer_group,
        )

    def run_once(self) -> int:
        events = self.bus.poll(self.consumer, timeout_ms=5000, max_records=1)
        if not events:
            return 0
        for event in events:
            payload = dict(event.envelope.payload)
            request_id = str(payload["request_id"])
            capture_id = str(uuid.uuid4())
            request = ManualIntakeRequest(
                source_channel=str(payload.get("source_channel") or "other"),
                raw_text=str(payload.get("raw_text") or ""),
                job_url=payload.get("job_url"),
                jd_text=payload.get("jd_text"),
                company_name=payload.get("company_name"),
                position_name=payload.get("position_name"),
                capture_company_name=payload.get("capture_company_name"),
                hiring_company=payload.get("hiring_company"),
                vendor_company=payload.get("vendor_company"),
                location=payload.get("location"),
                employment_type=payload.get("employment_type"),
                recruiter_name=payload.get("recruiter_name"),
                recruiter_email=payload.get("recruiter_email"),
                recruiter_phone=payload.get("recruiter_phone"),
                input_kind=payload.get("input_kind"),
                end_client_disclosed=payload.get("end_client_disclosed"),
                should_enrich_company_profile=bool(payload.get("should_enrich_company_profile", True)),
                field_confidence=payload.get("field_confidence"),
                field_evidence=payload.get("field_evidence"),
                normalization_payload=payload.get("normalization_payload"),
                notes=payload.get("notes"),
            )
            self.runtime_store.record_capture_job(
                capture_id=capture_id,
                request_id=request_id,
                source_component=str(payload.get("source_component") or "unknown"),
                source_channel=request.source_channel,
                job_url=request.job_url,
                company_name=request.company_name,
                status="running",
                payload=payload,
            )
            try:
                bundle = build_manual_capture_bundle(
                    repo_root=self.settings.repo_root,
                    request=request,
                    output_root=self.settings.repo_root / str(self.settings.capture.extras.get("bundle_root")),
                    model=str(self.settings.capture.extras.get("model", "gpt-5.4")),
                    browser_broker=self.browser_broker,
                )
                self.runtime_store.record_capture_job(
                    capture_id=capture_id,
                    request_id=request_id,
                    source_component=str(payload.get("source_component") or "unknown"),
                    source_channel=request.source_channel,
                    job_url=request.job_url,
                    company_name=request.company_name,
                    status="succeeded",
                    payload=payload,
                    bundle_dir=str(bundle.bundle_dir),
                    job_title=str(bundle.job_posting_payload.get("title") or ""),
                    company_label=str(bundle.job_posting_payload.get("company") or ""),
                )
                analysis_payload = {
                    "analysis_id": str(uuid.uuid4()),
                    "capture_id": capture_id,
                    "request": payload,
                    "bundle_dir": str(bundle.bundle_dir),
                }
                self.bus.publish(
                    topic=self.settings.topics.capture_bundle_ready,
                    event_type="capture.bundle.ready",
                    payload={
                        "capture_id": capture_id,
                        "request_id": request_id,
                        "bundle_dir": str(bundle.bundle_dir),
                        "request": payload,
                    },
                    producer_name="capture",
                    key=capture_id,
                    correlation_id=request_id,
                )
                self.bus.publish(
                    topic=self.settings.topics.analysis_requested,
                    event_type="analysis.requested",
                    payload=analysis_payload,
                    producer_name="capture",
                    key=capture_id,
                    correlation_id=request_id,
                )
                logger.info(
                    format_kv(
                        "service.capture.bundle_ready",
                        request_id=request_id,
                        capture_id=capture_id,
                        bundle_dir=bundle.bundle_dir,
                    )
                )
            except Exception as exc:
                self.runtime_store.record_capture_job(
                    capture_id=capture_id,
                    request_id=request_id,
                    source_component=str(payload.get("source_component") or "unknown"),
                    source_channel=request.source_channel,
                    job_url=request.job_url,
                    company_name=request.company_name,
                    status="failed",
                    payload=payload,
                    last_error=str(exc),
                )
                logger.error(format_kv("service.capture.failed", request_id=request_id, error=str(exc)))
            self.bus.commit(self.consumer)
        return len(events)

    def run_forever(self) -> None:
        interval = self.settings.capture.poll_interval_seconds
        while True:
            try:
                processed = self.run_once()
                sleep_seconds = 1 if processed else interval
            except Exception as exc:  # pragma: no cover - service guard
                logger.error(format_kv("service.capture.crashed", error=str(exc)))
                sleep_seconds = interval
            time.sleep(sleep_seconds)

    def close(self) -> None:
        self.consumer.close()
