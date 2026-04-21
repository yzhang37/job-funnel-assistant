from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ..models import TrackerDiscoverySummary, TrackerRunState


class TrackerStateStore(Protocol):
    def get_latest_run_states(self) -> dict[str, TrackerRunState]:
        """Return the latest known run state for each tracker id."""

    def record_discovery_run(
        self,
        *,
        tracker_id: str,
        target_new_jobs: int,
        job_urls: list[str],
        status: str,
        started_at: datetime,
        finished_at: datetime,
    ) -> TrackerDiscoverySummary:
        """Persist one tracker run and any discovered job URLs."""
