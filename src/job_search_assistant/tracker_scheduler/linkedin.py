from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import parse_qs, urlparse


LINKEDIN_HOSTS = {
    "linkedin.com",
    "www.linkedin.com",
}
JOB_VIEW_PATTERN = re.compile(r"/jobs/view/(\d+)")


def extract_linkedin_job_id(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None

    parsed = urlparse(text)
    if parsed.netloc and parsed.netloc.lower() not in LINKEDIN_HOSTS:
        return None

    query_values = parse_qs(parsed.query)
    current_job_id = _first_digit_string(query_values.get("currentJobId", []))
    if current_job_id is not None:
        return current_job_id

    match = JOB_VIEW_PATTERN.search(parsed.path)
    if match:
        return match.group(1)

    return None


def canonicalize_linkedin_job_url(value: str) -> str:
    job_id = extract_linkedin_job_id(value)
    if job_id is None:
        raise ValueError(f"Could not extract LinkedIn job id from {value!r}.")
    return build_linkedin_job_url(job_id)


def build_linkedin_job_url(job_id: str | int) -> str:
    normalized = str(job_id).strip()
    if not normalized.isdigit():
        raise ValueError(f"LinkedIn job id must be digits only (got {job_id!r}).")
    return f"https://www.linkedin.com/jobs/view/{normalized}/"


def canonicalize_linkedin_job_urls(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    canonical_urls: list[str] = []
    for value in values:
        canonical_url = canonicalize_linkedin_job_url(value)
        if canonical_url in seen:
            continue
        seen.add(canonical_url)
        canonical_urls.append(canonical_url)
    return canonical_urls


def _first_digit_string(values: list[str]) -> str | None:
    for value in values:
        text = value.strip()
        if text.isdigit():
            return text
    return None
