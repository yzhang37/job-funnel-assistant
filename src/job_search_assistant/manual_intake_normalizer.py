from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from job_search_assistant.analyzer.providers import CodexExecProvider, ProviderRequest
from job_search_assistant.runtime import format_kv, get_logger


logger = get_logger("manual_intake.normalizer")


NORMALIZATION_SCHEMA = {
    "name": "manual_intake_normalization",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "input_kind": {
                "type": "string",
                "enum": [
                    "job_url_only",
                    "job_url_with_context",
                    "structured_jd",
                    "recruiter_email",
                    "recruiter_message",
                    "informal_job_note",
                    "other",
                ],
            },
            "job_url": {"type": ["string", "null"]},
            "job_title": {"type": ["string", "null"]},
            "hiring_company": {"type": ["string", "null"]},
            "vendor_company": {"type": ["string", "null"]},
            "company_name_for_display": {"type": ["string", "null"]},
            "company_name_for_capture": {"type": ["string", "null"]},
            "should_enrich_company_profile": {"type": "boolean"},
            "location": {"type": ["string", "null"]},
            "employment_type": {"type": ["string", "null"]},
            "recruiter_name": {"type": ["string", "null"]},
            "recruiter_email": {"type": ["string", "null"]},
            "recruiter_phone": {"type": ["string", "null"]},
            "end_client_disclosed": {"type": ["boolean", "null"]},
            "notes": {"type": ["string", "null"]},
            "field_confidence": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "job_title": {"type": "string", "enum": ["high", "medium", "low", "none"]},
                    "hiring_company": {"type": "string", "enum": ["high", "medium", "low", "none"]},
                    "vendor_company": {"type": "string", "enum": ["high", "medium", "low", "none"]},
                    "location": {"type": "string", "enum": ["high", "medium", "low", "none"]},
                    "employment_type": {"type": "string", "enum": ["high", "medium", "low", "none"]},
                    "recruiter_name": {"type": "string", "enum": ["high", "medium", "low", "none"]},
                    "recruiter_email": {"type": "string", "enum": ["high", "medium", "low", "none"]},
                    "recruiter_phone": {"type": "string", "enum": ["high", "medium", "low", "none"]},
                },
                "required": [
                    "job_title",
                    "hiring_company",
                    "vendor_company",
                    "location",
                    "employment_type",
                    "recruiter_name",
                    "recruiter_email",
                    "recruiter_phone",
                ],
            },
            "field_evidence": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "job_title": {"type": "string"},
                    "hiring_company": {"type": "string"},
                    "vendor_company": {"type": "string"},
                    "location": {"type": "string"},
                    "employment_type": {"type": "string"},
                    "recruiter_name": {"type": "string"},
                    "recruiter_email": {"type": "string"},
                    "recruiter_phone": {"type": "string"},
                },
                "required": [
                    "job_title",
                    "hiring_company",
                    "vendor_company",
                    "location",
                    "employment_type",
                    "recruiter_name",
                    "recruiter_email",
                    "recruiter_phone",
                ],
            },
        },
        "required": [
            "input_kind",
            "job_url",
            "job_title",
            "hiring_company",
            "vendor_company",
            "company_name_for_display",
            "company_name_for_capture",
            "should_enrich_company_profile",
            "location",
            "employment_type",
            "recruiter_name",
            "recruiter_email",
            "recruiter_phone",
            "end_client_disclosed",
            "notes",
            "field_confidence",
            "field_evidence",
        ],
    },
}


