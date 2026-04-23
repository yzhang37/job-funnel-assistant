from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


LIVE_CAPTURE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "job_posting": {
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
        },
        "company_profile": {
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
                "bridge_signals": {"type": "array", "items": {"type": "string"}},
                "competitor_names": {"type": "array", "items": {"type": "string"}},
                "available_signals": {"type": "array", "items": {"type": "string"}},
                "missing_signals": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "array", "items": {"type": "string"}},
                "raw_sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "heading": {"type": "string"},
                            "text": {"type": "string"},
                            "source_label": {"type": "string"},
                            "note": {"type": "string"},
                        },
                        "required": ["heading", "text", "source_label", "note"],
                    },
                },
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
                "bridge_signals",
                "competitor_names",
                "available_signals",
                "missing_signals",
                "notes",
                "raw_sections",
            ],
        },
    },
    "required": ["job_posting", "company_profile"],
}


def codex_live_capture_job_url(
    *,
    job_url: str,
    model: str = "gpt-5.4",
    max_attempts: int = 2,
) -> dict[str, Any]:
    codex_bin = shutil.which("codex")
    if not codex_bin:
        raise RuntimeError("codex CLI is not installed or not on PATH.")

    last_error: RuntimeError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return _run_codex_capture_once(codex_bin=codex_bin, job_url=job_url, model=model)
        except RuntimeError as exc:
            last_error = exc
            if attempt >= max_attempts:
                break
    assert last_error is not None
    raise last_error


def _run_codex_capture_once(*, codex_bin: str, job_url: str, model: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="codex-capture-") as temp_dir:
        temp_root = Path(temp_dir)
        schema_path = temp_root / "output_schema.json"
        schema_path.write_text(json.dumps(LIVE_CAPTURE_SCHEMA, ensure_ascii=False, indent=2), encoding="utf-8")
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

        prompt_text = _build_capture_prompt(job_url)
        result = subprocess.run(
            command,
            input=prompt_text,
            text=True,
            capture_output=True,
            timeout=1200,
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
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Codex live capture returned non-JSON output: {raw}") from exc


def _build_capture_prompt(job_url: str) -> str:
    return f"""你现在是本地求职工作流里的 Capture 执行器。

目标：
- 输入是一个岗位 URL。
- 你必须使用 Computer Use 打开 Chrome，访问这个 URL，并抓取足够的信息来生成 bundle。
- 你只做抓取，不做分析，不申请，不点击投递，不发消息。

当前岗位链接：
{job_url}

抓取要求：
1. 打开 Chrome，并进入上面的岗位链接。
2. 尽量展开页面上的岗位正文、职位详情、福利、薪资、公司卡片、公司洞察或公司简介区域。
3. 如果当前岗位页能直接看到公司画像信号，就抓下来；如果页面上存在显眼的一跳公司资料/公司卡片入口，也可以进入一层补齐，但不要无边界深挖。
4. 不要离开这个岗位上下文去做广泛搜索。
5. 若页面内容有限，也必须尽最大努力返回最小可用结构。

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
2. `sections` 至少整理出 2 个有意义的区块，只要页面确实有内容。
3. `company_profile` 必须返回一个最小可用的公司画像对象。
4. 如果某个公司字段当前拿不到，就返回空字符串或空数组，并在 `missing_signals` / `notes` 里说明。
5. 最终只输出符合 schema 的 JSON，不要输出 markdown，不要输出解释。
""".strip()
