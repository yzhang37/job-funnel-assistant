from __future__ import annotations

import subprocess
from decimal import Decimal
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from job_search_assistant.runtime.config_files import ensure_config_file
from job_search_assistant.runtime.mysql_runtime import TIMESTAMP_FORMAT, MySQLRuntimeStore
from job_search_assistant.tracker_scheduler import TrackerScheduler, load_tracker_config
from job_search_assistant.tracker_scheduler.storage import MySQLTrackerStateStore


RUNTIME_LABEL_PREFIX = "com.yzhang.jobfunnel.runtime"
JOB_TABLES = {
    "capture": "capture_jobs",
    "analyzer": "analysis_jobs",
    "output": "output_jobs",
}
LOG_SERVICES = {"manual-intake", "capture", "analyzer", "output", "tracker"}
LOG_STREAMS = {"out", "err"}


class TaskManagerQueryService:
    def __init__(self, *, repo_root: Path, runtime_store: MySQLRuntimeStore, node_id: str) -> None:
        self.repo_root = repo_root
        self.runtime_store = runtime_store
        self.node_id = node_id

    def overview(self) -> dict[str, Any]:
        return {
            "generated_at": _utcnow_text(),
            "node_id": self.node_id,
            "launch_agents": list_runtime_launch_agents(),
            "worker_controls": self.worker_controls(),
            "job_counts": {
                component: self.job_counts(component)
                for component in ("capture", "analyzer", "output")
            },
            "tracker_request_counts": self.tracker_request_counts(),
            "tracker_run_summary": self.tracker_run_summary(limit=10),
            "cache_summary": self.cache_summary(),
            "browser_leases": self.browser_leases(active_only=True),
            "recent_errors": {
                "capture": self.jobs("capture", status="failed", limit=5),
                "analyzer": self.jobs("analyzer", status="failed", limit=5),
                "output": self.jobs("output", status="failed", limit=5),
                "tracker": self.tracker_errors(limit=5),
            },
        }

    def trackers(self, *, config_path: str = "config/trackers.toml") -> dict[str, Any]:
        tracker_config_path = ensure_config_file(self.repo_root, config_path)
        tracker_config = load_tracker_config(tracker_config_path)
        scheduler = TrackerScheduler(tracker_config, MySQLTrackerStateStore(self.runtime_store))
        due_by_id = {item.tracker.id: item.to_payload() for item in scheduler.list_due_trackers()}
        latest_runs = {
            str(row["tracker_id"]): row
            for row in self._fetchall(
                """
                SELECT tracker_id, started_at, finished_at, status, target_new_jobs,
                       submitted_count, unique_submitted_count, tracker_new_count, global_new_count
                FROM tracker_runs
                WHERE run_id IN (
                  SELECT MAX(run_id)
                  FROM tracker_runs
                  GROUP BY tracker_id
                )
                """
            )
        }
        aggregates = {
            str(row["tracker_id"]): row
            for row in self._fetchall(
                """
                SELECT tracker_id,
                       COUNT(*) AS run_count,
                       SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
                       SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) AS failure_count,
                       SUM(tracker_new_count) AS tracker_new_count,
                       SUM(global_new_count) AS global_new_count
                FROM tracker_runs
                GROUP BY tracker_id
                """
            )
        }
        active_requests = {
            str(row["tracker_id"]): row
            for row in self._fetchall(
                """
                SELECT tracker_id, request_id, status, priority, due_reason,
                       admitted_at, started_at, stale_after, last_error
                FROM tracker_discovery_requests
                WHERE status IN ('queued', 'running')
                ORDER BY admitted_at DESC
                """
            )
        }

        trackers = []
        for tracker in tracker_config.trackers:
            trackers.append(
                {
                    **tracker.to_payload(),
                    "due": tracker.id in due_by_id,
                    "due_detail": due_by_id.get(tracker.id),
                    "latest_run": latest_runs.get(tracker.id),
                    "summary": aggregates.get(tracker.id),
                    "active_request": active_requests.get(tracker.id),
                }
            )

        return {
            "config_path": str(tracker_config_path),
            "tracker_count": len(trackers),
            "enabled_count": sum(1 for item in trackers if item["enabled"]),
            "due_count": sum(1 for item in trackers if item["due"]),
            "trackers": trackers,
        }

    def jobs(self, component: str, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        table = _job_table(component)
        normalized_limit = sanitize_limit(limit)
        where = ""
        params: list[Any] = []
        if status:
            where = "WHERE status = %s"
            params.append(status)
        return self._fetchall(
            f"""
            SELECT *
            FROM {table}
            {where}
            ORDER BY updated_at DESC
            LIMIT {normalized_limit}
            """,
            tuple(params),
        )

    def job_counts(self, component: str) -> dict[str, int]:
        table = _job_table(component)
        rows = self._fetchall(
            f"""
            SELECT status, COUNT(*) AS count
            FROM {table}
            GROUP BY status
            ORDER BY status
            """
        )
        return {str(row["status"]): int(row["count"]) for row in rows}

    def cache_entries(self, *, namespace: str | None = None, limit: int = 100) -> dict[str, Any]:
        normalized_limit = sanitize_limit(limit, default=100, maximum=500)
        where = ""
        params: list[Any] = []
        if namespace:
            where = "WHERE namespace = %s"
            params.append(namespace)
        rows = self._fetchall(
            f"""
            SELECT namespace, subject_key, field_name, source_platform, source_url,
                   observed_at, fresh_until, stale_until, updated_at
            FROM capture_cache_entries
            {where}
            ORDER BY updated_at DESC
            LIMIT {normalized_limit}
            """,
            tuple(params),
        )
        now = datetime.now(UTC)
        return {
            "generated_at": _utcnow_text(),
            "namespace": namespace,
            "summary": self.cache_summary(),
            "entries": [
                {
                    **row,
                    "ttl_state": cache_ttl_state(
                        fresh_until=str(row["fresh_until"]),
                        stale_until=str(row["stale_until"]),
                        now=now,
                    ),
                }
                for row in rows
            ],
        }

    def cache_summary(self) -> dict[str, Any]:
        rows = self._fetchall(
            """
            SELECT namespace,
                   COUNT(*) AS entry_count,
                   COUNT(DISTINCT subject_key) AS subject_count,
                   MIN(observed_at) AS oldest_observed_at,
                   MAX(observed_at) AS newest_observed_at
            FROM capture_cache_entries
            GROUP BY namespace
            ORDER BY namespace
            """
        )
        return {"namespaces": rows, "total_entries": sum(int(row["entry_count"]) for row in rows)}

    def invalidate_cache_entry(
        self,
        *,
        namespace: str,
        subject_key: str,
        field_name: str,
        source_platform: str = "",
    ) -> int:
        with self.runtime_store.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM capture_cache_entries
                WHERE namespace = %s
                  AND subject_key = %s
                  AND field_name = %s
                  AND source_platform = %s
                """,
                (namespace, subject_key, field_name, source_platform),
            )
            deleted = int(cursor.rowcount or 0)
            cursor.close()
        return deleted

    def set_worker_control(
        self,
        *,
        component_name: str,
        worker_id: str,
        desired_state: str,
        node_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if desired_state not in {"running", "paused", "drain-current", "stopped"}:
            raise ValueError("desired_state must be one of: running, paused, drain-current, stopped")
        target_node_id = node_id or self.node_id
        shutdown_mode = "drain-current" if desired_state == "drain-current" else None
        self.runtime_store.set_worker_control(
            component_name=component_name,
            node_id=target_node_id,
            worker_id=worker_id,
            desired_state=desired_state,
            shutdown_mode=shutdown_mode,
            reason=reason or "task manager",
        )
        return {
            "component_name": component_name,
            "node_id": target_node_id,
            "worker_id": worker_id,
            "desired_state": desired_state,
            "shutdown_mode": shutdown_mode,
        }

    def worker_controls(self) -> list[dict[str, Any]]:
        return self._fetchall(
            """
            SELECT component_name, node_id, worker_id, desired_state,
                   shutdown_mode, reason, updated_at
            FROM runtime_worker_controls
            ORDER BY component_name, node_id, worker_id
            """
        )

    def browser_leases(self, *, active_only: bool = False) -> list[dict[str, Any]]:
        now_text = _utcnow_text()
        where = "WHERE leased_until > %s" if active_only else ""
        params = (now_text,) if active_only else ()
        return self._fetchall(
            f"""
            SELECT lane_key, holder_id, node_id, task_kind, task_ref,
                   leased_until, heartbeat_at, updated_at
            FROM browser_broker_leases
            {where}
            ORDER BY updated_at DESC
            """,
            params,
        )

    def tracker_request_counts(self) -> dict[str, int]:
        rows = self._fetchall(
            """
            SELECT status, COUNT(*) AS count
            FROM tracker_discovery_requests
            GROUP BY status
            ORDER BY status
            """
        )
        return {str(row["status"]): int(row["count"]) for row in rows}

    def tracker_run_summary(self, *, limit: int = 20) -> list[dict[str, Any]]:
        normalized_limit = sanitize_limit(limit)
        return self._fetchall(
            f"""
            SELECT tracker_id,
                   COUNT(*) AS run_count,
                   SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
                   SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) AS failure_count,
                   SUM(tracker_new_count) AS tracker_new_count,
                   SUM(global_new_count) AS global_new_count,
                   MAX(finished_at) AS last_finished_at
            FROM tracker_runs
            GROUP BY tracker_id
            ORDER BY last_finished_at DESC
            LIMIT {normalized_limit}
            """
        )

    def tracker_errors(self, *, limit: int = 20) -> list[dict[str, Any]]:
        normalized_limit = sanitize_limit(limit)
        return self._fetchall(
            f"""
            SELECT request_id, tracker_id, status, due_reason,
                   admitted_at, started_at, finished_at, last_error
            FROM tracker_discovery_requests
            WHERE status IN ('failed', 'expired')
            ORDER BY updated_at DESC
            LIMIT {normalized_limit}
            """
        )

    def log_tail(self, *, service: str, stream: str, limit: int = 200) -> dict[str, Any]:
        if service not in LOG_SERVICES:
            raise ValueError(f"Unsupported service: {service}")
        if stream not in LOG_STREAMS:
            raise ValueError(f"Unsupported stream: {stream}")
        normalized_limit = sanitize_limit(limit, default=200, maximum=1000)
        path = self.repo_root / "data" / "logs" / "runtime" / f"{service}.{stream}.log"
        if not path.exists():
            return {"path": str(path), "lines": []}
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return {"path": str(path), "lines": lines[-normalized_limit:]}

    def _fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.runtime_store.connect() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            cursor.close()
        return [_json_safe_row(row) for row in rows]


def list_runtime_launch_agents() -> list[dict[str, Any]]:
    result = subprocess.run(["launchctl", "list"], check=False, capture_output=True, text=True)
    if result.returncode != 0:
        return [{"error": result.stderr.strip() or f"launchctl exited {result.returncode}"}]
    return parse_launchctl_list(result.stdout)


def parse_launchctl_list(output: str) -> list[dict[str, Any]]:
    agents = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[0] == "PID":
            continue
        label = parts[2]
        if not label.startswith(RUNTIME_LABEL_PREFIX):
            continue
        agents.append(
            {
                "pid": None if parts[0] == "-" else int(parts[0]),
                "last_exit_status": None if parts[1] == "-" else int(parts[1]),
                "label": label,
                "component": label.removeprefix(f"{RUNTIME_LABEL_PREFIX}."),
            }
        )
    return agents


def cache_ttl_state(*, fresh_until: str, stale_until: str, now: datetime | None = None) -> str:
    current = now or datetime.now(UTC)
    fresh = _from_text(fresh_until)
    stale = _from_text(stale_until)
    if current <= fresh:
        return "fresh"
    if current <= stale:
        return "stale"
    return "expired"


def sanitize_limit(limit: int | str | None, *, default: int = 50, maximum: int = 200) -> int:
    try:
        parsed = int(limit) if limit is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


def _job_table(component: str) -> str:
    try:
        return JOB_TABLES[component]
    except KeyError as exc:
        raise ValueError(f"Unsupported job component: {component}") from exc


def _json_safe_row(row: dict[str, Any]) -> dict[str, Any]:
    safe = {}
    for key, value in row.items():
        if isinstance(value, datetime):
            safe[key] = value.astimezone(UTC).strftime(TIMESTAMP_FORMAT)
        elif isinstance(value, Decimal):
            safe[key] = int(value) if value == value.to_integral_value() else float(value)
        else:
            safe[key] = value
    return safe


def _from_text(value: str) -> datetime:
    return datetime.strptime(value, TIMESTAMP_FORMAT).replace(tzinfo=UTC)


def _utcnow_text() -> str:
    return datetime.now(UTC).replace(microsecond=0).strftime(TIMESTAMP_FORMAT)
