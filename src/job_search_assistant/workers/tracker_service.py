from __future__ import annotations

import time
import uuid

from job_search_assistant.runtime import format_kv, get_logger
from job_search_assistant.runtime.browser_broker import BrowserExecutionBroker
from job_search_assistant.runtime.config import RuntimeSettings
from job_search_assistant.runtime.kafka_bus import KafkaEventBus
from job_search_assistant.runtime.mysql_runtime import MySQLRuntimeStore
from job_search_assistant.tracker_scheduler import BrowserDiscoverySession, TrackerConfig, TrackerScheduler
from job_search_assistant.tracker_scheduler.storage import MySQLTrackerStateStore


logger = get_logger("service.tracker")


class TrackerService:
    def __init__(
        self,
        *,
        settings: RuntimeSettings,
        bus: KafkaEventBus,
        runtime_store: MySQLRuntimeStore,
        tracker_config: TrackerConfig,
        browser_broker: BrowserExecutionBroker,
    ) -> None:
        self.settings = settings
        self.bus = bus
        self.runtime_store = runtime_store
        self.browser_broker = browser_broker
        self.store = MySQLTrackerStateStore(runtime_store)
        self.scheduler = TrackerScheduler(tracker_config, self.store)
        self.consumer = self.bus.build_consumer(
            topics=[self.settings.topics.tracker_discovery_requested],
            group_id=self.settings.tracker.consumer_group,
        )

    def run_once(self) -> int:
        self._schedule_due_trackers()
        events = self.bus.poll(self.consumer, timeout_ms=5000, max_records=1)
        if not events:
            return 0
        for event in events:
            payload = dict(event.envelope.payload)
            tracker_id = str(payload["tracker_id"])
            request_id = str(payload["request_id"])
            tracker = self.scheduler.config.get_tracker(tracker_id)
            try:
                raw_payload = self.browser_broker.discover_tracker_urls(
                    tracker=tracker,
                    model=str(payload.get("model") or self.settings.tracker.extras.get("model", "gpt-5.4")),
                )
                session = BrowserDiscoverySession(tracker=tracker, store=self.store)
                batch = session.ingest_raw_job_urls(
                    [str(item).strip() for item in raw_payload.get("raw_job_urls", []) if str(item).strip()],
                    source_exhausted=bool(raw_payload.get("source_exhausted", False)),
                )
                summary = self.scheduler.record_discovery(
                    tracker_id=tracker.id,
                    job_urls=batch.canonical_job_urls,
                    status="success",
                )
                links_payload = {
                    "request_id": request_id,
                    "tracker_id": tracker.id,
                    "job_urls": batch.new_job_urls,
                    "source_exhausted": batch.source_exhausted,
                    "summary": summary.to_payload(),
                    "notes": list(raw_payload.get("notes", [])),
                }
                self.bus.publish(
                    topic=self.settings.topics.tracker_links_discovered,
                    event_type="tracker.links.discovered",
                    payload=links_payload,
                    producer_name="tracker",
                    key=tracker.id,
                    correlation_id=request_id,
                )
                for job_url in batch.new_job_urls:
                    capture_payload = {
                        "request_id": str(uuid.uuid4()),
                        "source_component": "tracker",
                        "source_channel": "tracker",
                        "raw_text": job_url,
                        "job_url": job_url,
                        "jd_text": None,
                        "company_name": None,
                        "notes": f"tracker_id={tracker.id}",
                        "send_telegram_reply": False,
                    }
                    self.bus.publish(
                        topic=self.settings.topics.capture_requested,
                        event_type="capture.requested",
                        payload=capture_payload,
                        producer_name="tracker",
                        key=job_url,
                        correlation_id=request_id,
                    )
                logger.info(
                    format_kv(
                        "service.tracker.discovery_done",
                        tracker_id=tracker.id,
                        request_id=request_id,
                        new_job_count=len(batch.new_job_urls),
                    )
                )
            except Exception as exc:
                logger.error(
                    format_kv(
                        "service.tracker.discovery_failed",
                        tracker_id=tracker_id,
                        request_id=request_id,
                        error=str(exc),
                    )
                )
            self.bus.commit(self.consumer)
        return len(events)

    def run_forever(self) -> None:
        interval = self.settings.tracker.poll_interval_seconds
        while True:
            try:
                processed = self.run_once()
                sleep_seconds = 1 if processed else interval
            except Exception as exc:  # pragma: no cover - service guard
                logger.error(format_kv("service.tracker.crashed", error=str(exc)))
                sleep_seconds = interval
            time.sleep(sleep_seconds)

    def _schedule_due_trackers(self) -> None:
        lease_holder = f"{self.settings.browser_broker.node_id}-tracker-scheduler"
        lane_key = "service:tracker_scheduler"
        if not self.runtime_store.acquire_runtime_lease(
            lane_key=lane_key,
            holder_id=lease_holder,
            node_id=self.settings.browser_broker.node_id,
            task_kind="tracker_scheduler",
            task_ref="due_scan",
            ttl_seconds=self.settings.tracker.poll_interval_seconds * 2,
        ):
            return
        try:
            due_trackers = self.scheduler.list_due_trackers()
            for due in due_trackers:
                request_id = str(uuid.uuid4())
                payload = {
                    "request_id": request_id,
                    "tracker_id": due.tracker.id,
                    "tracker_label": due.tracker.label,
                    "tracker_url": due.tracker.url,
                    "target_new_jobs": due.tracker.target_new_jobs,
                    "model": str(self.settings.tracker.extras.get("model", "gpt-5.4")),
                    "due_reason": due.due_reason,
                }
                self.bus.publish(
                    topic=self.settings.topics.tracker_discovery_requested,
                    event_type="tracker.discovery.requested",
                    payload=payload,
                    producer_name="tracker",
                    key=due.tracker.id,
                    correlation_id=request_id,
                )
                logger.info(
                    format_kv(
                        "service.tracker.enqueued",
                        tracker_id=due.tracker.id,
                        request_id=request_id,
                        due_reason=due.due_reason,
                    )
                )
        finally:
            self.runtime_store.release_runtime_lease(lane_key=lane_key, holder_id=lease_holder)

    def close(self) -> None:
        self.consumer.close()
