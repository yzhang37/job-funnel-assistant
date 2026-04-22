from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import parse_qs, urlparse


INDEED_HOSTS = {
    "indeed.com",
    "www.indeed.com",
}


def extract_indeed_job_id(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None

    parsed = urlparse(text)
    if parsed.netloc and parsed.netloc.lower() not in INDEED_HOSTS:
        return None

    query_values = parse_qs(parsed.query)
    direct_job_id = _first_job_id(query_values.get("jk", []))
    if direct_job_id is not None:
        return direct_job_id

    visible_job_id = _first_job_id(query_values.get("vjk", []))
    if visible_job_id is not None:
        return visible_job_id

    return None


def canonicalize_indeed_job_url(value: str) -> str:
    job_id = extract_indeed_job_id(value)
    if job_id is None:
        raise ValueError(f"Could not extract Indeed job id from {value!r}.")
    return build_indeed_job_url(job_id)


def build_indeed_job_url(job_id: str) -> str:
    normalized = job_id.strip()
    if not normalized:
        raise ValueError("Indeed job id must be a non-empty string.")
    return f"https://www.indeed.com/viewjob?jk={normalized}"


def canonicalize_indeed_job_urls(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    canonical_urls: list[str] = []
    for value in values:
        canonical_url = canonicalize_indeed_job_url(value)
        if canonical_url in seen:
            continue
        seen.add(canonical_url)
        canonical_urls.append(canonical_url)
    return canonical_urls


def _first_job_id(values: list[str]) -> str | None:
    for value in values:
        text = value.strip()
        if text:
            return text
    return None
