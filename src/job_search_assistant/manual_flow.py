from __future__ import annotations

import json
import re
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
    detect_source_platform,
    render_company_profile_markdown,
    render_jd_markdown,
)


URL_PATTERN = re.compile(r"https?://\S+")


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
    company_profile_markdown: str | None
    company_profile_payload: dict[str, Any] | None


def looks_like_job_input(request: ManualIntakeRequest) -> bool:
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
) -> CaptureBundleResult:
    if not request.jd_text:
        raise ValueError("当前 manual capture 仍需要 JD 文本；纯 URL 自动抓取还没有接入这个入口。")

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
        company_profile = CompanyProfileContent.from_dict(
            {
                "company_name": company_name,
                "source_url": request.job_url or f"manual://{request.source_channel}",
                "source_platform": source_platform,
                "available_signals": ["company_name", "source_url" if request.job_url else "manual_input"],
                "missing_signals": ["company_insights", "headcount_metrics", "bridge_signals"],
                "notes": [
                    "当前 company_profile 来自 manual intake 的最小证据包。",
                    "后续可由 Computer Use capture 进一步补齐公司画像。",
                ],
                "raw_sections": [
                    {
                        "heading": "Manual Intake Context",
                        "text": request.jd_text[:4000],
                        "source_label": request.source_channel,
                    }
                ],
            }
        )
        company_profile_payload = asdict(company_profile)
        company_profile_markdown = render_company_profile_markdown(company_profile)

    run_stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = _slugify(company_name or title)
    bundle_dir = output_root / f"{run_stamp}-{slug}"
    manifest_path = build_job_capture_bundle(
        output_dir=bundle_dir,
        posting=posting,
        company_profile=company_profile,
        source_inputs={
            "input_kind": "manual_intake",
            "source_channel": request.source_channel,
        },
        notes=[f"source_channel={request.source_channel}"],
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return CaptureBundleResult(
        bundle_dir=bundle_dir,
        manifest=manifest,
        jd_markdown=render_jd_markdown(posting),
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
    result = run_analysis(
        repo_root=repo_root,
        jd_text=request.jd_text or "",
        profile_stack_path=profile_stack_path,
        provider_name=provider_name,
        model=model,
        analysis_mode=analysis_mode,
        enable_web_search=enable_web_search,
        company_name=request.company_name or infer_company_name(request.jd_text or ""),
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
    title = infer_title(request.jd_text or "") or "未命名岗位"
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
