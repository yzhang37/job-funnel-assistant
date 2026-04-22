from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlparse

from .indeed import (
    canonicalize_indeed_job_url,
    canonicalize_indeed_job_urls,
    extract_indeed_job_id,
)
from .linkedin import (
    canonicalize_linkedin_job_url,
    canonicalize_linkedin_job_urls,
    extract_linkedin_job_id,
)


SUPPORTED_JOB_PLATFORMS = ("linkedin", "indeed")

_HOST_TO_PLATFORM = {
    "linkedin.com": "linkedin",
    "www.linkedin.com": "linkedin",
    "indeed.com": "indeed",
    "www.indeed.com": "indeed",
}


def infer_job_platform(value: str) -> str:
    parsed = urlparse(value.strip())
    host = parsed.netloc.lower()
    if host in _HOST_TO_PLATFORM:
        return _HOST_TO_PLATFORM[host]
    raise ValueError(f"Could not infer supported job platform from {value!r}.")


def extract_job_id(value: str, *, platform: str | None = None) -> str | None:
    normalized_platform = _resolve_platform(value, platform=platform)
    if normalized_platform == "linkedin":
        return extract_linkedin_job_id(value)
    if normalized_platform == "indeed":
        return extract_indeed_job_id(value)
    raise ValueError(f"Unsupported job platform: {normalized_platform!r}.")


def canonicalize_job_url(value: str, *, platform: str | None = None) -> str:
    normalized_platform = _resolve_platform(value, platform=platform)
    if normalized_platform == "linkedin":
        return canonicalize_linkedin_job_url(value)
    if normalized_platform == "indeed":
        return canonicalize_indeed_job_url(value)
    raise ValueError(f"Unsupported job platform: {normalized_platform!r}.")


def canonicalize_job_urls(
    values: Iterable[str],
    *,
    platform: str | None = None,
) -> list[str]:
    if platform == "linkedin":
        return canonicalize_linkedin_job_urls(values)
    if platform == "indeed":
        return canonicalize_indeed_job_urls(values)

    seen: set[str] = set()
    canonical_urls: list[str] = []
    for value in values:
        canonical_url = canonicalize_job_url(value, platform=platform)
        if canonical_url in seen:
            continue
        seen.add(canonical_url)
        canonical_urls.append(canonical_url)
    return canonical_urls


def _resolve_platform(value: str, *, platform: str | None) -> str:
    if platform is not None:
        normalized = platform.strip().lower()
        if normalized not in SUPPORTED_JOB_PLATFORMS:
            raise ValueError(
                f"Unsupported job platform {platform!r}. "
                f"Expected one of: {', '.join(SUPPORTED_JOB_PLATFORMS)}."
            )
        return normalized
    return infer_job_platform(value)
