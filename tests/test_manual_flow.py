from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from job_search_assistant.analyzer.runner import RunResult
from job_search_assistant.manual_flow import (
    ManualIntakeRequest,
    build_manual_capture_bundle,
    build_notion_payload_fields,
    build_telegram_short_message,
    normalize_manual_intake_request,
    parse_manual_intake_text,
    run_analysis_for_capture_bundle,
)
from job_search_assistant.manual_intake_normalizer import NormalizedManualIntake


class ManualFlowTests(unittest.TestCase):
    def test_normalize_manual_intake_request_uses_structured_fields(self) -> None:
        request = parse_manual_intake_text(
            """
            Hope you are doing great.

            Position: Principal GenAI Engineer – Knowledge Graph & Semantic Systems
            Location: New York (Onsite)
            Hire Type: Full Time

            Tanisha Systems Inc
            Email: prince@tanishasystems.com
            """,
            source_channel="telegram",
        )
        normalized = NormalizedManualIntake(
            input_kind="recruiter_message",
            job_url=None,
            job_title="Principal GenAI Engineer – Knowledge Graph & Semantic Systems",
            hiring_company=None,
            vendor_company="Tanisha Systems Inc",
            company_name_for_display="Tanisha Systems Inc",
            company_name_for_capture=None,
            should_enrich_company_profile=False,
            location="New York (Onsite)",
            employment_type="Full Time",
            recruiter_name="Prince Kumar",
            recruiter_email="prince@tanishasystems.com",
            recruiter_phone="(732) 375 2152",
            end_client_disclosed=False,
            notes="vendor-only message",
            field_confidence={
                "job_title": "high",
                "hiring_company": "none",
                "vendor_company": "high",
                "location": "high",
                "employment_type": "high",
                "recruiter_name": "medium",
                "recruiter_email": "high",
                "recruiter_phone": "high",
            },
            field_evidence={
                "job_title": "Position: Principal GenAI Engineer – Knowledge Graph & Semantic Systems",
                "hiring_company": "",
                "vendor_company": "Tanisha Systems Inc",
                "location": "Location: New York (Onsite)",
                "employment_type": "Hire Type: Full Time",
                "recruiter_name": "Prince Kumar",
                "recruiter_email": "prince@tanishasystems.com",
                "recruiter_phone": "(732) 375 2152",
            },
            raw_payload={},
        )

        with patch("job_search_assistant.manual_flow.normalize_manual_intake", return_value=normalized):
            result = normalize_manual_intake_request(repo_root=ROOT, request=request)

        self.assertEqual(result.company_name, "Tanisha Systems Inc")
        self.assertEqual(result.position_name, "Principal GenAI Engineer – Knowledge Graph & Semantic Systems")
        self.assertIsNone(result.capture_company_name)
        self.assertEqual(result.vendor_company, "Tanisha Systems Inc")
        self.assertEqual(result.location, "New York (Onsite)")
        self.assertEqual(result.employment_type, "Full Time")
        self.assertFalse(result.should_enrich_company_profile)
        self.assertFalse(result.end_client_disclosed)

    def test_url_only_normalization_forces_company_enrichment(self) -> None:
        request = parse_manual_intake_text(
            "https://www.linkedin.com/jobs/view/4389287838",
            source_channel="telegram",
        )
        normalized = NormalizedManualIntake(
            input_kind="job_url_only",
            job_url="https://www.linkedin.com/jobs/view/4389287838",
            job_title=None,
            hiring_company=None,
            vendor_company=None,
            company_name_for_display=None,
            company_name_for_capture=None,
            should_enrich_company_profile=False,
            location=None,
            employment_type=None,
            recruiter_name=None,
            recruiter_email=None,
            recruiter_phone=None,
            end_client_disclosed=None,
            notes=None,
            field_confidence={
                "job_title": "none",
                "hiring_company": "none",
                "vendor_company": "none",
                "location": "none",
                "employment_type": "none",
                "recruiter_name": "none",
                "recruiter_email": "none",
                "recruiter_phone": "none",
            },
            field_evidence={
                "job_title": "",
                "hiring_company": "",
                "vendor_company": "",
                "location": "",
                "employment_type": "",
                "recruiter_name": "",
                "recruiter_email": "",
                "recruiter_phone": "",
            },
            raw_payload={},
        )

        with patch("job_search_assistant.manual_flow.normalize_manual_intake", return_value=normalized):
            result = normalize_manual_intake_request(repo_root=ROOT, request=request)

        self.assertTrue(result.should_enrich_company_profile)

    def test_build_manual_capture_bundle_vendor_only_preserves_fields(self) -> None:
        request = ManualIntakeRequest(
            source_channel="telegram",
            raw_text="vendor recruiter email",
            job_url=None,
            jd_text="Position: Principal GenAI Engineer – Knowledge Graph & Semantic Systems",
            company_name="Tanisha Systems Inc",
            position_name="Principal GenAI Engineer – Knowledge Graph & Semantic Systems",
            vendor_company="Tanisha Systems Inc",
            location="New York (Onsite)",
            employment_type="Full Time",
            input_kind="recruiter_message",
            end_client_disclosed=False,
            should_enrich_company_profile=False,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = build_manual_capture_bundle(
                repo_root=ROOT,
                request=request,
                output_root=Path(temp_dir),
            )

            self.assertEqual(bundle.job_posting_payload["title"], "Principal GenAI Engineer – Knowledge Graph & Semantic Systems")
            self.assertEqual(bundle.job_posting_payload["company"], "Tanisha Systems Inc")
            self.assertEqual(bundle.job_posting_payload["location"], "New York (Onsite)")
            self.assertEqual(bundle.job_posting_payload["employment_type"], "Full Time")
            self.assertIsNone(bundle.company_profile_payload)
            self.assertIn("vendor_company=Tanisha Systems Inc", bundle.job_posting_payload["notes"])

    def test_recruiter_pipeline_end_to_end_uses_normalized_title(self) -> None:
        request = ManualIntakeRequest(
            source_channel="telegram",
            raw_text="Hope you are doing great.",
            job_url=None,
            jd_text="Position: Principal GenAI Engineer – Knowledge Graph & Semantic Systems",
            company_name="Tanisha Systems Inc",
            position_name="Principal GenAI Engineer – Knowledge Graph & Semantic Systems",
            vendor_company="Tanisha Systems Inc",
            location="New York (Onsite)",
            employment_type="Full Time",
            input_kind="recruiter_message",
            end_client_disclosed=False,
            should_enrich_company_profile=False,
        )

        payload = _sample_analysis_payload()
        result = RunResult(payload=payload, markdown="# 完整分析报告\n\n- 这是一份测试报告")

        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = build_manual_capture_bundle(
                repo_root=ROOT,
                request=request,
                output_root=Path(temp_dir),
            )
            with patch("job_search_assistant.manual_flow.run_analysis", return_value=result):
                analysis = run_analysis_for_capture_bundle(
                    repo_root=ROOT,
                    request=request,
                    capture_bundle=bundle,
                    profile_stack_path="profiles/default_stack.json",
                    provider_name="mock",
                )
            notion_fields = build_notion_payload_fields(
                request=request,
                capture_bundle=bundle,
                analysis_payload=analysis.payload,
            )
            telegram_message = build_telegram_short_message(
                analysis_payload=analysis.payload,
                notion_url="https://www.notion.so/example",
                company_name=request.company_name,
                position_name=request.position_name,
                job_url=request.job_url,
            )

            self.assertIn("Tanisha Systems Inc｜Principal GenAI Engineer – Knowledge Graph & Semantic Systems", notion_fields["title"])
            self.assertTrue((bundle.bundle_dir / "analysis_report.md").exists())
            self.assertIn("[主攻] Tanisha Systems Inc - Principal GenAI Engineer – Knowledge Graph & Semantic Systems", telegram_message)
            self.assertNotIn("Hope you are doing great.", telegram_message)


def _sample_analysis_payload() -> dict:
    return {
        "run_metadata": {
            "generated_at": "2026-04-23T00:00:00Z",
        },
        "report": {
            "executive_verdict": {
                "funnel_category": "主攻",
                "one_sentence": "这条岗位值得进入主攻 funnel。",
                "reasons": [
                    "岗位方向和画像高度重合。",
                    "地点与用工类型明确。",
                    "招聘方信息清晰。",
                ],
            },
            "candidate_fit_analysis": {
                "overall_fit_score": 82,
            },
            "risk_unknowns": {
                "unknowns": ["终端客户未披露。"],
            },
            "recommended_actions": [
                "先确认 end client 与 EOR。",
            ],
        },
    }


if __name__ == "__main__":
    unittest.main()
