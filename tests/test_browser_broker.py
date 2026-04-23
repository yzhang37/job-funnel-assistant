from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from job_search_assistant.runtime.browser_broker import CodexComputerUseBroker
from job_search_assistant.runtime.config import BrowserBrokerSettings


class BrowserBrokerPreflightTests(unittest.TestCase):
    def test_preflight_writes_marker_on_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = _settings(Path(temp_dir))
            broker = CodexComputerUseBroker(settings=settings, runtime_store=None)
            with patch.object(broker, "_ensure_codex_available", return_value="/tmp/codex"), patch.object(
                broker, "_check_chrome_window_control", return_value=None
            ), patch.object(
                broker,
                "_check_codex_computer_use",
                return_value={
                    "status": "ok",
                    "frontmost_app": "Google Chrome",
                    "observed_url": "https://example.com/",
                    "observed_title": "Example Domain",
                },
            ):
                result = broker.preflight(model="gpt-5.4")

            self.assertFalse(result.cached)
            self.assertTrue(result.marker_path.exists())
            payload = json.loads(result.marker_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["model"], "gpt-5.4")
            self.assertEqual(payload["observed_title"], "Example Domain")

    def test_preflight_uses_cached_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = _settings(Path(temp_dir))
            broker = CodexComputerUseBroker(settings=settings, runtime_store=None)
            marker_path = broker._preflight_marker_path()
            marker_path.write_text(
                json.dumps(
                    {
                        "node_id": settings.node_id,
                        "lane_name": settings.lane_name,
                        "model": "gpt-5.4",
                        "checked_at_utc": "2026-04-23T00:00:00Z",
                        "observed_app": "Google Chrome",
                        "observed_url": "https://example.com/",
                        "observed_title": "Example Domain",
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(broker, "_ensure_codex_available") as codex_mock, patch.object(
                broker, "_check_chrome_window_control"
            ) as chrome_mock, patch.object(broker, "_check_codex_computer_use") as probe_mock:
                result = broker.preflight(model="gpt-5.4")

            self.assertTrue(result.cached)
            codex_mock.assert_not_called()
            chrome_mock.assert_not_called()
            probe_mock.assert_not_called()

    def test_preflight_skips_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = BrowserBrokerSettings(
                node_id="test-node",
                lane_name="default",
                lock_dir=Path(temp_dir),
                acquire_timeout_seconds=60,
                poll_interval_seconds=1,
                preflight_required=False,
                preflight_codex_timeout_seconds=30,
            )
            broker = CodexComputerUseBroker(settings=settings, runtime_store=None)
            with patch.object(broker, "_ensure_codex_available") as codex_mock:
                result = broker.preflight(model="gpt-5.4")

            self.assertFalse(result.cached)
            codex_mock.assert_not_called()


def _settings(lock_dir: Path) -> BrowserBrokerSettings:
    return BrowserBrokerSettings(
        node_id="test-node",
        lane_name="default",
        lock_dir=lock_dir,
        acquire_timeout_seconds=60,
        poll_interval_seconds=1,
        preflight_required=True,
        preflight_codex_timeout_seconds=30,
    )


if __name__ == "__main__":
    unittest.main()
