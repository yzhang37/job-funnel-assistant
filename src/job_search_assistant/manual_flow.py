from __future__ import annotations

import json
import re
import time
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from job_search_assistant.analyzer.runner import RunResult, run_analysis, save_outputs
from job_search_assistant.capture import (
    CompanyProfileContent,
    JobPostingContent,
    JobSection,
    build_job_capture_bundle,
    codex_live_capture_job_url,
    detect_source_platform,
    enrich_company_profile_for_manual_capture,
    load_company_profile_cache,
    load_job_posting_cache,
    render_company_profile_markdown,
    render_jd_markdown,
)
from job_search_assistant.manual_intake_normalizer import normalize_manual_intake
from job_search_assistant.runtime import format_kv, get_logger

if TYPE_CHECKING:
    from job_search_assistant.runtime.browser_broker import BrowserExecutionBroker


URL_PATTERN = re.compile(r"https?://\S+")
logger = get_logger("manual_flow")


@dataclass
class ManualIntakeRequest:
    source_channel: str
    raw_text: str
    job_url: str | None
    jd_text: str | None
    company_name: str | None = None
    position_name: str | None = None
    capture_company_name: str | None = None
    hiring_company: str | None = None
    vendor_company: str | None = None
    location: str | None = None
    employment_type: str | None = None
    recruiter_name: str | None = None
    recruiter_email: str | None = None
    recruiter_phone: str | None = None
    input_kind: str | None = None
    end_client_disclosed: bool | None = None
    should_enrich_company_profile: bool = True
    field_confidence: dict[str, str] | None = None
    field_evidence: dict[str, str] | None = None
    normalization_payload: dict[str, Any] | None = None
    notes: str | None = None


@dataclass
class CaptureBundleResult:
    bundle_dir: Path
    manifest: dict[str, Any]
    jd_markdown: str
    job_posting_payload: dict[str, Any]
    company_profile_markdown: str | None
    company_profile_payload: dict[str, Any] | None


def looks_like_job_input(request: ManualIntakeRequest) -> bool:
    if request.job_url:
        return True
    if request.job_url and request.jd_text:
        return True
    if request.jd_text:
        text = request.jd_text.strip()
        lowered = text.lower()
        keyword_hits = sum(
            1
            for keyword in (
                "responsibilities",
                "qualifications",
                "requirements",
                "experience",
                "location",
                "salary",
                "engineer",
                "backend",
                "platform",
                "full-time",
                "job",
            )
            if keyword in lowered
        )
        return len(text) >= 180 or text.count("\n") >= 4 or keyword_hits >= 2
    return False


def parse_manual_intake_text(raw_text: str, *, source_channel: str) -> ManualIntakeRequest:
    text = raw_text.strip()
    urls = URL_PATTERN.findall(text)
    job_url = urls[0] if urls else None
    jd_text = text
    if job_url:
        jd_text = text.replace(job_url, "", 1).strip()
    if not jd_text:
        jd_text = None
    return ManualIntakeRequest(
        source_channel=source_channel,
        raw_text=text,
        job_url=job_url,
        jd_text=jd_text,
    )


def normalize_manual_intake_request(
    *,
    repo_root: Path,
    request: ManualIntakeRequest,
    model: str = "gpt-5.4",
) -> ManualIntakeRequest:
    normalized = normalize_manual_intake(
        repo_root=repo_root,
        raw_text=request.raw_text,
        source_channel=request.source_channel,
        detected_job_url=request.job_url,
        model=model,
    )
    job_url = normalized.job_url or request.job_url
    company_name = normalized.company_name_for_display or request.company_name
    capture_company_name = normalized.company_name_for_capture
    should_enrich_company_profile = bool(normalized.should_enrich_company_profile)
    if request.job_url:
        should_enrich_company_profile = True
    return ManualIntakeRequest(
        source_channel=request.source_channel,
        raw_text=request.raw_text,
        job_url=job_url,
        jd_text=request.jd_text,
        company_name=company_name,
        position_name=normalized.job_title,
        capture_company_name=capture_company_name,
        hiring_company=normalized.hiring_company,
        vendor_company=normalized.vendor_company,
        location=normalized.location,
        employment_type=normalized.employment_type,
        recruiter_name=normalized.recruiter_name,
        recruiter_email=normalized.recruiter_email,
        recruiter_phone=normalized.recruiter_phone,
        input_kind=normalized.input_kind,
        end_client_disclosed=normalized.end_client_disclosed,
        should_enrich_company_profile=should_enrich_company_profile,
        field_confidence=normalized.field_confidence,
        field_evidence=normalized.field_evidence,
        normalization_payload=normalized.raw_payload,
        notes=_merge_manual_intake_notes(request.notes, normalized.notes),
    )


