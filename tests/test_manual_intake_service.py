from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from job_search_assistant.manual_flow import ManualIntakeRequest
from job_search_assistant.workers.manual_intake_service import ManualIntakeService


class ManualIntakeServiceTests(unittest.TestCase):
    def test_service_enqueues_structured_fields(self) -> None:
        settings = SimpleNamespace(
            repo_root=ROOT,
            manual_intake=SimpleNamespace(extras={"model": "gpt-5.4", "send_ack": True}),
            topics=SimpleNamespace(capture_requested="capture.requested"),
        )
        bus = _FakeBus()
        runtime_store = _FakeRuntimeStore()
        telegram = _FakeTelegram(runtime_store)
        service = ManualIntakeService(
            settings=settings,
            bus=bus,
            runtime_store=runtime_store,
            telegram_client=telegram,
        )

        normalized_request = ManualIntakeRequest(
            source_channel="telegram",
            raw_text="vendor recruiter email",
            job_url=None,
            jd_text="Position: Principal GenAI Engineer – Knowledge Graph & Semantic Systems",
            company_name="Tanisha Systems Inc",
            position_name="Principal GenAI Engineer – Knowledge Graph & Semantic Systems",
            capture_company_name=None,
            hiring_company=None,
            vendor_company="Tanisha Systems Inc",
            location="New York (Onsite)",
            employment_type="Full Time",
            recruiter_name="Prince Kumar",
            recruiter_email="prince@tanishasystems.com",
            recruiter_phone="(732) 375 2152",
            input_kind="recruiter_message",
            end_client_disclosed=False,
            should_enrich_company_profile=False,
            field_confidence={"job_title": "high"},
            field_evidence={"job_title": "Position: Principal GenAI Engineer – Knowledge Graph & Semantic Systems"},
            normalization_payload={"input_kind": "recruiter_message"},
            notes="vendor-only message",
        )

        with patch(
            "job_search_assistant.workers.manual_intake_service.parse_manual_intake_text",
            return_value=normalized_request,
        ), patch(
            "job_search_assistant.workers.manual_intake_service.looks_like_job_input",
            return_value=True,
        ), patch(
            "job_search_assistant.workers.manual_intake_service.normalize_manual_intake_request",
            return_value=normalized_request,
        ):
            processed = service.run_once()

        self.assertEqual(processed, 1)
        self.assertEqual(runtime_store.offsets["telegram:last_update_id"], 999000201)
        self.assertEqual(len(bus.published), 1)
        payload = bus.published[0]["payload"]
        self.assertEqual(payload["company_name"], "Tanisha Systems Inc")
        self.assertEqual(payload["position_name"], "Principal GenAI Engineer – Knowledge Graph & Semantic Systems")
        self.assertEqual(payload["vendor_company"], "Tanisha Systems Inc")
        self.assertEqual(payload["location"], "New York (Onsite)")
        self.assertEqual(payload["employment_type"], "Full Time")
        self.assertFalse(payload["should_enrich_company_profile"])
        self.assertEqual(runtime_store.acks, [(8285341224, "已接收，开始处理。")])


class _FakeMessage:
    update_id = 999000201
    chat_id = 8285341224
    message_id = 1
    text = "ignored"
    from_user_id = 8285341224


class _FakeBus:
    def __init__(self) -> None:
        self.published = []

    def publish(self, **kwargs) -> None:
        self.published.append(kwargs)


class _FakeRuntimeStore:
    def __init__(self) -> None:
        self.offsets = {}
        self.events = []
        self.acks = []

    def get_offset(self, key: str, *, default: int = 0) -> int:
        return self.offsets.get(key, default)

    def set_offset(self, key: str, value: int) -> None:
        self.offsets[key] = value

    def record_manual_intake_event(self, **kwargs) -> None:
        self.events.append(kwargs)


class _FakeTelegram:
    def __init__(self, runtime_store: _FakeRuntimeStore) -> None:
        self.runtime_store = runtime_store

    def get_updates(self, offset=None):
        return [_FakeMessage()]

    def is_owner_message(self, message) -> bool:
        return True

    def send_message(self, text: str, chat_id=None) -> None:
        self.runtime_store.acks.append((chat_id, text))


if __name__ == "__main__":
    unittest.main()
