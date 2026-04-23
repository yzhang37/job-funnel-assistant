#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_search_assistant.capture import CompanyProfileContent, JobPostingContent
from job_search_assistant.capture.cache import write_company_profile_cache, write_job_posting_cache
from job_search_assistant.runtime import format_kv, get_logger
from job_search_assistant.runtime.bootstrap import bootstrap_runtime, ensure_runtime_ready


logger = get_logger("runtime.capture_cache_migration")
CAPTURE_NAMESPACES = ("job_posting", "company_profile_static", "company_insights")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate/backfill Capture cache into MySQL.")
    parser.add_argument(
        "--sqlite-db",
        default=str(ROOT / "data/cache/job_search.sqlite3"),
        help="Legacy SQLite cache DB to migrate from.",
    )
    parser.add_argument(
        "--bundle-root",
        action="append",
        default=[],
        help="Artifact root to scan recursively for job_posting.json/company_profile.json.",
    )
    parser.add_argument("--skip-sqlite", action="store_true")
    parser.add_argument("--skip-bundles", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runtime = bootstrap_runtime(ROOT, force_logging=True)
    ensure_runtime_ready(runtime)
    try:
        sqlite_count = 0
        bundle_job_count = 0
        bundle_company_count = 0

        if not args.skip_sqlite:
            sqlite_count = migrate_sqlite_entries(runtime, Path(args.sqlite_db))

        if not args.skip_bundles:
            bundle_roots = [Path(path) for path in args.bundle_root] or [
                ROOT / "data/raw/manual_intake",
                ROOT / "data/runtime_artifacts",
            ]
            bundle_job_count, bundle_company_count = backfill_bundles(bundle_roots)

        logger.info(
            format_kv(
                "capture.cache.migration.done",
                sqlite_entries=sqlite_count,
                bundle_job_postings=bundle_job_count,
                bundle_company_profiles=bundle_company_count,
            )
        )
    finally:
        runtime.close()


def migrate_sqlite_entries(runtime, sqlite_db: Path) -> int:
    if not sqlite_db.exists():
        logger.info(format_kv("capture.cache.migration.sqlite.skip", sqlite_db=sqlite_db, reason="missing"))
        return 0
    migrated = 0
    with sqlite3.connect(sqlite_db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
              namespace,
              subject_key,
              field_name,
              source_platform,
              source_url,
              value_json,
              observed_at,
              fresh_until,
              stale_until,
              metadata_json
            FROM cache_entries
            WHERE namespace IN (?, ?, ?)
            """,
            CAPTURE_NAMESPACES,
        ).fetchall()
    for row in rows:
        runtime.runtime_store.upsert_cache_entry(
            namespace=str(row["namespace"]),
            subject_key=str(row["subject_key"]),
            field_name=str(row["field_name"]),
            source_platform=str(row["source_platform"] or ""),
            source_url=str(row["source_url"]) if row["source_url"] is not None else None,
            value=json.loads(str(row["value_json"])),
            observed_at=_from_text(str(row["observed_at"])),
            fresh_until=_from_text(str(row["fresh_until"])),
            stale_until=_from_text(str(row["stale_until"])),
            metadata=json.loads(str(row["metadata_json"])),
        )
        migrated += 1
    logger.info(
        format_kv(
            "capture.cache.migration.sqlite.done",
            sqlite_db=sqlite_db,
            migrated_entries=migrated,
        )
    )
    return migrated


def backfill_bundles(bundle_roots: list[Path]) -> tuple[int, int]:
    job_count = 0
    company_count = 0
    seen_bundle_dirs: set[Path] = set()
    for root in bundle_roots:
        if not root.exists():
            continue
        for job_path in root.rglob("job_posting.json"):
            bundle_dir = job_path.parent
            if bundle_dir in seen_bundle_dirs:
                continue
            seen_bundle_dirs.add(bundle_dir)
            payload = json.loads(job_path.read_text(encoding="utf-8"))
            posting = JobPostingContent.from_dict(payload)
            write_job_posting_cache(
                posting,
                repo_root=ROOT,
                metadata={
                    "migration_source": "bundle",
                    "bundle_dir": str(bundle_dir),
                },
            )
            job_count += 1
            company_path = bundle_dir / "company_profile.json"
            if company_path.exists():
                profile = CompanyProfileContent.from_dict(json.loads(company_path.read_text(encoding="utf-8")))
                write_company_profile_cache(
                    profile,
                    repo_root=ROOT,
                    metadata={
                        "migration_source": "bundle",
                        "bundle_dir": str(bundle_dir),
                    },
                )
                company_count += 1
    logger.info(
        format_kv(
            "capture.cache.migration.bundle.done",
            bundle_roots=",".join(str(path) for path in bundle_roots),
            job_postings=job_count,
            company_profiles=company_count,
        )
    )
    return job_count, company_count


def _from_text(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


if __name__ == "__main__":
    main()
