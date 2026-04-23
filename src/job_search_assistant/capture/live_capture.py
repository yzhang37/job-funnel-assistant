from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from job_search_assistant.runtime import format_kv, get_logger


NARRATIVE_SECTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "heading": {"type": "string"},
        "paragraphs": {"type": "array", "items": {"type": "string"}},
        "bullets": {"type": "array", "items": {"type": "string"}},
        "sources": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["heading", "paragraphs", "bullets", "sources"],
}

RAW_SECTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "heading": {"type": "string"},
        "text": {"type": "string"},
        "source_label": {"type": "string"},
        "note": {"type": "string"},
    },
    "required": ["heading", "text", "source_label", "note"],
}

METRIC_ROW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "label": {"type": "string"},
        "cells": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "column": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["column", "value"],
            },
        },
    },
    "required": ["label", "cells"],
}

HEADLINE_METRIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        "value": {"type": ["string", "number", "boolean", "null"]},
    },
    "required": ["name", "value"],
}

METRIC_TABLE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "columns": {"type": "array", "items": {"type": "string"}},
        "rows": {"type": "array", "items": METRIC_ROW_SCHEMA},
        "note": {"type": "string"},
    },
    "required": ["title", "columns", "rows", "note"],
}

TIME_SERIES_POINT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "label": {"type": "string"},
        "value": {"type": "string"},
        "note": {"type": "string"},
    },
    "required": ["label", "value", "note"],
}

TIME_SERIES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "points": {"type": "array", "items": TIME_SERIES_POINT_SCHEMA},
        "note": {"type": "string"},
    },
    "required": ["title", "points", "note"],
}

ALUMNUS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        "degree": {"type": "string"},
        "current_role": {"type": "string"},
        "previous_role": {"type": "string"},
    },
    "required": ["name", "degree", "current_role", "previous_role"],
}

RELATED_PAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "label": {"type": "string"},
        "url": {"type": "string"},
        "relationship": {"type": "string"},
        "source": {"type": "string"},
        "note": {"type": "string"},
    },
    "required": ["label", "url", "relationship", "source", "note"],
}

SOURCE_SNAPSHOT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "label": {"type": "string"},
        "source_url": {"type": "string"},
        "source_platform": {"type": "string"},
        "source_kind": {"type": "string"},
        "headline_metrics": {
            "type": "array",
            "items": HEADLINE_METRIC_SCHEMA,
        },
        "bridge_signals": {"type": "array", "items": {"type": "string"}},
        "competitor_names": {"type": "array", "items": {"type": "string"}},
        "narrative_sections": {"type": "array", "items": NARRATIVE_SECTION_SCHEMA},
        "metric_tables": {"type": "array", "items": METRIC_TABLE_SCHEMA},
        "time_series": {"type": "array", "items": TIME_SERIES_SCHEMA},
        "notable_alumni": {"type": "array", "items": ALUMNUS_SCHEMA},
        "related_pages": {"type": "array", "items": RELATED_PAGE_SCHEMA},
        "available_signals": {"type": "array", "items": {"type": "string"}},
        "missing_signals": {"type": "array", "items": {"type": "string"}},
        "raw_sections": {"type": "array", "items": RAW_SECTION_SCHEMA},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "label",
        "source_url",
        "source_platform",
        "source_kind",
        "headline_metrics",
        "bridge_signals",
        "competitor_names",
        "narrative_sections",
        "metric_tables",
        "time_series",
        "notable_alumni",
        "related_pages",
        "available_signals",
        "missing_signals",
        "raw_sections",
        "notes",
    ],
}

JOB_POSTING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "company": {"type": "string"},
        "location": {"type": "string"},
        "source_platform": {"type": "string"},
        "source_url": {"type": "string"},
        "signals": {"type": "array", "items": {"type": "string"}},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "heading": {"type": "string"},
                    "paragraphs": {"type": "array", "items": {"type": "string"}},
                    "bullets": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["heading", "paragraphs", "bullets"],
            },
        },
        "compensation_text": {"type": "string"},
        "benefits": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "title",
        "company",
        "location",
        "source_platform",
        "source_url",
        "signals",
        "sections",
        "compensation_text",
        "benefits",
        "notes",
    ],
}

