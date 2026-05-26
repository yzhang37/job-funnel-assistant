from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from job_search_assistant.task_manager.service import (
    TaskManagerQueryService,
    cache_ttl_state,
    parse_launchctl_list,
    sanitize_limit,
    _json_safe_row,
)


class TaskManagerServiceTests(unittest.TestCase):
    def test_parse_launchctl_list_filters_runtime_agents(self) -> None:
        output = """PID\tStatus\tLabel
123\t0\tcom.yzhang.jobfunnel.runtime.tracker
-\t-15\tcom.yzhang.jobfunnel.runtime.capture
999\t0\tcom.apple.other
"""

        agents = parse_launchctl_list(output)

        self.assertEqual(
            agents,
            [
                {
                    "pid": 123,
                    "last_exit_status": 0,
                    "label": "com.yzhang.jobfunnel.runtime.tracker",
                    "component": "tracker",
                },
                {
                    "pid": None,
                    "last_exit_status": -15,
                    "label": "com.yzhang.jobfunnel.runtime.capture",
                    "component": "capture",
                },
            ],
        )

    def test_cache_ttl_state(self) -> None:
        now = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)

        self.assertEqual(
            cache_ttl_state(
                fresh_until="2026-04-24T12:01:00Z",
                stale_until="2026-04-25T12:00:00Z",
                now=now,
            ),
            "fresh",
        )
        self.assertEqual(
            cache_ttl_state(
                fresh_until="2026-04-24T11:59:00Z",
                stale_until="2026-04-25T12:00:00Z",
                now=now,
            ),
            "stale",
        )
        self.assertEqual(
            cache_ttl_state(
                fresh_until="2026-04-23T12:00:00Z",
                stale_until="2026-04-24T11:59:00Z",
                now=now,
            ),
            "expired",
        )

    def test_sanitize_limit(self) -> None:
        self.assertEqual(sanitize_limit("10"), 10)
        self.assertEqual(sanitize_limit("bad", default=7), 7)
        self.assertEqual(sanitize_limit("9999", maximum=100), 100)
        self.assertEqual(sanitize_limit("-4"), 1)

    def test_json_safe_row_converts_mysql_decimal(self) -> None:
        row = _json_safe_row({"count": Decimal("12"), "ratio": Decimal("1.5")})

        self.assertEqual(row, {"count": 12, "ratio": 1.5})

    def test_set_worker_control_writes_worker_scoped_state(self) -> None:
        runtime_store = _FakeRuntimeStore()
        service = TaskManagerQueryService(repo_root=ROOT, runtime_store=runtime_store, node_id="node-a")

        result = service.set_worker_control(
            component_name="tracker",
            worker_id="worker-a",
            desired_state="drain-current",
            reason="unit test",
        )

        self.assertEqual(result["node_id"], "node-a")
        self.assertEqual(result["shutdown_mode"], "drain-current")
        self.assertEqual(runtime_store.controls[0]["component_name"], "tracker")
        self.assertEqual(runtime_store.controls[0]["worker_id"], "worker-a")


class _FakeRuntimeStore:
    def __init__(self) -> None:
        self.controls = []

    def set_worker_control(self, **kwargs) -> None:
        self.controls.append(kwargs)


if __name__ == "__main__":
    unittest.main()
