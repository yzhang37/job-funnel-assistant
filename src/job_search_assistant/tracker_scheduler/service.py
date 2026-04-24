from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .browser import BrowserDiscoverySession
from .frequency import DEFAULT_TRACKER_TIMEZONE, normalize_source_frequency, tracker_period_key
from .models import DueTracker, TrackerConfig, TrackerDiscoverySummary, TrackerRunState
from .storage.base import TrackerStateStore


class TrackerScheduler:
    def __init__(
        self,
        config: TrackerConfig,
        store: TrackerStateStore,
        *,
        schedule_timezone: str = DEFAULT_TRACKER_TIMEZONE,
        failure_retry_cooldown: timedelta = timedelta(hours=1),
    ) -> None:
        self.config = config
        self.store = store
        self.schedule_timezone = schedule_timezone
        self.failure_retry_cooldown = failure_retry_cooldown

    def list_due_trackers(self, now: datetime | None = None) -> list[DueTracker]:
        current_time = now or _utcnow()
        latest_runs = self.store.get_latest_run_states()
        due: list[DueTracker] = []

        for tracker in self.config.enabled_trackers():
            state = latest_runs.get(tracker.id)
            due_reason = _resolve_due_reason(
                tracker.source_frequency,
                state,
                current_time,
                schedule_timezone=self.schedule_timezone,
                failure_retry_cooldown=self.failure_retry_cooldown,
            )
            if due_reason is not None:
                due.append(
                    DueTracker(
                        tracker=tracker,
                        due_reason=due_reason,
                        last_run_state=state,
                    )
                )
        return due

    def record_discovery(
        self,
        *,
        tracker_id: str,
        job_urls: list[str],
        status: str = "success",
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> TrackerDiscoverySummary:
        tracker = self.config.get_tracker(tracker_id)
        run_started_at = started_at or _utcnow()
        run_finished_at = finished_at or _utcnow()
        return self.store.record_discovery_run(
            tracker_id=tracker.id,
            target_new_jobs=tracker.target_new_jobs,
            job_urls=job_urls,
            status=status,
            started_at=run_started_at,
            finished_at=run_finished_at,
        )

    def start_browser_discovery_session(self, tracker_id: str) -> BrowserDiscoverySession:
        tracker = self.config.get_tracker(tracker_id)
        return BrowserDiscoverySession(tracker=tracker, store=self.store)


def _resolve_due_reason(
    source_frequency: str,
    state: TrackerRunState | None,
    now: datetime,
    *,
    schedule_timezone: str = DEFAULT_TRACKER_TIMEZONE,
    failure_retry_cooldown: timedelta = timedelta(hours=1),
) -> str | None:
    frequency = normalize_source_frequency(source_frequency)
    if state is None:
        return "never_run"
    if state.last_status != "success":
        retry_at = state.last_finished_at + failure_retry_cooldown
        if now >= retry_at:
            return "retry_after_failure"
        return None

    last_period = tracker_period_key(frequency, state.last_finished_at, timezone_name=schedule_timezone)
    current_period = tracker_period_key(frequency, now, timezone_name=schedule_timezone)
    if current_period != last_period:
        return f"period_elapsed:{frequency}:{last_period}->{current_period}"
    return None


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)
