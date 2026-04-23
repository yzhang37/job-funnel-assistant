from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from job_search_assistant.cache import CacheEntry, CachePolicyRegistry
from job_search_assistant.runtime import format_kv, get_logger
from job_search_assistant.runtime.config import load_runtime_settings
from job_search_assistant.runtime.mysql_runtime import MySQLRuntimeStore

from .company_profile import CompanyProfileContent, build_company_subject_key, detect_source_platform
from .jd_markdown import JobPostingContent, render_jd_markdown


DEFAULT_CACHE_CONFIG = Path("config/cache_policy.toml")
DEFAULT_RUNTIME_CONFIG = Path("config/runtime.toml")

logger = get_logger("capture.cache")


def write_company_profile_cache(
    profile: CompanyProfileContent,
    *,
    repo_root: Path,
    cache_db: Path | None = None,
    cache_config: Path | None = None,
    observed_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, int]:
    cache_config_path = (cache_config or (repo_root / DEFAULT_CACHE_CONFIG)).expanduser().resolve()
    subject_key = profile.subject_key()
    observed = observed_at or datetime.now(UTC)
    source_platform = _canonical_source_platform(profile.source_platform, profile.source_url)
    summary = _write_snapshot_map(
        repo_root=repo_root,
        cache_config_path=cache_config_path,
        subject_key=subject_key,
        source_platform=source_platform,
        source_url=profile.source_url,
        snapshot_map=profile.split_cache_payloads(),
        observed_at=observed,
        metadata={
            "capture_kind": "company_profile",
            **(metadata or {}),
        },
    )

    logger.info(
        format_kv(
            "capture.cache.company_profile.written",
            company_name=profile.company_name,
            subject_key=subject_key,
            mysql_database=load_runtime_settings(repo_root, DEFAULT_RUNTIME_CONFIG).mysql.database,
            namespaces=",".join(f"{key}:{value}" for key, value in sorted(summary.items())),
        )
    )
    return summary


def write_job_posting_cache(
    posting: JobPostingContent,
    *,
    repo_root: Path,
    cache_db: Path | None = None,
    cache_config: Path | None = None,
    observed_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, int]:
    del cache_db  # legacy argument retained for CLI compatibility
    cache_config_path = (cache_config or (repo_root / DEFAULT_CACHE_CONFIG)).expanduser().resolve()
    observed = observed_at or datetime.now(UTC)
    subject_key = build_job_posting_subject_key(posting)
    source_platform = _canonical_source_platform(posting.source_platform, posting.source_url)
    fields = {
        "title": posting.title,
        "company": posting.company,
        "location": posting.location,
        "source_platform": posting.source_platform,
        "source_url": posting.source_url,
        "signals": posting.signals,
        "sections": [
            {
                "heading": section.heading,
                "paragraphs": section.paragraphs,
                "bullets": section.bullets,
            }
            for section in posting.sections
            if section.heading or section.paragraphs or section.bullets
        ],
        "compensation_text": posting.compensation_text,
        "benefits": posting.benefits,
        "notes": posting.notes,
        "jd_text": render_jd_markdown(posting),
    }
    summary = _write_snapshot_map(
        repo_root=repo_root,
        cache_config_path=cache_config_path,
        subject_key=subject_key,
        source_platform=source_platform,
        source_url=posting.source_url,
        snapshot_map={"job_posting": {key: value for key, value in fields.items() if value not in (None, "", [], {})}},
        observed_at=observed,
        metadata={
            "capture_kind": "job_posting",
            **(metadata or {}),
        },
    )
    logger.info(
        format_kv(
            "capture.cache.job_posting.written",
            title=posting.title,
            subject_key=subject_key,
            mysql_database=load_runtime_settings(repo_root, DEFAULT_RUNTIME_CONFIG).mysql.database,
            namespaces=",".join(f"{key}:{value}" for key, value in sorted(summary.items())),
        )
    )
    return summary


def load_job_posting_cache(
    *,
    repo_root: Path,
    job_url: str,
    observed_at: datetime | None = None,
) -> tuple[JobPostingContent | None, str | None]:
    source_platform = _canonical_source_platform(None, job_url)
    subject_key = build_job_posting_subject_key_from_url(job_url)
    entries = _list_usable_entries(
        repo_root=repo_root,
        namespace="job_posting",
        subject_key=subject_key,
        source_platform=source_platform,
        observed_at=observed_at,
    )
    if not entries:
        logger.info(format_kv("capture.cache.job_posting.miss", job_url=job_url, subject_key=subject_key))
        return None, None
    fields = {entry.field_name: entry.value for entry in entries}
    payload = {
        "title": fields.get("title", ""),
        "company": fields.get("company"),
        "location": fields.get("location"),
        "source_platform": fields.get("source_platform") or source_platform,
        "source_url": fields.get("source_url") or job_url,
        "signals": fields.get("signals") or [],
        "sections": fields.get("sections") or [],
        "compensation_text": fields.get("compensation_text"),
        "benefits": fields.get("benefits") or [],
        "notes": fields.get("notes") or [],
    }
    try:
        posting = JobPostingContent.from_dict(payload)
    except Exception as exc:
        logger.warning(
            format_kv(
                "capture.cache.job_posting.invalid",
                job_url=job_url,
                subject_key=subject_key,
                error=str(exc),
            )
        )
        return None, None
    freshness = _freshness_state(entries)
    logger.info(
        format_kv(
            "capture.cache.job_posting.hit",
            job_url=job_url,
            subject_key=subject_key,
            freshness=freshness,
            field_count=len(entries),
        )
    )
    return posting, freshness