def build_manual_capture_bundle(
    *,
    repo_root: Path,
    request: ManualIntakeRequest,
    output_root: Path,
    model: str = "gpt-5.4",
    browser_broker: BrowserExecutionBroker | None = None,
) -> CaptureBundleResult:
    started = time.monotonic()
    input_kind = "job_url" if request.job_url and not request.jd_text else "job_url_and_jd_text" if request.job_url and request.jd_text else "jd_text"
    logger.info(
        format_kv(
            "capture.bundle.start",
            source_channel=request.source_channel,
            input_kind=input_kind,
            job_url=request.job_url,
            model=model,
        )
    )
    if request.jd_text:
        title = request.position_name or _infer_title_from_url(request.job_url) or "未命名岗位"
        display_company_name = request.company_name
        capture_company_name = request.capture_company_name or (
            request.company_name if request.should_enrich_company_profile else None
        )
        source_platform = detect_source_platform(request.job_url) if request.job_url else _platform_from_channel(request.source_channel)

        posting = JobPostingContent(
            title=title,
            company=display_company_name,
            location=request.location,
            employment_type=request.employment_type,
            source_platform=source_platform,
            source_url=request.job_url,
            sections=[JobSection(heading="Raw JD Input", paragraphs=_paragraphs_from_text(request.jd_text))],
            notes=_posting_notes(request),
        )

        company_profile = None
        company_profile_payload = None
        company_profile_markdown = None
        if capture_company_name:
            company_profile, cache_freshness = load_company_profile_cache(
                repo_root=repo_root,
                company_name=capture_company_name,
                source_url=request.job_url,
            )
            if company_profile is not None:
                logger.info(
                    format_kv(
                        "capture.bundle.company_profile.cache_hit",
                        company_name=capture_company_name,
                        freshness=cache_freshness,
                        source_channel=request.source_channel,
                    )
                )
            else:
                company_profile = enrich_company_profile_for_manual_capture(
                    company_name=capture_company_name,
                    job_url=request.job_url,
                    jd_text=request.jd_text,
                    source_platform=source_platform,
                    source_label=request.source_channel,
                    model=model,
                    browser_broker=browser_broker,
                )
            if company_profile is not None:
                company_profile_payload = asdict(company_profile)
                company_profile_markdown = render_company_profile_markdown(company_profile)
    elif request.job_url:
        posting, job_cache_freshness = load_job_posting_cache(
            repo_root=repo_root,
            job_url=request.job_url,
        )
        company_profile = None
        company_profile_payload = None
        company_profile_markdown = None
        if posting is not None:
            logger.info(
                format_kv(
                    "capture.bundle.job_posting.cache_hit",
                    job_url=request.job_url,
                    freshness=job_cache_freshness,
                    source_channel=request.source_channel,
                )
            )
            if request.company_name and not posting.company:
                posting.company = request.company_name
            if request.location and not posting.location:
                posting.location = request.location
            if request.employment_type and not posting.employment_type:
                posting.employment_type = request.employment_type
            posting.notes = _merge_posting_notes(posting.notes, _posting_notes(request))
            company_name = request.capture_company_name or posting.company
            if company_name and request.should_enrich_company_profile:
                company_profile, company_cache_freshness = load_company_profile_cache(
                    repo_root=repo_root,
                    company_name=company_name,
                    source_url=request.job_url,
                )
                if company_profile is not None:
                    logger.info(
                        format_kv(
                            "capture.bundle.company_profile.cache_hit",
                            company_name=company_name,
                            freshness=company_cache_freshness,
                            source_channel=request.source_channel,
                        )
                    )
                else:
                    company_profile = enrich_company_profile_for_manual_capture(
                        company_name=company_name,
                        job_url=request.job_url,
                        jd_text=render_jd_markdown(posting),
                        source_platform=posting.source_platform,
                        source_label=request.source_channel,
                        model=model,
                        browser_broker=browser_broker,
                    )
            if company_profile is not None:
                company_profile_payload = asdict(company_profile)
                company_profile_markdown = render_company_profile_markdown(company_profile)
        else:
            if browser_broker is None:
                captured = codex_live_capture_job_url(job_url=request.job_url, model=model)
            else:
                captured = browser_broker.capture_job_url(job_url=request.job_url, model=model)
            job_payload = dict(captured["job_posting"])
            if request.position_name and not job_payload.get("title"):
                job_payload["title"] = request.position_name
            if request.company_name and not job_payload.get("company"):
                job_payload["company"] = request.company_name
            if request.location and not job_payload.get("location"):
                job_payload["location"] = request.location
            if request.employment_type and not job_payload.get("employment_type"):
                job_payload["employment_type"] = request.employment_type
            job_payload["notes"] = _merge_posting_notes(job_payload.get("notes", []), _posting_notes(request))
            posting = JobPostingContent.from_dict(job_payload)

            company_payload = dict(captured.get("company_profile") or {})
            if company_payload:
                if request.capture_company_name and not company_payload.get("company_name"):
                    company_payload["company_name"] = request.capture_company_name
                if not company_payload.get("source_url"):
                    company_payload["source_url"] = request.job_url
                if not company_payload.get("source_platform"):
                    company_payload["source_platform"] = posting.source_platform or detect_source_platform(request.job_url)
                company_profile = CompanyProfileContent.from_dict(company_payload)
                company_profile_payload = asdict(company_profile)
                company_profile_markdown = render_company_profile_markdown(company_profile)
    else:
        raise ValueError("Manual capture requires either jd_text or job_url.")

    run_stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = _slugify((posting.company or request.company_name or posting.title))
    bundle_dir = output_root / f"{run_stamp}-{slug}"
    manifest_path = build_job_capture_bundle(
        output_dir=bundle_dir,
        posting=posting,
        company_profile=company_profile,
        repo_root=repo_root,
        source_inputs={
            "input_kind": "manual_intake",
            "source_channel": request.source_channel,
        },
        notes=[f"source_channel={request.source_channel}"],
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        format_kv(
            "capture.bundle.done",
            bundle_dir=bundle_dir,
            company=posting.company,
            title=posting.title,
            source_platform=posting.source_platform,
            duration_ms=duration_ms,
        )
    )
    return CaptureBundleResult(
        bundle_dir=bundle_dir,
        manifest=manifest,
        jd_markdown=render_jd_markdown(posting),
        job_posting_payload=asdict(posting),
        company_profile_markdown=company_profile_markdown,
        company_profile_payload=company_profile_payload,
    )


