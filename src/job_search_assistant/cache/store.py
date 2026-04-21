from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .policy import CachePolicyRegistry, ResolvedCachePolicy


TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass
class CacheEntry:
    namespace: str
    subject_key: str
    field_name: str
    source_platform: str
    source_url: str | None
    value: Any
    observed_at: datetime
    fresh_until: datetime
    stale_until: datetime
    metadata: dict[str, Any]

    def is_fresh(self, at: datetime | None = None) -> bool:
        now = at or _utcnow()
        return now <= self.fresh_until

    def is_usable(self, at: datetime | None = None) -> bool:
        now = at or _utcnow()
        return now <= self.stale_until

    def freshness_state(self, at: datetime | None = None) -> str:
        now = at or _utcnow()
        if now <= self.fresh_until:
            return "fresh"
        if now <= self.stale_until:
            return "stale"
        return "expired"


class CacheStore:
    def __init__(self, db_path: str | Path, policy_registry: CachePolicyRegistry) -> None:
        self.db_path = Path(db_path)
        self.policy_registry = policy_registry
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def upsert_field(
        self,
        *,
        namespace: str,
        subject_key: str,
        field_name: str,
        value: Any,
        source_platform: str = "",
        source_url: str | None = None,
        observed_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CacheEntry:
        observed = observed_at or _utcnow()
        policy = self.policy_registry.resolve(
            namespace=namespace,
            field_name=field_name,
            source_platform=source_platform or None,
            subject_key=subject_key,
        )
        entry = CacheEntry(
            namespace=namespace,
            subject_key=subject_key,
            field_name=field_name,
            source_platform=source_platform,
            source_url=source_url,
            value=value,
            observed_at=observed,
            fresh_until=observed + policy.fresh_for,
            stale_until=observed + policy.stale_for,
            metadata={
                **(metadata or {}),
                "_policy": policy.to_dict(),
            },
        )
        self._write_entry(entry)
        return entry

    def upsert_snapshot(
        self,
        *,
        namespace: str,
        subject_key: str,
        fields: dict[str, Any],
        source_platform: str = "",
        source_url: str | None = None,
        observed_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[CacheEntry]:
        observed = observed_at or _utcnow()
        entries = []
        for field_name, value in fields.items():
            entries.append(
                self.upsert_field(
                    namespace=namespace,
                    subject_key=subject_key,
                    field_name=field_name,
                    value=value,
                    source_platform=source_platform,
                    source_url=source_url,
                    observed_at=observed,
                    metadata=metadata,
                )
            )
        return entries

    def get_field(
        self,
        *,
        namespace: str,
        subject_key: str,
        field_name: str,
        source_platform: str = "",
    ) -> CacheEntry | None:
        with self._connect() as conn:
            row = conn.execute(
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
                WHERE namespace = ?
                  AND subject_key = ?
                  AND field_name = ?
                  AND source_platform = ?
                """,
                (namespace, subject_key, field_name, source_platform),
            ).fetchone()
        return self._row_to_entry(row) if row else None

    def list_subject(
        self,
        *,
        namespace: str,
        subject_key: str,
        source_platform: str | None = None,
    ) -> list[CacheEntry]:
        query = """
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
            WHERE namespace = ?
              AND subject_key = ?
        """
        params: list[Any] = [namespace, subject_key]
        if source_platform is not None:
            query += " AND source_platform = ?"
            params.append(source_platform)
        query += " ORDER BY field_name"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def get_policy(
        self,
        *,
        namespace: str,
        field_name: str | None = None,
        source_platform: str | None = None,
        subject_key: str | None = None,
    ) -> ResolvedCachePolicy:
        return self.policy_registry.resolve(
            namespace=namespace,
            field_name=field_name,
            source_platform=source_platform,
            subject_key=subject_key,
        )

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_entries (
                  namespace TEXT NOT NULL,
                  subject_key TEXT NOT NULL,
                  field_name TEXT NOT NULL,
                  source_platform TEXT NOT NULL DEFAULT '',
                  source_url TEXT,
                  value_json TEXT NOT NULL,
                  observed_at TEXT NOT NULL,
                  fresh_until TEXT NOT NULL,
                  stale_until TEXT NOT NULL,
                  metadata_json TEXT NOT NULL DEFAULT '{}',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  PRIMARY KEY (namespace, subject_key, field_name, source_platform)
                )
                """
            )

    def _write_entry(self, entry: CacheEntry) -> None:
        now_text = _to_text(_utcnow())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cache_entries (
                  namespace,
                  subject_key,
                  field_name,
                  source_platform,
                  source_url,
                  value_json,
                  observed_at,
                  fresh_until,
                  stale_until,
                  metadata_json,
                  created_at,
                  updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(namespace, subject_key, field_name, source_platform)
                DO UPDATE SET
                  source_url = excluded.source_url,
                  value_json = excluded.value_json,
                  observed_at = excluded.observed_at,
                  fresh_until = excluded.fresh_until,
                  stale_until = excluded.stale_until,
                  metadata_json = excluded.metadata_json,
                  updated_at = excluded.updated_at
                """,
                (
                    entry.namespace,
                    entry.subject_key,
                    entry.field_name,
                    entry.source_platform,
                    entry.source_url,
                    json.dumps(entry.value, ensure_ascii=False),
                    _to_text(entry.observed_at),
                    _to_text(entry.fresh_until),
                    _to_text(entry.stale_until),
                    json.dumps(entry.metadata, ensure_ascii=False),
                    now_text,
                    now_text,
                ),
            )

    def _row_to_entry(self, row: sqlite3.Row) -> CacheEntry:
        return CacheEntry(
            namespace=row["namespace"],
            subject_key=row["subject_key"],
            field_name=row["field_name"],
            source_platform=row["source_platform"],
            source_url=row["source_url"],
            value=json.loads(row["value_json"]),
            observed_at=_from_text(row["observed_at"]),
            fresh_until=_from_text(row["fresh_until"]),
            stale_until=_from_text(row["stale_until"]),
            metadata=json.loads(row["metadata_json"]),
        )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _to_text(value: datetime) -> str:
    return value.astimezone(UTC).strftime(TIMESTAMP_FORMAT)


def _from_text(value: str) -> datetime:
    return datetime.strptime(value, TIMESTAMP_FORMAT).replace(tzinfo=UTC)
