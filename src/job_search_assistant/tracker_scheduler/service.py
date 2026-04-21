from __future__ import annotations

from datetime import UTC, datetime

from .frequency import resolve_frequency_interval
from .models import DueTracker, TrackerConfig, TrackerDiscoverySummary, TrackerRunState
from .storage.base import TrackerStateStore


class TrackerScheduler:
    def __init__(self, config: TrackerConfig, store: TrackerStateStore) -> None:
        self.config = config
        self.store = store

    def list_due_trackers(self, now: datetime | None = None) -> list[DueTracker]:
        current_time = now or _utcnow()
        latest_runs = self.store.get_latest_run_states()
        due: list[DueTracker] = []

        for tracker in self.config.enabled_trackers():
            state = latest_runs.get(tracker.id)
            due_reason = _resolve_due_reason(tracker.source_frequency, state, current_time)
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


def _resolve_due_reason(
    source_frequency: str,
    state: TrackerRunState | None,
    now: datetime,
) -> str | None:
    if state is None:
        return "never_run"
    if state.last_status != "success":
        return "retry_after_failure"

    interval = resolve_frequency_interval(source_frequency)
    if now >= state.last_finished_at + interval:
        return f"interval_elapsed:{source_frequency}"
    return None


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)
