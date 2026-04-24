from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from job_search_assistant.tracker_scheduler import DueTracker, TrackerDefinition, TrackerRunState
from job_search_assistant.workers.tracker_service import TrackerService, select_due_trackers_for_admission


class TrackerAdmissionTests(unittest.TestCase):
    def test_admission_skips_active_and_prefers_never_admitted_trackers(self) -> None:
        due = [
            _due("active"),
            _due("old"),
            _due("never"),
            _due("recent"),
        ]
        last_admitted = {
            "old": datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
            "recent": datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
        }

        admitted = select_due_trackers_for_admission(
            due,
            active_tracker_ids={"active"},
            last_admitted_at=last_admitted,
            max_count=2,
        )

        self.assertEqual([item.tracker.id for item in admitted], ["never", "old"])

    def test_admission_capacity_zero_returns_no_work(self) -> None:
        admitted = select_due_trackers_for_admission(
            [_due("a")],
            active_tracker_ids=set(),
            last_admitted_at={},
            max_count=0,
        )

        self.assertEqual(admitted, [])


class TrackerGracefulShutdownTests(unittest.TestCase):
    def test_drain_current_worker_does_not_accept_new_work_when_idle(self) -> None:
        settings = _settings()
        bus = _FakeBus()
        runtime_store = _DrainRuntimeStore()
        service = TrackerService(
            settings=settings,
            bus=bus,
            runtime_store=runtime_store,
            tracker_config=SimpleNamespace(trackers=[]),
            browser_broker=SimpleNamespace(),
            worker_id="worker-a",
        )

        processed = service.run_once()

        self.assertEqual(processed, 0)
        self.assertEqual(bus.poll_count, 0)
        self.assertEqual(runtime_store.lease_attempts, 0)


def _due(tracker_id: str) -> DueTracker:
    tracker = TrackerDefinition(
        id=tracker_id,
        label=tracker_id,
        url=f"https://example.com/{tracker_id}",
        source_frequency="daily",
    )
    finished = datetime(2026, 4, 20, 12, 0, tzinfo=UTC)
    return DueTracker(
        tracker=tracker,
        due_reason="period_elapsed:daily",
        last_run_state=TrackerRunState(
            tracker_id=tracker_id,
            last_started_at=finished - timedelta(minutes=10),
            last_finished_at=finished,
            last_status="success",
            target_new_jobs=30,
            submitted_count=0,
            unique_submitted_count=0,
            tracker_new_count=0,
            global_new_count=0,
        ),
    )


def _settings():
    return SimpleNamespace(
        browser_broker=SimpleNamespace(node_id="test-node"),
        topics=SimpleNamespace(
            tracker_discovery_requested="tracker.discovery.requested",
            tracker_links_discovered="tracker.links.discovered",
            capture_requested="capture.requested",
        ),
        tracker=SimpleNamespace(
            consumer_group="tracker-test",
            poll_interval_seconds=1,
            extras={
                "model": "gpt-5.4",
                "worker_id": "worker-a",
                "schedule_timezone": "America/Los_Angeles",
                "failure_retry_cooldown_minutes": 60,
                "max_admissions_per_cycle": 1,
                "max_pending_discovery_requests": 1,
                "discovery_request_ttl_hours": 1,
                "max_capture_requests_per_tracker_run": 1,
            },
        ),
    )


class _FakeConsumer:
    def close(self) -> None:
        return None


class _FakeBus:
    def __init__(self) -> None:
        self.poll_count = 0

    def build_consumer(self, **kwargs) -> _FakeConsumer:
        return _FakeConsumer()

    def poll(self, *args, **kwargs) -> list[object]:
        self.poll_count += 1
        return []


class _DrainRuntimeStore:
    def __init__(self) -> None:
        self.lease_attempts = 0

    def get_worker_control(self, **kwargs):
        return {"desired_state": "drain-current", "shutdown_mode": "drain-current"}

    def acquire_runtime_lease(self, **kwargs) -> bool:
        self.lease_attempts += 1
        return False


if __name__ == "__main__":
    unittest.main()
