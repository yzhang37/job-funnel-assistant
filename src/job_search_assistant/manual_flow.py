from __future__ import annotations

import json
import re
import time
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from job_search_assistant.analyzer.job_packet import infer_company_name, infer_title
from job_search_assistant.analyzer.runner import RunResult, run_analysis, save_outputs
from job_search_assistant.capture import (
    CompanyProfileContent,
    JobPostingContent,
    JobSection,
    build_job_capture_bundle,
    codex_live_capture_job_url,
    detect_source_platform,
    enrich_company_profile_for_manual_capture,
    render_company_profile_markdown,
    render_jd_markdown,
)
from job_search_assistant.runtime import format_kv, get_logger


URL_PATTERN = re.compile(r"https?://\S+")
logger = get_logger("manual_flow")


@dataclass
class ManualIntakeRequest:
    source_channel: str
    raw_text: str
    job_url: str | None
    jd_text: str | None
    company_name: str | None = None
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


def build_manual_capture_bundle(
    *,
    repo_root: Path,
    request: ManualIntakeRequest,
    output_root: Path,
    model: str = "gpt-5.4",
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
        title = infer_title(request.jd_text) or _infer_title_from_url(request.job_url) or "未命名岗位"
        company_name = request.company_name or infer_company_name(request.jd_text)
        source_platform = detect_source_platform(request.job_url) if request.job_url else _platform_from_channel(request.source_channel)

        posting = JobPostingContent(
            title=title,
            company=company_name,
            source_platform=source_platform,
            source_url=request.job_url,
            sections=[JobSection(heading="Raw JD Input", paragraphs=_paragraphs_from_text(request.jd_text))],
            notes=[f"source_channel={request.source_channel}"],
        )

        company_profile = None
        company_profile_payload = None
        company_profile_markdown = None
        if company_name:
            company_profile = enrich_company_profile_for_manual_capture(
                company_name=company_name,
                job_url=request.job_url,
                jd_text=request.jd_text,
                source_platform=source_platform,
                source_label=request.source_channel,
                model=model,
            )
            if company_profile is not None:
                company_profile_payload = asdict(company_profile)
                company_profile_markdown = render_company_profile_markdown(company_profile)
    elif request.job_url:
        captured = codex_live_capture_job_url(job_url=request.job_url, model=model)
        job_payload = dict(captured["job_posting"])
        if request.company_name and not job_payload.get("company"):
            job_payload["company"] = request.company_name
        notes = [str(item).strip() for item in job_payload.get("notes", []) if str(item).strip()]
        notes.append(f"source_channel={request.source_channel}")
        job_payload["notes"] = notes
        posting = JobPostingContent.from_dict(job_payload)

        company_profile = None
        company_profile_payload = None
        company_profile_markdown = None
        company_payload = dict(captured.get("company_profile") or {})
        if company_payload:
            if request.company_name and not company_payload.get("company_name"):
                company_payload["company_name"] = request.company_name
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
        job_url=request.job_url,
        notes=request.notes,
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
    company_name = request.company_name or infer_company_name(request.jd_text or "")
    if not company_name:
        company_name = (
            capture_bundle.job_posting_payload.get("company")
            or (capture_bundle.company_profile_payload or {}).get("company_name")
        )
    title = infer_title(request.jd_text or "") or str(capture_bundle.job_posting_payload.get("title") or "未命名岗位")
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
