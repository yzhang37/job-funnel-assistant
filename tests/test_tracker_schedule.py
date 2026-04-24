from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from job_search_assistant.tracker_scheduler import TrackerConfig, TrackerDefinition, TrackerRunState, TrackerScheduler
from job_search_assistant.tracker_scheduler.frequency import normalize_source_frequency, tracker_period_key


class TrackerScheduleTests(unittest.TestCase):
    def test_daily_uses_seattle_calendar_day_not_rolling_24_hours(self) -> None:
        store = _Store(
            {
                "daily": _state(
                    "daily",
                    finished_at=datetime(2026, 4, 23, 6, 30, tzinfo=UTC),
                )
            }
        )
        scheduler = TrackerScheduler(_config("daily", "daily"), store, schedule_timezone="America/Los_Angeles")

        due = scheduler.list_due_trackers(now=datetime(2026, 4, 23, 8, 30, tzinfo=UTC))

        self.assertEqual([item.tracker.id for item in due], ["daily"])
        self.assertIn("period_elapsed:daily", due[0].due_reason)

    def test_daily_same_seattle_day_is_not_due(self) -> None:
        store = _Store(
            {
                "daily": _state(
                    "daily",
                    finished_at=datetime(2026, 4, 23, 16, 0, tzinfo=UTC),
                )
            }
        )
        scheduler = TrackerScheduler(_config("daily", "daily"), store, schedule_timezone="America/Los_Angeles")

        due = scheduler.list_due_trackers(now=datetime(2026, 4, 23, 20, 0, tzinfo=UTC))

        self.assertEqual(due, [])

    def test_calendar_frequencies_have_stable_period_keys(self) -> None:
        moment = datetime(2026, 4, 23, 16, 0, tzinfo=UTC)

        self.assertEqual(tracker_period_key("weekly", moment), "weekly:2026-W17")
        self.assertEqual(tracker_period_key("monthly", moment), "monthly:2026-04")
        self.assertEqual(tracker_period_key("bimonthly", moment), "bimonthly:2026-B2")
        self.assertEqual(tracker_period_key("quarterly", moment), "quarterly:2026-Q2")

    def test_new_supported_frequencies_are_due_after_period_changes(self) -> None:
        trackers = [
            TrackerDefinition(id="weekly", label="weekly", url="https://example.com/w", source_frequency="weekly"),
            TrackerDefinition(id="biweekly", label="biweekly", url="https://example.com/b", source_frequency="biweekly"),
            TrackerDefinition(id="monthly", label="monthly", url="https://example.com/m", source_frequency="monthly"),
            TrackerDefinition(id="bimonthly", label="bimonthly", url="https://example.com/bm", source_frequency="bimonthly"),
            TrackerDefinition(id="quarterly", label="quarterly", url="https://example.com/q", source_frequency="quarterly"),
        ]
        store = _Store(
            {
                tracker.id: _state(tracker.id, finished_at=datetime(2026, 1, 15, 18, 0, tzinfo=UTC))
                for tracker in trackers
            }
        )
        scheduler = TrackerScheduler(TrackerConfig(version=1, trackers=trackers), store)

        due = scheduler.list_due_trackers(now=datetime(2026, 4, 23, 18, 0, tzinfo=UTC))

        self.assertEqual({item.tracker.id for item in due}, {"weekly", "biweekly", "monthly", "bimonthly", "quarterly"})

    def test_failed_tracker_respects_retry_cooldown(self) -> None:
        store = _Store(
            {
                "daily": _state(
                    "daily",
                    status="failed",
                    finished_at=datetime(2026, 4, 23, 18, 0, tzinfo=UTC),
                )
            }
        )
        scheduler = TrackerScheduler(
            _config("daily", "daily"),
            store,
            failure_retry_cooldown=timedelta(hours=2),
        )

        self.assertEqual(scheduler.list_due_trackers(now=datetime(2026, 4, 23, 19, 0, tzinfo=UTC)), [])
        self.assertEqual(
            [item.tracker.id for item in scheduler.list_due_trackers(now=datetime(2026, 4, 23, 20, 1, tzinfo=UTC))],
            ["daily"],
        )

    def test_frequency_aliases_normalize_to_bimonthly(self) -> None:
        self.assertEqual(normalize_source_frequency("2 monthly"), "bimonthly")
        self.assertEqual(normalize_source_frequency("every-2-months"), "bimonthly")


def _config(tracker_id: str, frequency: str) -> TrackerConfig:
    return TrackerConfig(
        version=1,
        trackers=[
            TrackerDefinition(
                id=tracker_id,
                label=tracker_id,
                url=f"https://example.com/{tracker_id}",
                source_frequency=frequency,
            )
        ],
    )


def _state(
    tracker_id: str,
    *,
    status: str = "success",
    finished_at: datetime,
) -> TrackerRunState:
    return TrackerRunState(
        tracker_id=tracker_id,
        last_started_at=finished_at - timedelta(minutes=10),
        last_finished_at=finished_at,
        last_status=status,
        target_new_jobs=30,
        submitted_count=0,
        unique_submitted_count=0,
        tracker_new_count=0,
        global_new_count=0,
    )


class _Store:
    def __init__(self, states: dict[str, TrackerRunState]) -> None:
        self.states = states

    def get_latest_run_states(self) -> dict[str, TrackerRunState]:
        return self.states

    def get_existing_job_urls(self, job_urls: list[str]) -> set[str]:
        return set()

    def record_discovery_run(self, **kwargs):
        raise NotImplementedError


if __name__ == "__main__":
    unittest.main()
