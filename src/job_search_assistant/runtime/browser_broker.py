from __future__ import annotations

import json
import fcntl
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from job_search_assistant.capture.live_capture import codex_live_capture_company_name, codex_live_capture_job_url
from job_search_assistant.runtime.browser_window import BrowserWindowLease
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


@dataclass(frozen=True)
class BrowserPreflightResult:
    node_id: str
    lane_name: str
    model: str
    checked_at_utc: str
    marker_path: Path
    cached: bool
    observed_app: str
    observed_url: str
    observed_title: str


class BrowserPreflightError(RuntimeError):
    def __init__(self, *, code: str, detail: str, remediation: str) -> None:
        self.code = code
        self.detail = detail
        self.remediation = remediation
        super().__init__(f"{detail} Remediation: {remediation}")


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

    def preflight(self, *, model: str, force: bool = False) -> BrowserPreflightResult:
        marker_path = self._preflight_marker_path()
        if not self.settings.preflight_required:
            result = BrowserPreflightResult(
                node_id=self.settings.node_id,
                lane_name=self.settings.lane_name,
                model=model,
                checked_at_utc=_utc_now(),
                marker_path=marker_path,
                cached=False,
                observed_app="",
                observed_url="",
                observed_title="",
            )
            logger.info(
                format_kv(
                    "browser_broker.preflight.skipped",
                    node_id=self.settings.node_id,
                    lane_name=self.settings.lane_name,
                    reason="disabled_by_config",
                )
            )
            return result

        if not force:
            cached = self._load_cached_preflight(marker_path=marker_path, model=model)
            if cached is not None:
                logger.info(
                    format_kv(
                        "browser_broker.preflight.cached",
                        node_id=self.settings.node_id,
                        lane_name=self.settings.lane_name,
                        model=model,
                        checked_at_utc=cached.checked_at_utc,
                        marker_path=marker_path,
                    )
                )
                return cached

        logger.info(
            format_kv(
                "browser_broker.preflight.start",
                node_id=self.settings.node_id,
                lane_name=self.settings.lane_name,
                model=model,
                force=force,
            )
        )
        self._ensure_codex_available()
        self._check_chrome_window_control()
        probe = self._check_codex_computer_use(model=model)
        result = BrowserPreflightResult(
            node_id=self.settings.node_id,
            lane_name=self.settings.lane_name,
            model=model,
            checked_at_utc=_utc_now(),
            marker_path=marker_path,
            cached=False,
            observed_app=str(probe.get("frontmost_app") or ""),
            observed_url=str(probe.get("observed_url") or ""),
            observed_title=str(probe.get("observed_title") or ""),
        )
        marker_path.write_text(
            json.dumps(
                {
                    "node_id": result.node_id,
                    "lane_name": result.lane_name,
                    "model": result.model,
                    "checked_at_utc": result.checked_at_utc,
                    "observed_app": result.observed_app,
                    "observed_url": result.observed_url,
                    "observed_title": result.observed_title,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        logger.info(
            format_kv(
                "browser_broker.preflight.done",
                node_id=result.node_id,
                lane_name=result.lane_name,
                model=result.model,
                checked_at_utc=result.checked_at_utc,
                observed_app=result.observed_app,
                observed_url=result.observed_url,
                marker_path=marker_path,
            )
        )
        return result

    def _lease(self, *, task_kind: str, task_ref: str) -> AbstractContextManager[BrowserTaskLease]:
        return _BrowserLaneLeaseContext(
            settings=self.settings,
            runtime_store=self.runtime_store,
            task_kind=task_kind,
            task_ref=task_ref,
        )

    def _ensure_codex_available(self) -> str:
        codex_bin = shutil.which("codex")
        if not codex_bin:
            raise BrowserPreflightError(
                code="codex_cli_missing",
                detail="Codex CLI is not installed or not on PATH.",
                remediation="请先确认 Codex.app 已安装，并且 PATH 中包含 Codex CLI 路径。",
            )
        return codex_bin

    def _check_chrome_window_control(self) -> None:
        try:
            with BrowserWindowLease(task_name="browser.preflight.window_control", initial_url="about:blank"):
                pass
        except Exception as exc:
            raise BrowserPreflightError(
                code="chrome_window_control_failed",
                detail=f"Chrome automation warm-up failed: {exc}",
                remediation=(
                    "请前往 macOS 系统设置 -> 隐私与安全性，确认当前终端/Codex 对 Google Chrome 的自动化控制权限已允许，"
                    "并保证桌面已解锁、Chrome 可被正常打开。"
                ),
            ) from exc

    def _check_codex_computer_use(self, *, model: str) -> dict:
        codex_bin = self._ensure_codex_available()
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "status": {"type": "string"},
                "frontmost_app": {"type": "string"},
                "observed_url": {"type": "string"},
                "observed_title": {"type": "string"},
            },
            "required": ["status", "frontmost_app", "observed_url", "observed_title"],
        }
        prompt = (
            "你现在在执行 Browser Execution Broker 的权限预热。\n"
            "你必须使用 Computer Use 操作当前已经打开并置顶的 Chrome 自动化窗口。\n"
            "任务要求：\n"
            "- 确认前台应用是 Chrome。\n"
            "- 读取当前页面可见的 URL 或标题（当前页面应为 https://example.com/）。\n"
            "- 不要搜索，不要打开其他网站，不要做业务抓取。\n"
            "- 最终只输出符合 schema 的 JSON。\n"
        )
        try:
            with BrowserWindowLease(
                task_name="browser.preflight.codex_computer_use",
                initial_url="https://example.com/",
            ) as lease:
                full_prompt = f"{lease.prompt_hint()}\n\n{prompt}".strip()
                with tempfile.TemporaryDirectory(prefix="browser-preflight-") as temp_dir:
                    temp_root = Path(temp_dir)
                    schema_path = temp_root / "schema.json"
                    output_path = temp_root / "last_message.json"
                    schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
                    command = [
                        codex_bin,
                        "exec",
                        "-C",
                        str(temp_root),
                        "--skip-git-repo-check",
                        "--sandbox",
                        "read-only",
                        "--ephemeral",
                        "--output-schema",
                        str(schema_path),
                        "-o",
                        str(output_path),
                        "-m",
                        model,
                        "-",
                    ]
                    result = subprocess.run(
                        command,
                        input=full_prompt,
                        text=True,
                        capture_output=True,
                        timeout=self.settings.preflight_codex_timeout_seconds,
                        check=False,
                    )
                    if result.returncode != 0:
                        combined = "\n".join(
                            part.strip()
                            for part in (result.stdout, result.stderr)
                            if part and part.strip()
                        )
                        raise BrowserPreflightError(
                            code="codex_computer_use_failed",
                            detail=f"Codex Computer Use preflight failed with code {result.returncode}: {combined}",
                            remediation=(
                                "请重新打开 Codex，并在弹出系统权限框时依次允许 Computer Use / Automation / Accessibility 相关权限。"
                            ),
                        )
                    if not output_path.exists():
                        raise BrowserPreflightError(
                            code="codex_preflight_missing_output",
                            detail="Codex Computer Use preflight finished without writing output JSON.",
                            remediation="请重新运行 browser preflight；如果仍失败，请检查 Codex CLI 与 Computer Use 是否工作正常。",
                        )
                    payload = json.loads(output_path.read_text(encoding="utf-8").strip())
        except subprocess.TimeoutExpired as exc:
            raise BrowserPreflightError(
                code="codex_computer_use_timeout",
                detail=(
                    "Codex Computer Use preflight timed out while waiting for desktop interaction. "
                    "这通常表示系统权限弹窗尚未被人工允许。"
                ),
                remediation=(
                    "请回到桌面，完成 macOS 弹出的 Codex/Computer Use 权限授权，然后重新运行 browser preflight。"
                ),
            ) from exc
        except BrowserPreflightError:
            raise
        except Exception as exc:
            raise BrowserPreflightError(
                code="codex_computer_use_probe_failed",
                detail=f"Codex Computer Use preflight failed unexpectedly: {exc}",
                remediation="请确认 Codex CLI 已登录、桌面已解锁，并重新运行 browser preflight。",
            ) from exc

        if str(payload.get("status")).lower() not in {"ok", "success"}:
            raise BrowserPreflightError(
                code="codex_preflight_invalid_payload",
                detail=f"Codex Computer Use preflight returned unexpected payload: {payload}",
                remediation="请重新运行 browser preflight；如果重复失败，请检查 Codex Computer Use 权限是否完整。",
            )
        return payload

    def _preflight_marker_path(self) -> Path:
        filename = f"preflight_{self.settings.node_id}_{self.settings.lane_name}.json".replace(":", "_")
        return self.settings.lock_dir / filename

    def _load_cached_preflight(self, *, marker_path: Path, model: str) -> BrowserPreflightResult | None:
        if not marker_path.exists():
            return None
        try:
            payload = json.loads(marker_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return BrowserPreflightResult(
            node_id=str(payload.get("node_id") or self.settings.node_id),
            lane_name=str(payload.get("lane_name") or self.settings.lane_name),
            model=str(payload.get("model") or model),
            checked_at_utc=str(payload.get("checked_at_utc") or ""),
            marker_path=marker_path,
            cached=True,
            observed_app=str(payload.get("observed_app") or ""),
            observed_url=str(payload.get("observed_url") or ""),
            observed_title=str(payload.get("observed_title") or ""),
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
