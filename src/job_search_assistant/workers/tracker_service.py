from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import os
import time
import uuid

from job_search_assistant.runtime import format_kv, get_logger
from job_search_assistant.runtime.browser_broker import BrowserExecutionBroker
from job_search_assistant.runtime.config import RuntimeSettings
from job_search_assistant.runtime.kafka_bus import KafkaEventBus
from job_search_assistant.runtime.mysql_runtime import MySQLRuntimeStore
from job_search_assistant.tracker_scheduler import BrowserDiscoverySession, DueTracker, TrackerConfig, TrackerScheduler
from job_search_assistant.tracker_scheduler.frequency import DEFAULT_TRACKER_TIMEZONE
from job_search_assistant.tracker_scheduler.storage import MySQLTrackerStateStore


logger = get_logger("service.tracker")


@dataclass(frozen=True)
class TrackerAdmissionPolicy:
    max_admissions_per_cycle: int
    max_pending_discovery_requests: int
    discovery_request_ttl: timedelta
    max_capture_requests_per_tracker_run: int


class TrackerService:
    def __init__(
        self,
        *,
        settings: RuntimeSettings,
        bus: KafkaEventBus,
        runtime_store: MySQLRuntimeStore,
        tracker_config: TrackerConfig,
        browser_broker: BrowserExecutionBroker,
        worker_id: str | None = None,
    ) -> None:
        self.settings = settings
        self.bus = bus
        self.runtime_store = runtime_store
        self.browser_broker = browser_broker
        self.store = MySQLTrackerStateStore(runtime_store)
        self.worker_id = worker_id or str(self.settings.tracker.extras.get("worker_id") or os.getpid())
        schedule_timezone = str(self.settings.tracker.extras.get("schedule_timezone") or DEFAULT_TRACKER_TIMEZONE)
        failure_retry_cooldown = timedelta(
            minutes=_int_extra(self.settings.tracker.extras, "failure_retry_cooldown_minutes", 60)
        )
        self.admission_policy = TrackerAdmissionPolicy(
            max_admissions_per_cycle=_int_extra(self.settings.tracker.extras, "max_admissions_per_cycle", 5),
            max_pending_discovery_requests=_int_extra(
                self.settings.tracker.extras,
                "max_pending_discovery_requests",
                20,
            ),
            discovery_request_ttl=timedelta(
                hours=_int_extra(self.settings.tracker.extras, "discovery_request_ttl_hours", 24)
            ),
            max_capture_requests_per_tracker_run=_int_extra(
                self.settings.tracker.extras,
                "max_capture_requests_per_tracker_run",
                30,
            ),
        )
        self.scheduler = TrackerScheduler(
            tracker_config,
            self.store,
            schedule_timezone=schedule_timezone,
            failure_retry_cooldown=failure_retry_cooldown,
        )
        self.consumer = self.bus.build_consumer(
            topics=[self.settings.topics.tracker_discovery_requested],
            group_id=self.settings.tracker.consumer_group,
        )

    def run_once(self) -> int:
        if self._should_stop_before_new_work():
            logger.info(
                format_kv(
                    "service.tracker.drain_current.idle_exit",
                    node_id=self.settings.browser_broker.node_id,
                    worker_id=self.worker_id,
                )
            )
            return 0
        self._schedule_due_trackers()
        if self._should_stop_before_new_work():
            return 0
        events = self.bus.poll(self.consumer, timeout_ms=5000, max_records=1)
        if not events:
            return 0
        for event in events:
            payload = dict(event.envelope.payload)
            tracker_id = str(payload["tracker_id"])
            request_id = str(payload["request_id"])
            self.runtime_store.mark_tracker_discovery_request_running(request_id=request_id)
            try:
                tracker = self.scheduler.config.get_tracker(tracker_id)
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
                downstream_job_urls = _limit_capture_requests(
                    batch.new_job_urls,
                    max_items=self.admission_policy.max_capture_requests_per_tracker_run,
                )
                for job_url in downstream_job_urls:
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
                self.runtime_store.mark_tracker_discovery_request_finished(
                    request_id=request_id,
                    status="succeeded",
                )
                logger.info(
                    format_kv(
                        "service.tracker.discovery_done",
                        tracker_id=tracker.id,
                        request_id=request_id,
                        new_job_count=len(batch.new_job_urls),
                        capture_enqueued_count=len(downstream_job_urls),
                        capture_skipped_count=len(batch.new_job_urls) - len(downstream_job_urls),
                    )
                )
            except Exception as exc:
                try:
                    self.scheduler.record_discovery(
                        tracker_id=tracker_id,
                        job_urls=[],
                        status="failed",
                    )
                except Exception as record_exc:
                    logger.warning(
                        format_kv(
                            "service.tracker.failure_record_skipped",
                            tracker_id=tracker_id,
                            request_id=request_id,
                            error=str(record_exc),
                        )
                    )
                self.runtime_store.mark_tracker_discovery_request_finished(
                    request_id=request_id,
                    status="failed",
                    last_error=str(exc),
                )
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
        while not self._should_stop_before_new_work():
            try:
                processed = self.run_once()
                sleep_seconds = 1 if processed else interval
            except Exception as exc:  # pragma: no cover - service guard
                logger.error(format_kv("service.tracker.crashed", error=str(exc)))
                sleep_seconds = interval
            if self._should_stop_before_new_work():
                break
            time.sleep(sleep_seconds)
        logger.info(
            format_kv(
                "service.tracker.stopped",
                node_id=self.settings.browser_broker.node_id,
                worker_id=self.worker_id,
            )
        )

    def _schedule_due_trackers(self) -> None:
        if self._should_stop_before_new_work():
            return
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
            expired_count = self.runtime_store.cleanup_stale_tracker_discovery_requests()
            due_trackers = self.scheduler.list_due_trackers()
            active_tracker_ids = self.runtime_store.get_active_tracker_discovery_tracker_ids()
            pending_count = self.runtime_store.count_tracker_discovery_requests()
            capacity = max(self.admission_policy.max_pending_discovery_requests - pending_count, 0)
            capacity = min(capacity, self.admission_policy.max_admissions_per_cycle)
            if capacity <= 0:
                logger.info(
                    format_kv(
                        "service.tracker.admission_throttled",
                        due_count=len(due_trackers),
                        active_tracker_count=len(active_tracker_ids),
                        pending_count=pending_count,
                        max_pending=self.admission_policy.max_pending_discovery_requests,
                        expired_count=expired_count,
                    )
                )
                return
            last_admitted_at = self.runtime_store.get_tracker_last_admitted_at()
            admitted = select_due_trackers_for_admission(
                due_trackers,
                active_tracker_ids=active_tracker_ids,
                last_admitted_at=last_admitted_at,
                max_count=capacity,
            )
            now = datetime.now(UTC).replace(microsecond=0)
            for priority, due in enumerate(admitted, start=100):
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
                self.runtime_store.record_tracker_discovery_request(
                    request_id=request_id,
                    tracker_id=due.tracker.id,
                    status="queued",
                    priority=priority,
                    due_reason=due.due_reason,
                    admitted_at=now,
                    stale_after=now + self.admission_policy.discovery_request_ttl,
                    payload=payload,
                )
                try:
                    self.bus.publish(
                        topic=self.settings.topics.tracker_discovery_requested,
                        event_type="tracker.discovery.requested",
                        payload=payload,
                        producer_name="tracker",
                        key=due.tracker.id,
                        correlation_id=request_id,
                    )
                except Exception as exc:
                    self.runtime_store.mark_tracker_discovery_request_finished(
                        request_id=request_id,
                        status="failed",
                        last_error=f"publish failed: {exc}",
                    )
                    raise
                logger.info(
                    format_kv(
                        "service.tracker.enqueued",
                        tracker_id=due.tracker.id,
                        request_id=request_id,
                        due_reason=due.due_reason,
                        priority=priority,
                    )
                )
        finally:
            self.runtime_store.release_runtime_lease(lane_key=lane_key, holder_id=lease_holder)

    def _should_stop_before_new_work(self) -> bool:
        control = self.runtime_store.get_worker_control(
            component_name="tracker",
            node_id=self.settings.browser_broker.node_id,
            worker_id=self.worker_id,
        )
        if not control:
            return False
        desired_state = str(control.get("desired_state") or "").replace("_", "-")
        shutdown_mode = str(control.get("shutdown_mode") or "").replace("_", "-")
        return desired_state in {"drain-current", "stopped"} or shutdown_mode == "drain-current"

    def close(self) -> None:
        self.consumer.close()


