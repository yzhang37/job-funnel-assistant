"""Capture-side helpers for browser-derived job materials."""

from .bundle import build_company_profile_bundle, build_job_capture_bundle
from .cache import (
    build_job_posting_subject_key,
    build_job_posting_subject_key_from_url,
    load_company_profile_cache,
    load_job_posting_cache,
    write_company_profile_cache,
    write_job_posting_cache,
)
from .company_profile import (
    CompanyMetricRow,
    CompanyMetricTable,
    CompanyNarrativeSection,
    CompanyProfileContent,
    CompanyRawSection,
    CompanyRelatedPage,
    CompanySourceSnapshot,
    CompanyTimeSeries,
    NotableAlumnus,
    TimeSeriesPoint,
    build_company_subject_key,
    detect_source_platform,
    render_company_profile_markdown,
)
from .jd_markdown import JobPostingContent, JobSection, render_jd_markdown
from .live_capture import codex_live_capture_company_name, codex_live_capture_job_url
from .service import build_manual_fallback_company_profile, enrich_company_profile_for_manual_capture

__all__ = [
    "CompanyMetricRow",
    "CompanyMetricTable",
    "CompanyNarrativeSection",
    "CompanyProfileContent",
    "CompanyRawSection",
    "CompanyRelatedPage",
    "CompanySourceSnapshot",
    "CompanyTimeSeries",
    "JobPostingContent",
    "JobSection",
    "NotableAlumnus",
    "TimeSeriesPoint",
    "build_company_profile_bundle",
    "build_job_posting_subject_key",
    "build_job_posting_subject_key_from_url",
    "build_manual_fallback_company_profile",
    "build_job_capture_bundle",
    "build_company_subject_key",
    "codex_live_capture_company_name",
    "codex_live_capture_job_url",
    "detect_source_platform",
    "enrich_company_profile_for_manual_capture",
    "load_company_profile_cache",
    "load_job_posting_cache",
    "render_company_profile_markdown",
    "render_jd_markdown",
    "write_company_profile_cache",
    "write_job_posting_cache",
]
