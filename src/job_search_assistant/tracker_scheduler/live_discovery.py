from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from job_search_assistant.runtime import BrowserWindowLease, format_kv, get_logger

from .browser import BrowserDiscoverySession
from .models import TrackerDefinition, TrackerDiscoveryBatch, TrackerDiscoverySummary
from .service import TrackerScheduler


TRACKER_DISCOVERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "raw_job_urls": {
            "type": "array",
            "items": {"type": "string"},
        },
        "source_exhausted": {"type": "boolean"},
        "notes": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["raw_job_urls", "source_exhausted", "notes"],
}

logger = get_logger("tracker.live")


@dataclass(frozen=True)
class LiveTrackerDiscoveryResult:
    tracker: TrackerDefinition
    batch: TrackerDiscoveryBatch
    summary: TrackerDiscoverySummary | None
    raw_job_urls: list[str]
    source_exhausted: bool
    notes: list[str]

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tracker": self.tracker.to_payload(),
            "batch": self.batch.to_payload(),
            "raw_job_urls": list(self.raw_job_urls),
            "source_exhausted": self.source_exhausted,
            "notes": list(self.notes),
        }
        if self.summary is not None:
            payload["summary"] = self.summary.to_payload()
        return payload


def run_live_tracker_discovery(
    *,
    scheduler: TrackerScheduler,
    tracker_id: str,
    model: str = "gpt-5.4",
    max_attempts: int = 2,
    target_new_jobs_override: int | None = None,
    record_run: bool = True,
) -> LiveTrackerDiscoveryResult:
    base_tracker = scheduler.config.get_tracker(tracker_id)
    tracker = (
        replace(base_tracker, target_new_jobs=target_new_jobs_override)
        if target_new_jobs_override is not None
        else base_tracker
    )
    session = BrowserDiscoverySession(tracker=tracker, store=scheduler.store)

    payload = codex_live_discover_tracker_urls(
        tracker=tracker,
        model=model,
        max_attempts=max_attempts,
    )
    raw_job_urls = [str(item).strip() for item in payload.get("raw_job_urls", []) if str(item).strip()]
    source_exhausted = bool(payload.get("source_exhausted", False))
    notes = [str(item).strip() for item in payload.get("notes", []) if str(item).strip()]

    batch = session.ingest_raw_job_urls(raw_job_urls, source_exhausted=source_exhausted)
    summary = None
    if record_run:
        summary = scheduler.record_discovery(
            tracker_id=tracker.id,
            job_urls=batch.canonical_job_urls,
            status="success",
        )

    logger.info(
        format_kv(
            "tracker.live.run.done",
            tracker_id=tracker.id,
            submitted_count=len(raw_job_urls),
            canonical_count=batch.canonical_count,
            new_count=len(batch.new_job_urls),
            existing_count=len(batch.existing_job_urls),
            remaining_target_new_jobs=batch.remaining_target_new_jobs,
            source_exhausted=source_exhausted,
            recorded=record_run,
        )
    )
    return LiveTrackerDiscoveryResult(
        tracker=tracker,
        batch=batch,
        summary=summary,
        raw_job_urls=raw_job_urls,
        source_exhausted=source_exhausted,
        notes=notes,
    )


def codex_live_discover_tracker_urls(
    *,
    tracker: TrackerDefinition,
    model: str = "gpt-5.4",
    max_attempts: int = 2,
) -> dict[str, Any]:
    logger.info(
        format_kv(
            "tracker.live.requested",
            tracker_id=tracker.id,
            model=model,
            max_attempts=max_attempts,
            target_new_jobs=tracker.target_new_jobs,
            tracker_url=tracker.url,
        )
    )
    codex_bin = shutil.which("codex")
    if not codex_bin:
        logger.error(format_kv("tracker.live.codex_missing", tracker_id=tracker.id))
        raise RuntimeError("codex CLI is not installed or not on PATH.")

    last_error: RuntimeError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(
                format_kv(
                    "tracker.live.attempt.start",
                    tracker_id=tracker.id,
                    attempt=attempt,
                    codex_bin=codex_bin,
                )
            )
            payload = _run_codex_tracker_once(
                codex_bin=codex_bin,
                tracker=tracker,
                model=model,
            )
            logger.info(
                format_kv(
                    "tracker.live.attempt.done",
                    tracker_id=tracker.id,
                    attempt=attempt,
                    raw_url_count=len(payload.get("raw_job_urls", [])),
                    source_exhausted=payload.get("source_exhausted", False),
                )
            )
            return payload
        except RuntimeError as exc:
            last_error = exc
            logger.warning(
                format_kv(
                    "tracker.live.attempt.failed",
                    tracker_id=tracker.id,
                    attempt=attempt,
                    error=str(exc),
                )
            )
            if attempt >= max_attempts:
                break
    assert last_error is not None
    raise last_error


