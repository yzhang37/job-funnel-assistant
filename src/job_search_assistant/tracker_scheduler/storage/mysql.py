from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from job_search_assistant.runtime.mysql_runtime import TIMESTAMP_FORMAT

from ..models import TrackerDiscoverySummary, TrackerRunState


class MySQLTrackerStateStore:
    def __init__(self, runtime_store) -> None:
        self.runtime_store = runtime_store

    def get_latest_run_states(self) -> dict[str, TrackerRunState]:
        with self.runtime_store.connect() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT
                  tracker_id,
                  started_at,
                  finished_at,
                  status,
                  target_new_jobs,
                  submitted_count,
                  unique_submitted_count,
                  tracker_new_count,
                  global_new_count
                FROM tracker_runs
                WHERE run_id IN (
                  SELECT MAX(run_id)
                  FROM tracker_runs
                  GROUP BY tracker_id
                )
                """
            )
            rows = cursor.fetchall()
            cursor.close()

        states: dict[str, TrackerRunState] = {}
        for row in rows:
            states[row["tracker_id"]] = TrackerRunState(
                tracker_id=row["tracker_id"],
                last_started_at=_from_text(row["started_at"]),
                last_finished_at=_from_text(row["finished_at"]),
                last_status=row["status"],
                target_new_jobs=int(row["target_new_jobs"]),
                submitted_count=int(row["submitted_count"]),
                unique_submitted_count=int(row["unique_submitted_count"]),
                tracker_new_count=int(row["tracker_new_count"]),
                global_new_count=int(row["global_new_count"]),
            )
        return states

    def get_existing_job_urls(self, job_urls: list[str]) -> set[str]:
        normalized_urls = _normalize_urls(job_urls)
        if not normalized_urls:
            return set()
        hashed_pairs = [(job_url, _hash_job_url(job_url)) for job_url in normalized_urls]
        placeholders = ", ".join(["%s"] * len(hashed_pairs))
        query = f"SELECT job_url_hash, job_url FROM discovered_jobs WHERE job_url_hash IN ({placeholders})"
        with self.runtime_store.connect() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, tuple(job_url_hash for _, job_url_hash in hashed_pairs))
            rows = cursor.fetchall()
            cursor.close()
        by_hash = {str(row["job_url_hash"]): str(row["job_url"]) for row in rows}
        return {job_url for job_url, job_url_hash in hashed_pairs if by_hash.get(job_url_hash) == job_url}

    def record_discovery_run(
        self,
        *,
        tracker_id: str,
        target_new_jobs: int,
        job_urls: list[str],
        status: str,
        started_at: datetime,
        finished_at: datetime,
    ) -> TrackerDiscoverySummary:
        normalized_urls = _normalize_urls(job_urls)
        tracker_new_count = 0
        global_new_count = 0
        finished_text = _to_text(finished_at)

        with self.runtime_store.connect() as conn:
            cursor = conn.cursor(dictionary=True)
            for job_url in normalized_urls:
                job_url_hash = _hash_job_url(job_url)
                cursor.execute(
                    "SELECT job_url FROM discovered_jobs WHERE job_url_hash = %s",
                    (job_url_hash,),
                )
                existing_global = cursor.fetchone()
                if existing_global is None or str(existing_global["job_url"]) != job_url:
                    cursor.execute(
                        """
                        INSERT INTO discovered_jobs (
                          job_url_hash, job_url, first_seen_at, last_seen_at, first_tracker_id, last_tracker_id
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (job_url_hash, job_url, finished_text, finished_text, tracker_id, tracker_id),
                    )
                    global_new_count += 1
                else:
                    cursor.execute(
                        """
                        UPDATE discovered_jobs
                        SET last_seen_at = %s, last_tracker_id = %s
                        WHERE job_url_hash = %s
                        """,
                        (finished_text, tracker_id, job_url_hash),
                    )

                cursor.execute(
                    """
                    SELECT hit_count
                    FROM tracker_job_hits
                    WHERE tracker_id = %s AND job_url_hash = %s
                    """,
                    (tracker_id, job_url_hash),
                )
                existing_hit = cursor.fetchone()
                if existing_hit is None:
                    cursor.execute(
                        """
                        INSERT INTO tracker_job_hits (
                          tracker_id, job_url_hash, job_url, first_seen_at, last_seen_at, hit_count
                        ) VALUES (%s, %s, %s, %s, %s, 1)
                        """,
                        (tracker_id, job_url_hash, job_url, finished_text, finished_text),
                    )
                    tracker_new_count += 1
                else:
                    cursor.execute(
                        """
                        UPDATE tracker_job_hits
                        SET last_seen_at = %s, hit_count = hit_count + 1
                        WHERE tracker_id = %s AND job_url_hash = %s
                        """,
                        (finished_text, tracker_id, job_url_hash),
                    )

            cursor.execute(
                """
                INSERT INTO tracker_runs (
                  tracker_id, started_at, finished_at, status, target_new_jobs,
                  submitted_count, unique_submitted_count, tracker_new_count,
                  global_new_count, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    tracker_id,
                    _to_text(started_at),
                    finished_text,
                    status,
                    target_new_jobs,
                    len(job_urls),
                    len(normalized_urls),
                    tracker_new_count,
                    global_new_count,
                    finished_text,
                ),
            )
            run_id = int(cursor.lastrowid)
            cursor.close()

        unique_submitted_count = len(normalized_urls)
        return TrackerDiscoverySummary(
            tracker_id=tracker_id,
            status=status,
            target_new_jobs=target_new_jobs,
            submitted_count=len(job_urls),
            unique_submitted_count=unique_submitted_count,
            tracker_new_count=tracker_new_count,
            tracker_repeat_count=unique_submitted_count - tracker_new_count,
            global_new_count=global_new_count,
            global_existing_count=unique_submitted_count - global_new_count,
            run_started_at=started_at,
            run_finished_at=finished_at,
            run_id=run_id,
        )


def _normalize_urls(job_urls: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in job_urls:
        text = str(value).strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return normalized


def _hash_job_url(job_url: str) -> str:
    return hashlib.sha256(job_url.encode("utf-8")).hexdigest()


def _to_text(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime(TIMESTAMP_FORMAT)


def _from_text(value: str) -> datetime:
    return datetime.strptime(value, TIMESTAMP_FORMAT).replace(tzinfo=UTC)
