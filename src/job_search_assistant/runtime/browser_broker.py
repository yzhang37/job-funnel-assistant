from __future__ import annotations

import fcntl
import os
import time
import uuid
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from job_search_assistant.capture.live_capture import codex_live_capture_company_name, codex_live_capture_job_url
from job_search_assistant.runtime.logging import format_kv, get_logger
from job_search_assistant.tracker_scheduler.live_discovery import codex_live_discover_tracker_urls

from .config import BrowserBrokerSettings
from .mysql_runtime import MySQLRuntimeStore


logger = get_logger("runtime.browser_broker")


class BrowserExecutionBroker(Protocol):
    def capture_job_url(self, *, job_url: str, model: str, max_attempts: int = 2) -> dict:
        ...

    def capture_company_name(
        self,
        *,
        company_name: str,
        model: str,
        job_url: str | None = None,
        jd_text: str | None = None,
        max_attempts: int = 2,
    ) -> dict:
        ...

    def discover_tracker_urls(self, *, tracker, model: str, max_attempts: int = 2) -> dict:
        ...


@dataclass(frozen=True)
class BrowserTaskLease:
    lane_key: str
    holder_id: str
    lock_path: Path


class CodexComputerUseBroker:
    def __init__(self, *, settings: BrowserBrokerSettings, runtime_store: MySQLRuntimeStore | None = None) -> None:
        self.settings = settings
        self.runtime_store = runtime_store
        self.settings.lock_dir.mkdir(parents=True, exist_ok=True)

    def capture_job_url(self, *, job_url: str, model: str, max_attempts: int = 2) -> dict:
        with self._lease(task_kind="capture_job_url", task_ref=job_url):
            logger.info(format_kv("browser_broker.capture_job_url.start", job_url=job_url, model=model))
            payload = codex_live_capture_job_url(job_url=job_url, model=model, max_attempts=max_attempts)
            logger.info(format_kv("browser_broker.capture_job_url.done", job_url=job_url, model=model))
            return payload

    def capture_company_name(
        self,
        *,
        company_name: str,
        model: str,
        job_url: str | None = None,
        jd_text: str | None = None,
        max_attempts: int = 2,
    ) -> dict:
        with self._lease(task_kind="capture_company_name", task_ref=company_name):
            logger.info(
                format_kv(
                    "browser_broker.capture_company_name.start",
                    company_name=company_name,
                    model=model,
                    job_url=job_url,
                    has_jd_text=bool(jd_text),
                )
            )
            payload = codex_live_capture_company_name(
                company_name=company_name,
                model=model,
                job_url=job_url,
                jd_text=jd_text,
                max_attempts=max_attempts,
            )
            logger.info(format_kv("browser_broker.capture_company_name.done", company_name=company_name, model=model))
            return payload

    def discover_tracker_urls(self, *, tracker, model: str, max_attempts: int = 2) -> dict:
        with self._lease(task_kind="tracker_discovery", task_ref=getattr(tracker, "id", "unknown")):
            logger.info(
                format_kv(
                    "browser_broker.tracker_discovery.start",
                    tracker_id=getattr(tracker, "id", "unknown"),
                    model=model,
                    target_new_jobs=getattr(tracker, "target_new_jobs", None),
                )
            )
            payload = codex_live_discover_tracker_urls(tracker=tracker, model=model, max_attempts=max_attempts)
            logger.info(
                format_kv(
                    "browser_broker.tracker_discovery.done",
                    tracker_id=getattr(tracker, "id", "unknown"),
                    raw_url_count=len(payload.get("raw_job_urls", [])),
                )
            )
            return payload

    def _lease(self, *, task_kind: str, task_ref: str) -> AbstractContextManager[BrowserTaskLease]:
        return _BrowserLaneLeaseContext(
            settings=self.settings,
            runtime_store=self.runtime_store,
            task_kind=task_kind,
            task_ref=task_ref,
        )


class _BrowserLaneLeaseContext(AbstractContextManager[BrowserTaskLease]):
    def __init__(
        self,
        *,
        settings: BrowserBrokerSettings,
        runtime_store: MySQLRuntimeStore | None,
        task_kind: str,
        task_ref: str,
    ) -> None:
        self.settings = settings
        self.runtime_store = runtime_store
        self.task_kind = task_kind
        self.task_ref = task_ref
        self.holder_id = str(uuid.uuid4())
        self.lock_file = None
        self.lease: BrowserTaskLease | None = None

    def __enter__(self) -> BrowserTaskLease:
        lane_key = f"{self.settings.node_id}:{self.settings.lane_name}"
        lock_path = self.settings.lock_dir / f"{lane_key.replace(':', '_')}.lock"
        self.lock_file = lock_path.open("a+", encoding="utf-8")
        started = time.monotonic()
        acquired = False
        while time.monotonic() - started < self.settings.acquire_timeout_seconds:
            try:
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                time.sleep(self.settings.poll_interval_seconds)
        if not acquired:
            self.lock_file.close()
            raise TimeoutError(f"Timed out acquiring browser broker lane {lane_key}.")
        if self.runtime_store is not None:
            if not self.runtime_store.acquire_browser_lease(
                lane_key=lane_key,
                holder_id=self.holder_id,
                node_id=self.settings.node_id,
                task_kind=self.task_kind,
                task_ref=self.task_ref,
                ttl_seconds=self.settings.acquire_timeout_seconds,
            ):
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                self.lock_file.close()
                raise TimeoutError(f"MySQL lease rejected browser lane {lane_key}.")
        self.lease = BrowserTaskLease(lane_key=lane_key, holder_id=self.holder_id, lock_path=lock_path)
        logger.info(
            format_kv(
                "browser_broker.lease.acquired",
                lane_key=lane_key,
                holder_id=self.holder_id,
                task_kind=self.task_kind,
                task_ref=self.task_ref,
            )
        )
        return self.lease

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.lease is not None and self.runtime_store is not None:
            self.runtime_store.release_browser_lease(lane_key=self.lease.lane_key, holder_id=self.lease.holder_id)
        if self.lease is not None:
            logger.info(
                format_kv(
                    "browser_broker.lease.released",
                    lane_key=self.lease.lane_key,
                    holder_id=self.holder_id,
                    task_kind=self.task_kind,
                    task_ref=self.task_ref,
                    had_error=exc is not None,
                )
            )
        if self.lock_file is not None:
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
            self.lock_file.close()
        self.lock_file = None
        self.lease = None