def run_analysis_for_capture_bundle(
    *,
    repo_root: Path,
    request: ManualIntakeRequest,
    capture_bundle: CaptureBundleResult,
    profile_stack_path: str | Path,
    provider_name: str = "auto",
    model: str = "gpt-5.4",
    analysis_mode: str = "full",
    enable_web_search: bool = False,
) -> RunResult:
    started = time.monotonic()
    resolved_jd_text = request.jd_text or capture_bundle.jd_markdown
    resolved_company_name = (
        request.company_name
        or capture_bundle.job_posting_payload.get("company")
        or (capture_bundle.company_profile_payload or {}).get("company_name")
    )
    result = run_analysis(
        repo_root=repo_root,
        jd_text=resolved_jd_text,
        profile_stack_path=profile_stack_path,
        provider_name=provider_name,
        model=model,
        analysis_mode=analysis_mode,
        enable_web_search=enable_web_search,
        company_name=resolved_company_name,
        guessed_title=request.position_name or str(capture_bundle.job_posting_payload.get("title") or "") or None,
        job_url=request.job_url,
        notes=_analysis_notes(request),
        company_profile_payload=capture_bundle.company_profile_payload,
        bundle_manifest=capture_bundle.manifest,
    )
    save_outputs(
        result,
        capture_bundle.bundle_dir / "analysis_report.md",
        capture_bundle.bundle_dir / "analysis_report.json",
    )
    report = result.payload["report"]
    verdict = report["executive_verdict"]
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        format_kv(
            "analysis.bundle.done",
            bundle_dir=capture_bundle.bundle_dir,
            decision=verdict.get("funnel_category"),
            company=resolved_company_name,
            duration_ms=duration_ms,
        )
    )
    return result


