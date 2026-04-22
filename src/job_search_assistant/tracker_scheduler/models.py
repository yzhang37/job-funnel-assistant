from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class TrackerDefinition:
    id: str
    label: str
    url: str
    source_frequency: str
    target_new_jobs: int = 30
    enabled: bool = True

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "url": self.url,
            "source_frequency": self.source_frequency,
            "target_new_jobs": self.target_new_jobs,
            "enabled": self.enabled,
        }


@dataclass(frozen=True)
class TrackerDiscoveryBatch:
    tracker_id: str
    source_platform: str
    submitted_count: int
    canonical_count: int
    duplicate_input_count: int
    canonical_job_urls: list[str] = field(default_factory=list)
    new_job_urls: list[str] = field(default_factory=list)
    existing_job_urls: list[str] = field(default_factory=list)
    run_duplicate_job_urls: list[str] = field(default_factory=list)
    total_new_job_urls: list[str] = field(default_factory=list)
    remaining_target_new_jobs: int = 0
    source_exhausted: bool = False
    discovery_scope: str = "main_results"
    ignored_sections: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, object]:
        return {
            "tracker_id": self.tracker_id,
            "source_platform": self.source_platform,
            "submitted_count": self.submitted_count,
            "canonical_count": self.canonical_count,
            "duplicate_input_count": self.duplicate_input_count,
            "canonical_job_urls": list(self.canonical_job_urls),
            "new_job_urls": list(self.new_job_urls),
            "existing_job_urls": list(self.existing_job_urls),
            "run_duplicate_job_urls": list(self.run_duplicate_job_urls),
            "total_new_job_urls": list(self.total_new_job_urls),
            "remaining_target_new_jobs": self.remaining_target_new_jobs,
            "source_exhausted": self.source_exhausted,
            "discovery_scope": self.discovery_scope,
            "ignored_sections": list(self.ignored_sections),
        }


@dataclass(frozen=True)
class TrackerConfig:
    version: int
    trackers: list[TrackerDefinition] = field(default_factory=list)

    def enabled_trackers(self) -> list[TrackerDefinition]:
        return [tracker for tracker in self.trackers if tracker.enabled]

    def get_tracker(self, tracker_id: str) -> TrackerDefinition:
        for tracker in self.trackers:
            if tracker.id == tracker_id:
                return tracker
        raise KeyError(f"Unknown tracker id: {tracker_id}")


@dataclass(frozen=True)
class TrackerRunState:
    tracker_id: str
    last_started_at: datetime
    last_finished_at: datetime
    last_status: str
    target_new_jobs: int
    submitted_count: int
    unique_submitted_count: int
    tracker_new_count: int
    global_new_count: int

    def to_payload(self) -> dict[str, object]:
        return {
            "tracker_id": self.tracker_id,
            "last_started_at": self.last_started_at.isoformat(),
            "last_finished_at": self.last_finished_at.isoformat(),
            "last_status": self.last_status,
            "target_new_jobs": self.target_new_jobs,
            "submitted_count": self.submitted_count,
            "unique_submitted_count": self.unique_submitted_count,
            "tracker_new_count": self.tracker_new_count,
            "global_new_count": self.global_new_count,
        }


@dataclass(frozen=True)
class DueTracker:
    tracker: TrackerDefinition
    due_reason: str
    last_run_state: TrackerRunState | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "tracker": self.tracker.to_payload(),
            "due_reason": self.due_reason,
        }
        if self.last_run_state is not None:
            payload["last_run_state"] = self.last_run_state.to_payload()
        return payload


@dataclass(frozen=True)
class TrackerDiscoverySummary:
    tracker_id: str
    status: str
    target_new_jobs: int
    submitted_count: int
    unique_submitted_count: int
    tracker_new_count: int
    tracker_repeat_count: int
    global_new_count: int
    global_existing_count: int
    run_started_at: datetime
    run_finished_at: datetime
    run_id: int | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "tracker_id": self.tracker_id,
            "status": self.status,
            "target_new_jobs": self.target_new_jobs,
            "submitted_count": self.submitted_count,
            "unique_submitted_count": self.unique_submitted_count,
            "tracker_new_count": self.tracker_new_count,
            "tracker_repeat_count": self.tracker_repeat_count,
            "global_new_count": self.global_new_count,
            "global_existing_count": self.global_existing_count,
            "run_started_at": self.run_started_at.isoformat(),
            "run_finished_at": self.run_finished_at.isoformat(),
            "run_id": self.run_id,
        }
