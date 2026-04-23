from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from job_search_assistant.cache import CachePolicyRegistry, CacheStore
from job_search_assistant.runtime import format_kv, get_logger

from .company_profile import CompanyProfileContent


DEFAULT_CACHE_DB = Path("data/cache/job_search.sqlite3")
DEFAULT_CACHE_CONFIG = Path("config/cache_policy.toml")

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
    cache_db_path = (cache_db or (repo_root / DEFAULT_CACHE_DB)).expanduser().resolve()
    cache_config_path = (cache_config or (repo_root / DEFAULT_CACHE_CONFIG)).expanduser().resolve()

    registry = CachePolicyRegistry.from_file(cache_config_path)
    store = CacheStore(cache_db_path, registry)
    subject_key = profile.subject_key()
    observed = observed_at or datetime.now(UTC)
    summary: dict[str, int] = {}

    for namespace, fields in profile.split_cache_payloads().items():
        store.upsert_snapshot(
            namespace=namespace,
            subject_key=subject_key,
            fields=fields,
            source_platform=profile.source_platform or "",
            source_url=profile.source_url,
            observed_at=observed,
            metadata={
                "capture_kind": "company_profile",
                **(metadata or {}),
            },
        )
        summary[namespace] = len(fields)

    logger.info(
        format_kv(
            "capture.cache.company_profile.written",
            company_name=profile.company_name,
            subject_key=subject_key,
            cache_db=cache_db_path,
            namespaces=",".join(f"{key}:{value}" for key, value in sorted(summary.items())),
        )
    )
    return summary
