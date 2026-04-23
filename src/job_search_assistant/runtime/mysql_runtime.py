from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Iterator

import mysql.connector
from mysql.connector import pooling

from job_search_assistant.cache import CacheEntry

from .config import MySQLSettings


TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class MySQLRuntimeStore:
    def __init__(self, settings: MySQLSettings) -> None:
        self.settings = settings
        self._pool = pooling.MySQLConnectionPool(
            pool_name=f"jobfunnel_{settings.database}",
            pool_size=settings.pool_size,
            **settings.connector_kwargs(),
        )

    @contextmanager
    def connect(self) -> Iterator[mysql.connector.MySQLConnection]:
        conn = self._pool.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def ensure_schema(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS runtime_offsets (
              offset_key VARCHAR(255) PRIMARY KEY,
              offset_value BIGINT NOT NULL,
              updated_at VARCHAR(32) NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS manual_intake_events (
              request_id VARCHAR(64) PRIMARY KEY,
              source_channel VARCHAR(64) NOT NULL,
              update_id BIGINT NULL,
              chat_id BIGINT NULL,
              message_id BIGINT NULL,
              job_url TEXT NULL,
              has_jd_text TINYINT(1) NOT NULL,
              status VARCHAR(32) NOT NULL,
              payload_json LONGTEXT NOT NULL,
              created_at VARCHAR(32) NOT NULL,
              updated_at VARCHAR(32) NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS capture_jobs (
              capture_id VARCHAR(64) PRIMARY KEY,
              request_id VARCHAR(64) NOT NULL,
              source_component VARCHAR(64) NOT NULL,
              source_channel VARCHAR(64) NOT NULL,
              job_url TEXT NULL,
              company_name TEXT NULL,
              status VARCHAR(32) NOT NULL,
              bundle_dir TEXT NULL,
              job_title TEXT NULL,
              company_label TEXT NULL,
              payload_json LONGTEXT NOT NULL,
              last_error LONGTEXT NULL,
              created_at VARCHAR(32) NOT NULL,
              updated_at VARCHAR(32) NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS analysis_jobs (
              analysis_id VARCHAR(64) PRIMARY KEY,
              capture_id VARCHAR(64) NOT NULL,
              bundle_dir TEXT NOT NULL,
              status VARCHAR(32) NOT NULL,
              decision VARCHAR(32) NULL,
              fit_score INT NULL,
              payload_json LONGTEXT NOT NULL,
              last_error LONGTEXT NULL,
              created_at VARCHAR(32) NOT NULL,
              updated_at VARCHAR(32) NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS output_jobs (
              output_id VARCHAR(64) PRIMARY KEY,
              analysis_id VARCHAR(64) NOT NULL,
              status VARCHAR(32) NOT NULL,
              notion_page_id VARCHAR(128) NULL,
              notion_page_url TEXT NULL,
              telegram_chat_id BIGINT NULL,
              payload_json LONGTEXT NOT NULL,
              last_error LONGTEXT NULL,
              created_at VARCHAR(32) NOT NULL,
              updated_at VARCHAR(32) NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS browser_broker_leases (
              lane_key VARCHAR(255) PRIMARY KEY,
              holder_id VARCHAR(255) NOT NULL,
              node_id VARCHAR(255) NOT NULL,
              task_kind VARCHAR(128) NOT NULL,
              task_ref VARCHAR(255) NOT NULL,
              leased_until VARCHAR(32) NOT NULL,
              heartbeat_at VARCHAR(32) NOT NULL,
              updated_at VARCHAR(32) NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS tracker_runs (
              run_id BIGINT PRIMARY KEY AUTO_INCREMENT,
              tracker_id VARCHAR(255) NOT NULL,
              started_at VARCHAR(32) NOT NULL,
              finished_at VARCHAR(32) NOT NULL,
              status VARCHAR(32) NOT NULL,
              target_new_jobs INT NOT NULL,
              submitted_count INT NOT NULL,
              unique_submitted_count INT NOT NULL,
              tracker_new_count INT NOT NULL,
              global_new_count INT NOT NULL,
              created_at VARCHAR(32) NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS discovered_jobs (
              job_url_hash CHAR(64) PRIMARY KEY,
              job_url TEXT NOT NULL,
              first_seen_at VARCHAR(32) NOT NULL,
              last_seen_at VARCHAR(32) NOT NULL,
              first_tracker_id VARCHAR(255) NOT NULL,
              last_tracker_id VARCHAR(255) NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS tracker_job_hits (
              tracker_id VARCHAR(255) NOT NULL,
              job_url_hash CHAR(64) NOT NULL,
              job_url TEXT NOT NULL,
              first_seen_at VARCHAR(32) NOT NULL,
              last_seen_at VARCHAR(32) NOT NULL,
              hit_count INT NOT NULL DEFAULT 1,
              PRIMARY KEY (tracker_id, job_url_hash)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS capture_cache_entries (
              namespace VARCHAR(64) NOT NULL,
              subject_key VARCHAR(191) NOT NULL,
              field_name VARCHAR(191) NOT NULL,
              source_platform VARCHAR(64) NOT NULL DEFAULT '',
              source_url TEXT NULL,
              value_json LONGTEXT NOT NULL,
              observed_at VARCHAR(32) NOT NULL,
              fresh_until VARCHAR(32) NOT NULL,
              stale_until VARCHAR(32) NOT NULL,
              metadata_json LONGTEXT NOT NULL,
              created_at VARCHAR(32) NOT NULL,
              updated_at VARCHAR(32) NOT NULL,
              PRIMARY KEY (namespace, subject_key, field_name, source_platform)
            )
            """,
        ]
        with self.connect() as conn:
            cursor = conn.cursor()
            for statement in statements:
                cursor.execute(statement)
            cursor.close()

    def close(self) -> None:
        return None

    def get_offset(self, offset_key: str, *, default: int = 0) -> int:
        with self.connect() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT offset_value FROM runtime_offsets WHERE offset_key = %s",
                (offset_key,),
            )
            row = cursor.fetchone()
            cursor.close()
        return int(row["offset_value"]) if row else default

    def set_offset(self, offset_key: str, value: int) -> None:
        now_text = _to_text(datetime.now(UTC))
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO runtime_offsets (offset_key, offset_value, updated_at)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE offset_value = VALUES(offset_value), updated_at = VALUES(updated_at)
                """,
                (offset_key, value, now_text),
            )
            cursor.close()

    def record_manual_intake_event(
        self,
        *,
        request_id: str,
        source_channel: str,
        update_id: int | None,
        chat_id: int | None,
        message_id: int | None,
        job_url: str | None,
        has_jd_text: bool,
        status: str,
        payload: dict[str, Any],
    ) -> None:
        now_text = _to_text(datetime.now(UTC))
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO manual_intake_events (
                  request_id, source_channel, update_id, chat_id, message_id,
                  job_url, has_jd_text, status, payload_json, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  status = VALUES(status),
                  payload_json = VALUES(payload_json),
                  updated_at = VALUES(updated_at)
                """,
                (
                    request_id,
                    source_channel,
                    update_id,
                    chat_id,
                    message_id,
                    job_url,
                    1 if has_jd_text else 0,
                    status,
                    json.dumps(payload, ensure_ascii=False),
                    now_text,
                    now_text,
                ),
            )
            cursor.close()

    def record_capture_job(
        self,
        *,
        capture_id: str,
        request_id: str,
        source_component: str,
        source_channel: str,
        job_url: str | None,
        company_name: str | None,
        status: str,
        payload: dict[str, Any],
        bundle_dir: str | None = None,
        job_title: str | None = None,
        company_label: str | None = None,
        last_error: str | None = None,
    ) -> None:
        now_text = _to_text(datetime.now(UTC))
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO capture_jobs (
                  capture_id, request_id, source_component, source_channel,
                  job_url, company_name, status, bundle_dir, job_title,
                  company_label, payload_json, last_error, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  status = VALUES(status),
                  bundle_dir = VALUES(bundle_dir),
                  job_title = VALUES(job_title),
                  company_label = VALUES(company_label),
                  payload_json = VALUES(payload_json),
                  last_error = VALUES(last_error),
                  updated_at = VALUES(updated_at)
                """,
                (
                    capture_id,
                    request_id,
                    source_component,
                    source_channel,
                    job_url,
                    company_name,
                    status,
                    bundle_dir,
                    job_title,
                    company_label,
                    json.dumps(payload, ensure_ascii=False),
                    last_error,
                    now_text,
                    now_text,
                ),
            )
            cursor.close()

    def record_analysis_job(
        self,
        *,
        analysis_id: str,
        capture_id: str,
        bundle_dir: str,
        status: str,
        payload: dict[str, Any],
        decision: str | None = None,
        fit_score: int | None = None,
        last_error: str | None = None,
    ) -> None:
        now_text = _to_text(datetime.now(UTC))
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO analysis_jobs (
                  analysis_id, capture_id, bundle_dir, status, decision,
                  fit_score, payload_json, last_error, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  status = VALUES(status),
                  decision = VALUES(decision),
                  fit_score = VALUES(fit_score),
                  payload_json = VALUES(payload_json),
                  last_error = VALUES(last_error),
                  updated_at = VALUES(updated_at)
                """,
                (
                    analysis_id,
                    capture_id,
                    bundle_dir,
                    status,
                    decision,
                    fit_score,
                    json.dumps(payload, ensure_ascii=False),
                    last_error,
                    now_text,
                    now_text,
                ),
            )
            cursor.close()

    def record_output_job(
        self,
        *,
        output_id: str,
        analysis_id: str,
        status: str,
        payload: dict[str, Any],
        notion_page_id: str | None = None,
        notion_page_url: str | None = None,
        telegram_chat_id: int | None = None,
        last_error: str | None = None,
    ) -> None:
        now_text = _to_text(datetime.now(UTC))
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO output_jobs (
                  output_id, analysis_id, status, notion_page_id, notion_page_url,
                  telegram_chat_id, payload_json, last_error, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  status = VALUES(status),
                  notion_page_id = VALUES(notion_page_id),
                  notion_page_url = VALUES(notion_page_url),
                  telegram_chat_id = VALUES(telegram_chat_id),
                  payload_json = VALUES(payload_json),
                  last_error = VALUES(last_error),
                  updated_at = VALUES(updated_at)
                """,
                (
                    output_id,
                    analysis_id,
                    status,
                    notion_page_id,
                    notion_page_url,
                    telegram_chat_id,
                    json.dumps(payload, ensure_ascii=False),
                    last_error,
                    now_text,
                    now_text,
                ),
            )
            cursor.close()

    def upsert_cache_entry(
        self,
        *,
        namespace: str,
        subject_key: str,
        field_name: str,
        source_platform: str = "",
        source_url: str | None = None,
        value: Any,
        observed_at: datetime,
        fresh_until: datetime,
        stale_until: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now_text = _to_text(datetime.now(UTC))
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO capture_cache_entries (
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
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  source_url = VALUES(source_url),
                  value_json = VALUES(value_json),
                  observed_at = VALUES(observed_at),
                  fresh_until = VALUES(fresh_until),
                  stale_until = VALUES(stale_until),
                  metadata_json = VALUES(metadata_json),
                  updated_at = VALUES(updated_at)
                """,
                (
                    namespace,
                    subject_key,
                    field_name,
                    source_platform,
                    source_url,
                    json.dumps(value, ensure_ascii=False),
                    _to_text(observed_at),
                    _to_text(fresh_until),
                    _to_text(stale_until),
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now_text,
                    now_text,
                ),
            )
            cursor.close()

    def get_cache_entry(
        self,
        *,
        namespace: str,
        subject_key: str,
        field_name: str,
        source_platform: str = "",
    ) -> CacheEntry | None:
        with self.connect() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
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
                FROM capture_cache_entries
                WHERE namespace = %s
                  AND subject_key = %s
                  AND field_name = %s
                  AND source_platform = %s
                """,
                (namespace, subject_key, field_name, source_platform),
            )
            row = cursor.fetchone()
            cursor.close()
        return _row_to_cache_entry(row) if row else None

    def list_cache_subject(
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
            FROM capture_cache_entries
            WHERE namespace = %s
              AND subject_key = %s
        """
        params: list[Any] = [namespace, subject_key]
        if source_platform is not None:
            query += " AND source_platform = %s"
            params.append(source_platform)
        query += " ORDER BY field_name"
        with self.connect() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            cursor.close()
        return [_row_to_cache_entry(row) for row in rows]

    def acquire_runtime_lease(
        self,
        *,
        lane_key: str,
        holder_id: str,
        node_id: str,
        task_kind: str,
        task_ref: str,
        ttl_seconds: int,
    ) -> bool:
        now = datetime.now(UTC).replace(microsecond=0)
        leased_until = now + timedelta(seconds=ttl_seconds)
        now_text = _to_text(now)
        leased_until_text = _to_text(leased_until)
        with self.connect() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT holder_id, leased_until FROM browser_broker_leases WHERE lane_key = %s FOR UPDATE",
                (lane_key,),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    """
                    INSERT INTO browser_broker_leases (
                      lane_key, holder_id, node_id, task_kind, task_ref,
                      leased_until, heartbeat_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (lane_key, holder_id, node_id, task_kind, task_ref, leased_until_text, now_text, now_text),
                )
                cursor.close()
                return True
            current_holder = str(row["holder_id"])
            current_until = _from_text(str(row["leased_until"]))
            if current_holder != holder_id and current_until > now:
                cursor.close()
                return False
            cursor.execute(
                """
                UPDATE browser_broker_leases
                SET holder_id = %s,
                    node_id = %s,
                    task_kind = %s,
                    task_ref = %s,
                    leased_until = %s,
                    heartbeat_at = %s,
                    updated_at = %s
                WHERE lane_key = %s
                """,
                (holder_id, node_id, task_kind, task_ref, leased_until_text, now_text, now_text, lane_key),
            )
            cursor.close()
            return True

    def release_runtime_lease(self, *, lane_key: str, holder_id: str) -> None:
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM browser_broker_leases WHERE lane_key = %s AND holder_id = %s",
                (lane_key, holder_id),
            )
            cursor.close()

    def acquire_browser_lease(
        self,
        *,
        lane_key: str,
        holder_id: str,
        node_id: str,
        task_kind: str,
        task_ref: str,
        ttl_seconds: int,
    ) -> bool:
        return self.acquire_runtime_lease(
            lane_key=lane_key,
            holder_id=holder_id,
            node_id=node_id,
            task_kind=task_kind,
            task_ref=task_ref,
            ttl_seconds=ttl_seconds,
        )

    def release_browser_lease(self, *, lane_key: str, holder_id: str) -> None:
        self.release_runtime_lease(lane_key=lane_key, holder_id=holder_id)


def _to_text(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime(TIMESTAMP_FORMAT)


def _from_text(value: str) -> datetime:
    return datetime.strptime(value, TIMESTAMP_FORMAT).replace(tzinfo=UTC)


def _row_to_cache_entry(row: dict[str, Any]) -> CacheEntry:
    return CacheEntry(
        namespace=str(row["namespace"]),
        subject_key=str(row["subject_key"]),
        field_name=str(row["field_name"]),
        source_platform=str(row["source_platform"]),
        source_url=str(row["source_url"]) if row["source_url"] is not None else None,
        value=json.loads(str(row["value_json"])),
        observed_at=_from_text(str(row["observed_at"])),
        fresh_until=_from_text(str(row["fresh_until"])),
        stale_until=_from_text(str(row["stale_until"])),
        metadata=json.loads(str(row["metadata_json"])),
    )