def load_company_profile_cache(
    *,
    repo_root: Path,
    company_name: str,
    source_url: str | None,
    observed_at: datetime | None = None,
) -> tuple[CompanyProfileContent | None, str | None]:
    subject_key = build_company_subject_key(company_name, source_url)
    source_platform = _canonical_source_platform(None, source_url)
    static_entries = _list_usable_entries(
        repo_root=repo_root,
        namespace="company_profile_static",
        subject_key=subject_key,
        source_platform=source_platform if source_platform else None,
        observed_at=observed_at,
    )
    insight_entries = _list_usable_entries(
        repo_root=repo_root,
        namespace="company_insights",
        subject_key=subject_key,
        source_platform=source_platform if source_platform else None,
        observed_at=observed_at,
    )
    entries = static_entries + insight_entries
    if not entries:
        logger.info(
            format_kv(
                "capture.cache.company_profile.miss",
                company_name=company_name,
                subject_key=subject_key,
            )
        )
        return None, None
    payload = {entry.field_name: entry.value for entry in entries}
    if not payload.get("company_name"):
        payload["company_name"] = company_name
    if not payload.get("source_url") and source_url:
        payload["source_url"] = source_url
    try:
        profile = CompanyProfileContent.from_dict(payload)
    except Exception as exc:
        logger.warning(
            format_kv(
                "capture.cache.company_profile.invalid",
                company_name=company_name,
                subject_key=subject_key,
                error=str(exc),
            )
        )
        return None, None
    freshness = _freshness_state(entries)
    logger.info(
        format_kv(
            "capture.cache.company_profile.hit",
            company_name=company_name,
            subject_key=subject_key,
            freshness=freshness,
            static_fields=len(static_entries),
            insight_fields=len(insight_entries),
        )
    )
    return profile, freshness


def build_job_posting_subject_key(posting: JobPostingContent) -> str:
    if posting.source_url:
        return build_job_posting_subject_key_from_url(
            posting.source_url,
            source_platform=posting.source_platform,
        )
    raw = "|".join(
        [
            _canonical_source_platform(posting.source_platform, posting.source_url),
            posting.company or "",
            posting.title or "",
            posting.location or "",
        ]
    )
    return f"job:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def build_job_posting_subject_key_from_url(job_url: str, *, source_platform: str | None = None) -> str:
    digest = hashlib.sha256(job_url.encode("utf-8")).hexdigest()[:16]
    platform = _canonical_source_platform(source_platform, job_url) or "job"
    return f"{platform}:{digest}"


def _write_snapshot_map(
    *,
    repo_root: Path,
    cache_config_path: Path,
    subject_key: str,
    source_platform: str,
    source_url: str | None,
    snapshot_map: dict[str, dict[str, Any]],
    observed_at: datetime,
    metadata: dict[str, Any],
) -> dict[str, int]:
    runtime_settings = load_runtime_settings(repo_root, DEFAULT_RUNTIME_CONFIG)
    registry = CachePolicyRegistry.from_file(cache_config_path)
    store = MySQLRuntimeStore(runtime_settings.mysql)
    store.ensure_schema()
    summary: dict[str, int] = {}
    try:
        for namespace, fields in snapshot_map.items():
            count = 0
            for field_name, value in fields.items():
                policy = registry.resolve(
                    namespace=namespace,
                    field_name=field_name,
                    source_platform=source_platform or None,
                    subject_key=subject_key,
                )
                store.upsert_cache_entry(
                    namespace=namespace,
                    subject_key=subject_key,
                    field_name=field_name,
                    source_platform=source_platform,
                    source_url=source_url,
                    value=value,
                    observed_at=observed_at,
                    fresh_until=observed_at + policy.fresh_for,
                    stale_until=observed_at + policy.stale_for,
                    metadata={
                        **metadata,
                        "_policy": policy.to_dict(),
                    },
                )
                count += 1
            summary[namespace] = count
    finally:
        store.close()
    return summary


def _list_usable_entries(
    *,
    repo_root: Path,
    namespace: str,
    subject_key: str,
    source_platform: str | None,
    observed_at: datetime | None,
) -> list[CacheEntry]:
    runtime_settings = load_runtime_settings(repo_root, DEFAULT_RUNTIME_CONFIG)
    store = MySQLRuntimeStore(runtime_settings.mysql)
    try:
        entries = store.list_cache_subject(
            namespace=namespace,
            subject_key=subject_key,
            source_platform=source_platform,
        )
    finally:
        store.close()
    at = observed_at or datetime.now(UTC)
    return [entry for entry in entries if entry.is_usable(at)]


def _freshness_state(entries: list[CacheEntry], at: datetime | None = None) -> str:
    now = at or datetime.now(UTC)
    return "fresh" if all(entry.is_fresh(now) for entry in entries) else "stale"


def _canonical_source_platform(source_platform: str | None, source_url: str | None) -> str:
    resolved = detect_source_platform(source_url)
    if resolved:
        return resolved
    if not source_platform:
        return ""
    return str(source_platform).strip().lower()