def load_capture_bundle_result(bundle_dir: Path) -> CaptureBundleResult:
    bundle_dir = Path(bundle_dir)
    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    job_posting_payload = json.loads((bundle_dir / "job_posting.json").read_text(encoding="utf-8"))
    jd_markdown = (bundle_dir / "jd.md").read_text(encoding="utf-8")
    company_profile_payload = None
    company_profile_markdown = None
    company_json_path = bundle_dir / "company_profile.json"
    company_md_path = bundle_dir / "company_profile.md"
    if company_json_path.exists():
        company_profile_payload = json.loads(company_json_path.read_text(encoding="utf-8"))
    if company_md_path.exists():
        company_profile_markdown = company_md_path.read_text(encoding="utf-8")
    return CaptureBundleResult(
        bundle_dir=bundle_dir,
        manifest=manifest,
        jd_markdown=jd_markdown,
        job_posting_payload=job_posting_payload,
        company_profile_markdown=company_profile_markdown,
        company_profile_payload=company_profile_payload,
    )


def build_telegram_short_message(
    *,
    analysis_payload: dict[str, Any],
    notion_url: str,
    company_name: str | None,
    position_name: str | None,
    job_url: str | None,
) -> str:
    report = analysis_payload["report"]
    verdict = report["executive_verdict"]
    risk_items = report["risk_unknowns"]["unknowns"]
    actions = report["recommended_actions"]

    header = f"[{verdict['funnel_category']}] {(company_name or '未知公司')} - {(position_name or '未知岗位')}"
    lines = [header, "", "结论", verdict["one_sentence"], "", "原因"]
    for item in verdict["reasons"][:3]:
        lines.append(f"- {item}")
    if risk_items:
        lines.extend(["", "风险", f"- {risk_items[0]}"])
    if actions:
        lines.extend(["", "下一步", f"- {actions[0]}"])
    lines.extend(["", "链接"])
    if job_url:
        lines.append(f"JD: {job_url}")
    lines.append(f"Notion: {notion_url}")
    return "\n".join(lines).strip()


def build_notion_payload_fields(
    *,
    request: ManualIntakeRequest,
    capture_bundle: CaptureBundleResult,
    analysis_payload: dict[str, Any],
) -> dict[str, Any]:
    report = analysis_payload["report"]
    verdict = report["executive_verdict"]
    fit = report["candidate_fit_analysis"]
    risks = report["risk_unknowns"]
    actions = report["recommended_actions"]
    company_name = request.company_name
    if not company_name:
        company_name = (
            capture_bundle.job_posting_payload.get("company")
            or (capture_bundle.company_profile_payload or {}).get("company_name")
        )
    title = request.position_name or str(capture_bundle.job_posting_payload.get("title") or "未命名岗位")
    company_summary = None
    if capture_bundle.company_profile_markdown:
        company_summary = capture_bundle.company_profile_markdown.splitlines()[0].replace("# ", "", 1)
    return {
        "title": f"{company_name or '未知公司'}｜{title}｜{datetime.now().strftime('%Y-%m-%d')}",
        "company_name": company_name,
        "position_name": title,
        "job_url": request.job_url,
        "source_platform": detect_source_platform(request.job_url) if request.job_url else _platform_from_channel(request.source_channel),
        "input_method": _input_method_label(request.source_channel),
        "decision": verdict["funnel_category"],
        "fit_score": fit.get("overall_fit_score"),
        "one_sentence": verdict["one_sentence"],
        "core_reasons": verdict["reasons"],
        "key_risk": risks["unknowns"][0] if risks["unknowns"] else None,
        "recommended_action": actions[0] if actions else None,
        "company_profile_summary": company_summary,
        "analyzed_at": analysis_payload["run_metadata"]["generated_at"],
        "bundle_path": str(capture_bundle.bundle_dir),
        "report_markdown": (capture_bundle.bundle_dir / "analysis_report.md").read_text(encoding="utf-8"),
        "jd_markdown": capture_bundle.jd_markdown,
        "company_profile_markdown": capture_bundle.company_profile_markdown,
    }