NORMALIZER_PROMPT = """你是这个本地工作流里的 Manual Intake Normalizer。

你的任务是把用户贴进来的原始岗位文本、猎头邮件、转发消息、口语化说明，抽取成严格结构化字段。

规则：
1. 只根据给定文本做提取，不要脑补，不要查网，不要补全未披露的公司。
2. 如果是 recruiter / vendor 邮件：
   - `vendor_company` 填 recruiter/vendor 公司名
   - 如果 end client / hiring company 没有被明确披露，`hiring_company = null`
   - 这时 `company_name_for_display` 用 vendor_company
   - 这时 `company_name_for_capture = null`
   - `should_enrich_company_profile = false`
   - `end_client_disclosed = false`
3. 如果文本明确就是公司自身 JD 或明确披露 hiring company：
   - `hiring_company` 填真实公司
   - `company_name_for_display` 用 hiring_company
   - `company_name_for_capture` 用 hiring_company
   - `should_enrich_company_profile = true`
4. `job_title` 优先从显式字段中提取，例如 `Position:` / `Title:` / `Role:` / `岗位` / `后端jd` 等；不要把寒暄语句当标题。
5. `location` 保留原文措辞，例如 `New York (Onsite)`、`Sunnyvale,CA`、`Burlingame, CA (Hybrid, 3 days Work from Office)`。
6. `employment_type` 保留原文措辞，例如 `Full Time`、`Full-time`、`12+ month contract`。
7. `field_evidence` 必须给每个关键字段一个最短证据片段；没有证据就填空字符串。
8. `field_confidence` 必须保守：
   - 明确字段或签名区直接出现：`high`
   - 语义明确但不是标准字段：`medium`
   - 弱推断：`low`
   - 没有：`none`
9. 对 mixed Chinese / English 文本同样适用。
10. 如果 `detected_job_url` 已提供且文本里没有更好的岗位 URL，返回该 URL。

重点：
- 不要把 `Hope you are doing great.` 之类寒暄语当 job_title。
- 不要因为出现 `Reality Labs`、`MAANG Client`、`AI-powered travel planning startup` 这类描述就编造 hiring company。
- 如果 `Tanisha Systems Inc`、`Hays`、`Ursus, Inc.` 这类 vendor 明确出现，但客户未披露，就保持 hiring_company 为空。
""".strip()


@dataclass(frozen=True)
class NormalizedManualIntake:
    input_kind: str
    job_url: str | None
    job_title: str | None
    hiring_company: str | None
    vendor_company: str | None
    company_name_for_display: str | None
    company_name_for_capture: str | None
    should_enrich_company_profile: bool
    location: str | None
    employment_type: str | None
    recruiter_name: str | None
    recruiter_email: str | None
    recruiter_phone: str | None
    end_client_disclosed: bool | None
    notes: str | None
    field_confidence: dict[str, str]
    field_evidence: dict[str, str]
    raw_payload: dict[str, Any]


def normalize_manual_intake(
    *,
    repo_root: Path,
    raw_text: str,
    source_channel: str,
    detected_job_url: str | None,
    model: str = "gpt-5.4",
) -> NormalizedManualIntake:
    provider = CodexExecProvider()
    user_text = _build_user_text(
        raw_text=raw_text,
        source_channel=source_channel,
        detected_job_url=detected_job_url,
    )
    logger.info(
        format_kv(
            "manual_intake.normalize.start",
            source_channel=source_channel,
            detected_job_url=detected_job_url,
            model=model,
        )
    )
    payload = provider.run(
        ProviderRequest(
            repo_root=repo_root,
            developer_prompt=NORMALIZER_PROMPT,
            user_text=user_text,
            image_paths=[],
            schema=NORMALIZATION_SCHEMA,
            model=model,
            analysis_mode="normalize",
            enable_web_search=False,
        )
    )
    if detected_job_url and not payload.get("job_url"):
        payload["job_url"] = detected_job_url
    normalized = NormalizedManualIntake(
        input_kind=str(payload["input_kind"]),
        job_url=_optional_text(payload.get("job_url")),
        job_title=_optional_text(payload.get("job_title")),
        hiring_company=_optional_text(payload.get("hiring_company")),
        vendor_company=_optional_text(payload.get("vendor_company")),
        company_name_for_display=_optional_text(payload.get("company_name_for_display")),
        company_name_for_capture=_optional_text(payload.get("company_name_for_capture")),
        should_enrich_company_profile=bool(payload.get("should_enrich_company_profile")),
        location=_optional_text(payload.get("location")),
        employment_type=_optional_text(payload.get("employment_type")),
        recruiter_name=_optional_text(payload.get("recruiter_name")),
        recruiter_email=_optional_text(payload.get("recruiter_email")),
        recruiter_phone=_optional_text(payload.get("recruiter_phone")),
        end_client_disclosed=payload.get("end_client_disclosed"),
        notes=_optional_text(payload.get("notes")),
        field_confidence={str(key): str(value) for key, value in dict(payload["field_confidence"]).items()},
        field_evidence={str(key): str(value) for key, value in dict(payload["field_evidence"]).items()},
        raw_payload=dict(payload),
    )
    logger.info(
        format_kv(
            "manual_intake.normalize.done",
            input_kind=normalized.input_kind,
            job_title=normalized.job_title,
            display_company=normalized.company_name_for_display,
            capture_company=normalized.company_name_for_capture,
            location=normalized.location,
            employment_type=normalized.employment_type,
        )
    )
    return normalized


def _build_user_text(*, raw_text: str, source_channel: str, detected_job_url: str | None) -> str:
    return f"""## Source Channel
{source_channel}

## Detected Job URL
{detected_job_url or ""}

## Raw Input
{raw_text}
""".strip()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