COMPANY_PROFILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "company_name": {"type": "string"},
        "source_url": {"type": "string"},
        "source_platform": {"type": "string"},
        "company_tagline": {"type": "string"},
        "company_description": {"type": "string"},
        "industry": {"type": "string"},
        "headquarters": {"type": "string"},
        "followers_text": {"type": "string"},
        "employee_size_text": {"type": "string"},
        "employees_on_platform_text": {"type": "string"},
        "featured_customers": {"type": "array", "items": {"type": "string"}},
        "bridge_signals": {"type": "array", "items": {"type": "string"}},
        "competitor_names": {"type": "array", "items": {"type": "string"}},
        "headline_metrics": {
            "type": "array",
            "items": HEADLINE_METRIC_SCHEMA,
        },
        "narrative_sections": {"type": "array", "items": NARRATIVE_SECTION_SCHEMA},
        "metric_tables": {"type": "array", "items": METRIC_TABLE_SCHEMA},
        "time_series": {"type": "array", "items": TIME_SERIES_SCHEMA},
        "notable_alumni": {"type": "array", "items": ALUMNUS_SCHEMA},
        "related_pages": {"type": "array", "items": RELATED_PAGE_SCHEMA},
        "available_signals": {"type": "array", "items": {"type": "string"}},
        "missing_signals": {"type": "array", "items": {"type": "string"}},
        "raw_sections": {"type": "array", "items": RAW_SECTION_SCHEMA},
        "source_snapshots": {"type": "array", "items": SOURCE_SNAPSHOT_SCHEMA},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "company_name",
        "source_url",
        "source_platform",
        "company_tagline",
        "company_description",
        "industry",
        "headquarters",
        "followers_text",
        "employee_size_text",
        "employees_on_platform_text",
        "featured_customers",
        "bridge_signals",
        "competitor_names",
        "headline_metrics",
        "narrative_sections",
        "metric_tables",
        "time_series",
        "notable_alumni",
        "related_pages",
        "available_signals",
        "missing_signals",
        "raw_sections",
        "source_snapshots",
        "notes",
    ],
}

LIVE_CAPTURE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "job_posting": JOB_POSTING_SCHEMA,
        "company_profile": COMPANY_PROFILE_SCHEMA,
    },
    "required": ["job_posting", "company_profile"],
}

COMPANY_PROFILE_CAPTURE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "company_profile": COMPANY_PROFILE_SCHEMA,
    },
    "required": ["company_profile"],
}

logger = get_logger("capture.live")


def codex_live_capture_job_url(
    *,
    job_url: str,
    model: str = "gpt-5.4",
    max_attempts: int = 2,
) -> dict[str, Any]:
    return _run_capture_with_retries(
        schema=LIVE_CAPTURE_SCHEMA,
        prompt_text=_build_job_capture_prompt(job_url),
        model=model,
        max_attempts=max_attempts,
        event_prefix="capture.live.job_url",
        log_fields={"job_url": job_url},
    )


def codex_live_capture_company_name(
    *,
    company_name: str,
    model: str = "gpt-5.4",
    job_url: str | None = None,
    jd_text: str | None = None,
    max_attempts: int = 2,
) -> dict[str, Any]:
    payload = _run_capture_with_retries(
        schema=COMPANY_PROFILE_CAPTURE_SCHEMA,
        prompt_text=_build_company_profile_prompt(
            company_name=company_name,
            job_url=job_url,
            jd_text=jd_text,
        ),
        model=model,
        max_attempts=max_attempts,
        event_prefix="capture.live.company_name",
        log_fields={
            "company_name": company_name,
            "job_url": job_url,
            "has_jd_text": bool(jd_text),
        },
    )
    return payload.get("company_profile") or {}


def _run_capture_with_retries(
    *,
    schema: dict[str, Any],
    prompt_text: str,
    model: str,
    max_attempts: int,
    event_prefix: str,
    log_fields: dict[str, Any],
) -> dict[str, Any]:
    logger.info(format_kv(f"{event_prefix}.requested", model=model, max_attempts=max_attempts, **log_fields))
    codex_bin = shutil.which("codex")
    if not codex_bin:
        logger.error(format_kv(f"{event_prefix}.codex_missing", **log_fields))
        raise RuntimeError("codex CLI is not installed or not on PATH.")

    last_error: RuntimeError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(
                format_kv(
                    f"{event_prefix}.attempt.start",
                    attempt=attempt,
                    codex_bin=codex_bin,
                    **log_fields,
                )
            )
            payload = _run_codex_capture_once(
                codex_bin=codex_bin,
                schema=schema,
                prompt_text=prompt_text,
                model=model,
            )
            logger.info(format_kv(f"{event_prefix}.attempt.done", attempt=attempt, **log_fields))
            return payload
        except RuntimeError as exc:
            last_error = exc
            logger.warning(
                format_kv(
                    f"{event_prefix}.attempt.failed",
                    attempt=attempt,
                    error=str(exc),
                    **log_fields,
                )
            )
            if attempt >= max_attempts:
                break

    assert last_error is not None
    raise last_error


def _run_codex_capture_once(
    *,
    codex_bin: str,
    schema: dict[str, Any],
    prompt_text: str,
    model: str,
) -> dict[str, Any]:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="codex-capture-") as temp_dir:
        temp_root = Path(temp_dir)
        schema_path = temp_root / "output_schema.json"
        schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
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
            raise RuntimeError(f"codex live capture failed with code {result.returncode}: {combined}")
        if not output_path.exists():
            raise RuntimeError("codex live capture finished without writing the last-message file.")
        raw = output_path.read_text(encoding="utf-8").strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Codex live capture returned non-JSON output: {raw}") from exc

    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(format_kv("capture.live.exec.done", duration_ms=duration_ms))
    return payload