def _paragraphs_from_text(text: str) -> list[str]:
    return [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]


def _posting_notes(request: ManualIntakeRequest) -> list[str]:
    notes = [f"source_channel={request.source_channel}"]
    if request.input_kind:
        notes.append(f"input_kind={request.input_kind}")
    if request.hiring_company:
        notes.append(f"hiring_company={request.hiring_company}")
    if request.vendor_company:
        notes.append(f"vendor_company={request.vendor_company}")
    if request.recruiter_name:
        notes.append(f"recruiter_name={request.recruiter_name}")
    if request.recruiter_email:
        notes.append(f"recruiter_email={request.recruiter_email}")
    if request.recruiter_phone:
        notes.append(f"recruiter_phone={request.recruiter_phone}")
    if request.end_client_disclosed is not None:
        notes.append(f"end_client_disclosed={str(request.end_client_disclosed).lower()}")
    return notes


def _merge_posting_notes(existing: list[str] | None, additions: list[str]) -> list[str]:
    merged: list[str] = []
    for item in list(existing or []) + list(additions):
        text = str(item).strip()
        if text and text not in merged:
            merged.append(text)
    return merged


def _merge_manual_intake_notes(existing: str | None, normalized: str | None) -> str | None:
    parts = [part.strip() for part in (existing, normalized) if part and part.strip()]
    if not parts:
        return None
    return "\n".join(parts)


def _analysis_notes(request: ManualIntakeRequest) -> str | None:
    lines = [line for line in (request.notes or "").splitlines() if line.strip()]
    if request.input_kind:
        lines.append(f"normalized_input_kind: {request.input_kind}")
    if request.company_name:
        lines.append(f"display_company_name: {request.company_name}")
    if request.hiring_company:
        lines.append(f"hiring_company: {request.hiring_company}")
    if request.vendor_company:
        lines.append(f"vendor_company: {request.vendor_company}")
    if request.location:
        lines.append(f"location: {request.location}")
    if request.employment_type:
        lines.append(f"employment_type: {request.employment_type}")
    if request.recruiter_name:
        lines.append(f"recruiter_name: {request.recruiter_name}")
    if request.recruiter_email:
        lines.append(f"recruiter_email: {request.recruiter_email}")
    if request.recruiter_phone:
        lines.append(f"recruiter_phone: {request.recruiter_phone}")
    if request.end_client_disclosed is not None:
        lines.append(f"end_client_disclosed: {str(request.end_client_disclosed).lower()}")
    if request.field_evidence:
        evidence_lines = [f"{key}={value}" for key, value in request.field_evidence.items() if value]
        if evidence_lines:
            lines.append("field_evidence: " + " | ".join(evidence_lines))
    if not lines:
        return None
    return "\n".join(lines)


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "-", value).strip("-").lower()
    return normalized[:80] or "manual-intake"


def _infer_title_from_url(job_url: str | None) -> str | None:
    if not job_url:
        return None
    path = urlparse(job_url).path.strip("/")
    return path.split("/")[-1] if path else None


def _platform_from_channel(source_channel: str) -> str:
    if source_channel == "telegram":
        return "Telegram"
    if source_channel == "email_forward":
        return "Email"
    return "Manual"


def _input_method_label(source_channel: str) -> str:
    mapping = {
        "telegram": "Telegram",
        "email_forward": "邮件转发",
        "manual_cli": "手动文本",
    }
    return mapping.get(source_channel, "其他")