def _run_codex_tracker_once(
    *,
    codex_bin: str,
    tracker: TrackerDefinition,
    model: str,
) -> dict[str, Any]:
    started = time.monotonic()
    with BrowserWindowLease(task_name=f"tracker.{tracker.id}", initial_url=tracker.url) as lease:
        prompt_text = f"{lease.prompt_hint()}\n\n{_build_tracker_discovery_prompt(tracker)}".strip()
        with tempfile.TemporaryDirectory(prefix="codex-tracker-") as temp_dir:
            temp_root = Path(temp_dir)
            schema_path = temp_root / "output_schema.json"
            schema_path.write_text(json.dumps(TRACKER_DISCOVERY_SCHEMA, ensure_ascii=False, indent=2), encoding="utf-8")
            output_path = temp_root / "last_message.json"

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
                input=prompt_text,
                text=True,
                capture_output=True,
                timeout=900,
                check=False,
            )
            if result.returncode != 0:
                combined = "\n".join(
                    part.strip()
                    for part in (result.stdout, result.stderr)
                    if part and part.strip()
                )
                raise RuntimeError(f"codex tracker live discovery failed with code {result.returncode}: {combined}")
            if not output_path.exists():
                raise RuntimeError("codex tracker live discovery finished without writing the last-message file.")
            raw = output_path.read_text(encoding="utf-8").strip()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Codex tracker live discovery returned non-JSON output: {raw}") from exc

    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(format_kv("tracker.live.exec.done", tracker_id=tracker.id, duration_ms=duration_ms))
    return payload


def _build_tracker_discovery_prompt(tracker: TrackerDefinition) -> str:
    return f"""你现在是本地求职工作流里的 Tracker 执行器。

目标：
- 输入是一个 tracker 搜索结果页 URL。
- 你必须使用 Computer Use 操作已经打开好的 Chrome 自动化窗口。
- 你只做 discovery：收集主结果列表里的岗位原始 URL。
- 不抓 JD 正文，不抓公司画像，不做分析，不投递，不发消息。

当前 tracker：
- id: {tracker.id}
- label: {tracker.label}
- url: {tracker.url}
- target_new_jobs: {tracker.target_new_jobs}

执行要求：
1. 只使用主结果列表（vertical results list）。
2. 忽略 horizontal carousel、related jobs、detail sidebar recommendations。
3. 点击岗位卡片后，从地址栏读取当前原始 URL。
4. 对 LinkedIn，可接受：
   - `search-results?...currentJobId=<job_id>`
   - `/jobs/view/<job_id>/...`
5. 对 Indeed，可接受：
   - `search?...vjk=<job_id>`
   - `search?...jk=<job_id>`
   - `/viewjob?jk=<job_id>`
6. 尽量翻页，直到你收集到至少 {tracker.target_new_jobs} 条原始岗位 URL，或者确认结果耗尽。
7. 如果结果页不够，就把 `source_exhausted` 设为 true。
8. 如果 4 到 5 分钟内没有更多有效岗位 URL，就尽快返回部分结果。

输出要求：
- `raw_job_urls`: 按你观察到的顺序返回原始 URL 列表
- `source_exhausted`: 是否已经到底
- `notes`: 简短说明，例如翻到了第几页、是否遇到 skeleton loading、是否有页面限制

最终只输出符合 schema 的 JSON，不要输出 markdown，不要输出解释。
""".strip()
