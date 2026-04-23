from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any
from typing import TYPE_CHECKING

from job_search_assistant.runtime import format_kv, get_logger

from .company_profile import CompanyProfileContent
from .live_capture import codex_live_capture_company_name

if TYPE_CHECKING:
    from job_search_assistant.runtime.browser_broker import BrowserExecutionBroker


logger = get_logger("capture.service")


def build_manual_fallback_company_profile(
    *,
    company_name: str,
    source_url: str | None,
    source_platform: str | None,
    source_label: str,
    jd_text: str | None = None,
) -> CompanyProfileContent:
    return CompanyProfileContent.from_dict(
        {
            "company_name": _sanitize_company_name(company_name),
            "source_url": source_url or f"manual://{source_label}",
            "source_platform": source_platform,
            "available_signals": ["company_name", "source_url" if source_url else "manual_input"],
            "missing_signals": [
                "company_insights",
                "headline_metrics",
                "metric_tables",
                "time_series",
                "source_snapshots",
            ],
            "notes": [
                "当前 company_profile 由 Capture 生成的最小回退证据包。",
                "若 live enrichment 失败，应继续允许 Analyzer 使用这个最小版本。",
            ],
            "raw_sections": [
                {
                    "heading": "Manual Intake Context",
                    "text": (jd_text or "")[:4000],
                    "source_label": source_label,
                    "note": "fallback_company_profile",
                }
            ]
            if jd_text
            else [],
        }
    )


def enrich_company_profile_for_manual_capture(
    *,
    company_name: str | None,
    job_url: str | None,
    jd_text: str | None,
    source_platform: str | None,
    source_label: str,
    model: str,
    browser_broker: BrowserExecutionBroker | None = None,
) -> CompanyProfileContent | None:
    if not company_name:
        return None
    company_name = _sanitize_company_name(company_name)

    fallback = build_manual_fallback_company_profile(
        company_name=company_name,
        source_url=job_url,
        source_platform=source_platform,
        source_label=source_label,
        jd_text=jd_text,
    )

    try:
        if browser_broker is None:
            payload = codex_live_capture_company_name(
                company_name=company_name,
                model=model,
                job_url=job_url,
                jd_text=jd_text,
            )
        else:
            payload = browser_broker.capture_company_name(
                company_name=company_name,
                model=model,
                job_url=job_url,
                jd_text=jd_text,
            )
    except RuntimeError as exc:
        logger.warning(
            format_kv(
                "capture.company_profile.enrichment.failed",
                company_name=company_name,
                job_url=job_url,
                source_label=source_label,
                error=str(exc),
            )
        )
        return fallback

    merged_payload = merge_company_profile_payloads(asdict(fallback), payload)
    logger.info(
        format_kv(
            "capture.company_profile.enrichment.done",
            company_name=company_name,
            job_url=job_url,
            has_source_snapshots=bool(merged_payload.get("source_snapshots")),
            has_metric_tables=bool(merged_payload.get("metric_tables")),
            has_time_series=bool(merged_payload.get("time_series")),
        )
    )
    return CompanyProfileContent.from_dict(merged_payload)


def merge_company_profile_payloads(
    base: dict[str, Any],
    overlay: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(base)

    for field_name in (
        "company_name",
        "source_url",
        "source_platform",
        "company_tagline",
        "company_description",
        "industry",
        "headquarters",
        "followers_text",
        "employee_size_text",
        "employees_on_platform_text",
    ):
        overlay_value = overlay.get(field_name)
        if overlay_value not in (None, "", [], {}):
            merged[field_name] = overlay_value

    merged["featured_customers"] = _merge_list(base.get("featured_customers"), overlay.get("featured_customers"))
    merged["bridge_signals"] = _merge_list(base.get("bridge_signals"), overlay.get("bridge_signals"))
    merged["competitor_names"] = _merge_list(base.get("competitor_names"), overlay.get("competitor_names"))
    merged["available_signals"] = _merge_list(base.get("available_signals"), overlay.get("available_signals"))
    merged["missing_signals"] = _subtract_list(
        _merge_list(base.get("missing_signals"), overlay.get("missing_signals")),
        merged["available_signals"],
    )
    merged["notes"] = _merge_list(base.get("notes"), overlay.get("notes"))
    merged["raw_sections"] = _merge_object_list(base.get("raw_sections"), overlay.get("raw_sections"))
    merged["source_snapshots"] = _merge_object_list(base.get("source_snapshots"), overlay.get("source_snapshots"))
    merged["narrative_sections"] = _merge_object_list(base.get("narrative_sections"), overlay.get("narrative_sections"))
    merged["metric_tables"] = _merge_object_list(base.get("metric_tables"), overlay.get("metric_tables"))
    merged["time_series"] = _merge_object_list(base.get("time_series"), overlay.get("time_series"))
    merged["notable_alumni"] = _merge_object_list(base.get("notable_alumni"), overlay.get("notable_alumni"))
    merged["related_pages"] = _merge_object_list(base.get("related_pages"), overlay.get("related_pages"))

    headline_metrics = dict(base.get("headline_metrics") or {})
    headline_metrics.update(
        {
            key: value
            for key, value in _normalize_metric_map(overlay.get("headline_metrics")).items()
            if value not in (None, "")
        }
    )
    merged["headline_metrics"] = headline_metrics
    resolved_missing: list[str] = []
    if merged["headline_metrics"]:
        resolved_missing.append("headline_metrics")
    if merged["metric_tables"]:
        resolved_missing.append("metric_tables")
    if merged["time_series"]:
        resolved_missing.append("time_series")
    if merged["source_snapshots"]:
        resolved_missing.append("source_snapshots")
    if merged["headline_metrics"] or merged["metric_tables"] or merged["time_series"] or merged["source_snapshots"]:
        resolved_missing.append("company_insights")
    merged["missing_signals"] = _subtract_list(merged["missing_signals"], resolved_missing)
    return merged


def _merge_list(left: Any, right: Any) -> list[Any]:
    seen: set[str] = set()
    merged: list[Any] = []
    for raw in list(left or []) + list(right or []):
        if raw in (None, "", {}):
            continue
        key = str(raw)
        if key in seen:
            continue
        seen.add(key)
        merged.append(raw)
    return merged


def _merge_object_list(left: Any, right: Any) -> list[dict[str, Any]]:
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for raw in list(left or []) + list(right or []):
        if not isinstance(raw, dict):
            continue
        key = repr(sorted(raw.items()))
        if key in seen:
            continue
        seen.add(key)
        merged.append(raw)
    return merged


def _subtract_list(source: list[Any], to_remove: list[Any]) -> list[Any]:
    removed = {str(item) for item in to_remove}
    result: list[Any] = []
    seen: set[str] = set()
    for item in source:
        key = str(item)
        if key in removed or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _normalize_metric_map(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            str(key).strip(): raw_value
            for key, raw_value in value.items()
            if str(key).strip()
        }
    if isinstance(value, list):
        normalized: dict[str, Any] = {}
        for item in value:
            if not isinstance(item, dict):
                continue
            key = str(item.get("name") or item.get("label") or item.get("column") or "").strip()
            raw_value = item.get("value")
            if not key or raw_value in (None, ""):
                continue
            normalized[key] = raw_value
        return normalized
    return {}


def _sanitize_company_name(text: str) -> str:
    cleaned = text.strip()
    cleaned = cleaned.lstrip("-*# ").strip()
    prefixes = (
        "公司:",
        "company:",
        "company name:",
        "公司名称:",
    )
    lowered = cleaned.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix.lower()):
            cleaned = cleaned[len(prefix):].strip()
            break
    return cleaned