def select_due_trackers_for_admission(
    due_trackers: list[DueTracker],
    *,
    active_tracker_ids: set[str],
    last_admitted_at: dict[str, datetime],
    max_count: int,
) -> list[DueTracker]:
    if max_count <= 0:
        return []
    candidates = [
        (index, due)
        for index, due in enumerate(due_trackers)
        if due.tracker.id not in active_tracker_ids
    ]

    def sort_key(item: tuple[int, DueTracker]) -> tuple[int, datetime, datetime, int, str]:
        index, due = item
        last_admitted = last_admitted_at.get(due.tracker.id)
        last_finished = due.last_run_state.last_finished_at if due.last_run_state else datetime.min.replace(tzinfo=UTC)
        return (
            0 if last_admitted is None else 1,
            last_admitted or datetime.min.replace(tzinfo=UTC),
            last_finished,
            index,
            due.tracker.id,
        )

    candidates.sort(key=sort_key)
    return [due for _, due in candidates[:max_count]]


def _limit_capture_requests(job_urls: list[str], *, max_items: int) -> list[str]:
    if max_items <= 0:
        return []
    return list(job_urls[:max_items])


def _int_extra(extras: dict[str, object], name: str, default: int) -> int:
    value = extras.get(name, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Tracker setting {name!r} must be an integer.") from exc
    if parsed < 0:
        raise ValueError(f"Tracker setting {name!r} must be >= 0.")
    return parsed