def _build_job_capture_prompt(job_url: str) -> str:
    return f"""你现在是本地求职工作流里的 Capture 执行器。

目标：
- 输入是一个岗位 URL。
- 你必须使用 Computer Use 打开 Chrome，访问这个 URL，并抓取足够的信息来生成完整 bundle 所需的岗位信息和公司画像。
- 你只做抓取，不做分析，不申请，不点击投递，不发消息。

当前岗位链接：
{job_url}

抓取优先级：
1. 先抓当前岗位页本身的 JD 与 source-native 公司信号。
2. 再抓当前页能直接到达的公司资料/公司卡片/公司简介。
3. 只要能识别到 LinkedIn 公司实体，就应默认补抓 LinkedIn 公司页；若能进入 `/company/<slug>/insights/` 或等价 insights 页面，也应抓取。
4. 如岗位页或公司页能看到官网 / careers 入口，再补一层 official signals。
5. 保留来源分层。不要把不同来源混成一坨；尽量把每一跳的证据放进 `source_snapshots`。

执行边界：
- 最多处理 3 个来源页面：当前岗位页 / 一个 LinkedIn 公司来源 / 一个 official 来源。
- 如果某个来源很难进入，就跳过并在 `missing_signals` / `notes` 中说明，不要无限尝试。
- 如果 4 到 5 分钟内拿不到更多高价值信号，就立刻收尾并输出 partial-but-structured JSON。
- 优先“快速、完整地返回结构化证据”，不要为了追求完美信息而长时间卡住。

特别要求：
- 重点抓这些高价值 company insights（如果页面上存在）：
  - Total employee count
  - 6m / 1y / 2y growth
  - Median employee tenure
  - Employee distribution / headcount growth by function
  - Total job openings / openings by function
  - Notable alumni
  - Affiliated pages / related pages
- 如果拿不到这些字段，不要脑补；写进 `missing_signals`。
- 返回要尽可能完整，而不是过度摘要。

输出要求：
1. `job_posting` 必须包含结构化岗位信息：
   - title
   - company
   - location
   - source_platform
   - source_url
   - signals
   - sections
   - compensation_text
   - benefits
   - notes
2. `company_profile` 必须包含完整的 rich profile 结构：
   - source-native / linkedin / official 等来源证据
   - headline_metrics
   - narrative_sections
   - metric_tables
   - time_series
   - notable_alumni
   - related_pages
   - available_signals
   - missing_signals
   - raw_sections
   - source_snapshots
3. 若某字段拿不到，返回空字符串、空数组或空对象，但 key 必须存在。
4. 最终只输出符合 schema 的 JSON，不要输出 markdown，不要输出解释。
""".strip()


def _build_company_profile_prompt(
    *,
    company_name: str,
    job_url: str | None,
    jd_text: str | None,
) -> str:
    jd_excerpt = (jd_text or "").strip()[:2500]
    return f"""你现在是本地求职工作流里的 Capture 执行器，当前任务只做 Company Profile / Insights 抓取。

目标：
- 输入是公司名，可能附带岗位 URL 和 JD 上下文。
- 你必须使用 Computer Use 打开 Chrome，抓取这个公司的完整 company profile / insights 证据包。
- 你只做抓取，不做分析，不发消息。

公司名：
{company_name}

辅助上下文：
- 相关岗位链接：{job_url or ""}
- JD 摘要：
{jd_excerpt}

抓取优先级：
1. 如果提供了岗位链接，先从岗位页里抓 source-native 公司信号。
2. 再找 official site / careers。
3. 再找 LinkedIn 公司页；只要能定位到 LinkedIn 公司实体，就默认继续抓 company insights。
4. 保留来源分层，尽量把每个来源写进 `source_snapshots`。

执行边界：
- 最多处理 3 个来源页面：一个 source-native 来源、一个 official 来源、一个 LinkedIn 来源。
- 如果 LinkedIn / official 一时定位不到，就记录缺失并尽快返回，不要无限搜索。
- 如果 4 到 5 分钟内拿不到更多高价值信号，就立刻输出 partial-but-structured JSON。

重点信号：
- Total employee count
- 6m / 1y / 2y growth
- Median employee tenure
- Employee distribution / headcount growth by function
- Total job openings / openings by function
- Notable alumni
- Affiliated pages / related pages
- 任何能帮助 Analyzer 判断 hiring signal、buyer need、bridge/access 的公司级信息

输出要求：
- 只返回 `company_profile`
- 不做分析，不给建议
- 如果缺失就明确写进 `missing_signals`
- 只输出符合 schema 的 JSON，不要输出解释
""".strip()
