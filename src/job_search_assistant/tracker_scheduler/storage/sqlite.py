from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ..models import TrackerDiscoverySummary, TrackerRunState


TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class SQLiteTrackerStateStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def get_latest_run_states(self) -> dict[str, TrackerRunState]:
        with self._connect() as conn:
            rows = conn.execute(
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
            ).fetchall()

        states: dict[str, TrackerRunState] = {}
        for row in rows:
            states[row["tracker_id"]] = TrackerRunState(
                tracker_id=row["tracker_id"],
                last_started_at=_from_text(row["started_at"]),
                last_finished_at=_from_text(row["finished_at"]),
                last_status=row["status"],
                target_new_jobs=row["target_new_jobs"],
                submitted_count=row["submitted_count"],
                unique_submitted_count=row["unique_submitted_count"],
                tracker_new_count=row["tracker_new_count"],
                global_new_count=row["global_new_count"],
            )
        return states

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

        with self._connect() as conn:
            for job_url in normalized_urls:
                now_text = _to_text(finished_at)
                existing_global = conn.execute(
                    "SELECT 1 FROM discovered_jobs WHERE job_url = ?",
                    (job_url,),
                ).fetchone()
                if existing_global is None:
                    conn.execute(
                        """
                        INSERT INTO discovered_jobs (
                          job_url,
                          first_seen_at,
                          last_seen_at,
                          first_tracker_id,
                          last_tracker_id
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (job_url, now_text, now_text, tracker_id, tracker_id),
                    )
                    global_new_count += 1
                else:
                    conn.execute(
                        """
                        UPDATE discovered_jobs
                        SET last_seen_at = ?,
                            last_tracker_id = ?
                        WHERE job_url = ?
                        """,
                        (now_text, tracker_id, job_url),
                    )

                existing_tracker_hit = conn.execute(
                    """
                    SELECT hit_count
                    FROM tracker_job_hits
                    WHERE tracker_id = ?
                      AND job_url = ?
                    """,
                    (tracker_id, job_url),
                ).fetchone()
                if existing_tracker_hit is None:
                    conn.execute(
                        """
                        INSERT INTO tracker_job_hits (
                          tracker_id,
                          job_url,
                          first_seen_at,
                          last_seen_at,
                          hit_count
                        )
                        VALUES (?, ?, ?, ?, 1)
                        """,
                        (tracker_id, job_url, now_text, now_text),
                    )
                    tracker_new_count += 1
                else:
                    conn.execute(
                        """
                        UPDATE tracker_job_hits
                        SET last_seen_at = ?,
                            hit_count = hit_count + 1
                        WHERE tracker_id = ?
                          AND job_url = ?
                        """,
                        (now_text, tracker_id, job_url),
                    )

            cursor = conn.execute(
                """
                INSERT INTO tracker_runs (
                  tracker_id,
                  started_at,
                  finished_at,
                  status,
                  target_new_jobs,
                  submitted_count,
                  unique_submitted_count,
                  tracker_new_count,
                  global_new_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tracker_id,
                    _to_text(started_at),
                    _to_text(finished_at),
                    status,
                    target_new_jobs,
                    len(job_urls),
                    len(normalized_urls),
                    tracker_new_count,
                    global_new_count,
                ),
            )
            run_id = int(cursor.lastrowid)

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

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tracker_runs (
                  run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  tracker_id TEXT NOT NULL,
                  started_at TEXT NOT NULL,
                  finished_at TEXT NOT NULL,
                  status TEXT NOT NULL,
                  target_new_jobs INTEGER NOT NULL,
                  submitted_count INTEGER NOT NULL,
                  unique_submitted_count INTEGER NOT NULL,
                  tracker_new_count INTEGER NOT NULL,
                  global_new_count INTEGER NOT NULL,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS discovered_jobs (
                  job_url TEXT PRIMARY KEY,
                  first_seen_at TEXT NOT NULL,
                  last_seen_at TEXT NOT NULL,
                  first_tracker_id TEXT NOT NULL,
                  last_tracker_id TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tracker_job_hits (
                  tracker_id TEXT NOT NULL,
                  job_url TEXT NOT NULL,
                  first_seen_at TEXT NOT NULL,
                  last_seen_at TEXT NOT NULL,
                  hit_count INTEGER NOT NULL DEFAULT 1,
                  PRIMARY KEY (tracker_id, job_url)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


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


def _to_text(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime(TIMESTAMP_FORMAT)


def _from_text(value: str) -> datetime:
    return datetime.strptime(value, TIMESTAMP_FORMAT).replace(tzinfo=UTC)
