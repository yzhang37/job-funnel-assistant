"""Capture-side helpers for browser-derived job materials."""

from .bundle import build_company_profile_bundle, build_job_capture_bundle
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
    "build_job_capture_bundle",
    "build_company_subject_key",
    "detect_source_platform",
    "render_company_profile_markdown",
    "render_jd_markdown",
]
