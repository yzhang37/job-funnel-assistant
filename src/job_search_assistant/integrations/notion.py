from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests


NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2025-09-03"
DEFAULT_ANALYSIS_DATA_SOURCE_ID = "913694d8-d6dd-4379-8153-22a36bf0f0c1"
DEFAULT_MAX_CHILDREN_PER_REQUEST = 100


@dataclass
class NotionPageResult:
    page_id: str
    page_url: str
    raw_response: dict[str, Any]


class NotionAnalysisReportClient:
    def __init__(
        self,
        api_token: str | None = None,
        analysis_data_source_id: str | None = None,
        max_children_per_request: int | None = None,
    ) -> None:
        self.api_token = api_token or os.getenv("NOTION_API_TOKEN")
        self.analysis_data_source_id = analysis_data_source_id or os.getenv("NOTION_ANALYSIS_DATA_SOURCE_ID")
        self.analysis_data_source_id = self.analysis_data_source_id or DEFAULT_ANALYSIS_DATA_SOURCE_ID
        self.max_children_per_request = (
            max_children_per_request
            or _load_notion_settings()["max_children_per_request"]
            or DEFAULT_MAX_CHILDREN_PER_REQUEST
        )
        if not self.api_token:
            raise RuntimeError("NOTION_API_TOKEN is not set.")

    def create_analysis_page(
        self,
        *,
        title: str,
        company_name: str | None,
        position_name: str | None,
        job_url: str | None,
        source_platform: str | None,
        input_method: str,
        decision: str,
        fit_score: int | None,
        one_sentence: str,
        core_reasons: list[str],
        key_risk: str | None,
        recommended_action: str | None,
        company_profile_summary: str | None,
        analyzed_at: str,
        bundle_path: str | None,
        report_markdown: str,
        jd_markdown: str,
        company_profile_markdown: str | None,
    ) -> NotionPageResult:
        properties = {
            "报告标题": {"title": [_text(title)]},
            "公司名称": {"rich_text": _maybe_text(company_name)},
            "职位名称": {"rich_text": _maybe_text(position_name)},
            "岗位链接": {"url": job_url},
            "来源平台": {"select": {"name": source_platform or "其他"}},
            "输入方式": {"select": {"name": input_method}},
            "分析结论": {"select": {"name": decision}},
            "匹配分数": {"number": fit_score},
            "一句话结论": {"rich_text": _maybe_text(one_sentence)},
            "核心理由": {"rich_text": _maybe_text("；".join(core_reasons[:3]))},
            "关键风险": {"rich_text": _maybe_text(key_risk)},
            "推荐动作": {"rich_text": _maybe_text(recommended_action)},
            "公司画像摘要": {"rich_text": _maybe_text(company_profile_summary)},
            "分析时间": {"date": {"start": analyzed_at}},
            "报告版本": {"number": 1},
            "Bundle 路径": {"rich_text": _maybe_text(bundle_path)},
        }
        children = []
        children.extend(_heading_block("完整分析报告"))
        children.extend(_markdown_blocks(report_markdown))
        children.extend(_heading_block("原始 JD"))
        children.extend(_markdown_blocks(jd_markdown))
        if company_profile_markdown:
            children.extend(_heading_block("公司画像"))
            children.extend(_markdown_blocks(company_profile_markdown))

        response = requests.post(
            f"{NOTION_API_BASE}/pages",
            headers=self._headers(),
            json={
                "parent": {"data_source_id": self.analysis_data_source_id},
                "properties": properties,
            },
            timeout=60,
        )
        response.raise_for_status()
        body = response.json()
        if children:
            self._append_children_in_batches(body["id"], children)
        return NotionPageResult(
            page_id=body["id"],
            page_url=body["url"],
            raw_response=body,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION,
        }

    def _append_children_in_batches(self, parent_block_id: str, children: list[dict[str, Any]]) -> None:
        for batch in _chunk_blocks(children, batch_size=self.max_children_per_request):
            response = requests.patch(
                f"{NOTION_API_BASE}/blocks/{parent_block_id}/children",
                headers=self._headers(),
                json={"children": batch},
                timeout=60,
            )
            response.raise_for_status()


def _text(value: str) -> dict[str, Any]:
    return {"type": "text", "text": {"content": value[:2000]}}


def _maybe_text(value: str | None) -> list[dict[str, Any]]:
    return [_text(value)] if value else []


def _chunk_blocks(children: list[dict[str, Any]], *, batch_size: int) -> list[list[dict[str, Any]]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive.")
    return [children[index : index + batch_size] for index in range(0, len(children), batch_size)]


def _heading_block(text: str) -> list[dict[str, Any]]:
    return [
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [_text(text)]},
        }
    ]


def _markdown_blocks(markdown: str, chunk_size: int = 1800) -> list[dict[str, Any]]:
    return _markdown_to_blocks(markdown, chunk_size=chunk_size)


def _markdown_to_blocks(markdown: str, *, chunk_size: int) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    lines = markdown.splitlines()
    paragraph_lines: list[str] = []
    code_lines: list[str] = []
    in_code_block = False
    code_language = "plain text"
    index = 0

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if not paragraph_lines:
            return
        text = "\n".join(paragraph_lines).strip()
        if text:
            blocks.extend(_paragraph_blocks(text, chunk_size=chunk_size))
        paragraph_lines = []

    def flush_code_block() -> None:
        nonlocal code_lines, code_language
        if not code_lines:
            return
        text = "\n".join(code_lines).strip("\n")
        for chunk in _chunk_markdown(text, chunk_size=chunk_size):
            blocks.append(
                {
                    "object": "block",
                    "type": "code",
                    "code": {
                        "language": _normalize_code_language(code_language),
                        "rich_text": _inline_rich_text(chunk),
                    },
                }
            )
        code_lines = []
        code_language = "plain text"

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            if in_code_block:
                flush_code_block()
                in_code_block = False
            else:
                code_language = stripped[3:].strip() or "plain text"
                in_code_block = True
            index += 1
            continue

        if in_code_block:
            code_lines.append(line)
            index += 1
            continue

        if not stripped:
            flush_paragraph()
            index += 1
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            flush_paragraph()
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip()
            blocks.append(_heading_markdown_block(level, text))
            index += 1
            continue

        bullet_match = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet_match:
            flush_paragraph()
            while index < len(lines):
                current = lines[index].strip()
                current_match = re.match(r"^[-*]\s+(.+)$", current)
                if not current_match:
                    break
                blocks.append(
                    {
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {"rich_text": _inline_rich_text(current_match.group(1).strip())},
                    }
                )
                index += 1
            continue

        numbered_match = re.match(r"^\d+\.\s+(.+)$", stripped)
        if numbered_match:
            flush_paragraph()
            while index < len(lines):
                current = lines[index].strip()
                current_match = re.match(r"^\d+\.\s+(.+)$", current)
                if not current_match:
                    break
                blocks.append(
                    {
                        "object": "block",
                        "type": "numbered_list_item",
                        "numbered_list_item": {"rich_text": _inline_rich_text(current_match.group(1).strip())},
                    }
                )
                index += 1
            continue

        paragraph_lines.append(line)
        index += 1

    flush_paragraph()
    if in_code_block:
        flush_code_block()

    return blocks


def _heading_markdown_block(level: int, text: str) -> dict[str, Any]:
    if level <= 1:
        block_type = "heading_1"
    elif level == 2:
        block_type = "heading_2"
    else:
        block_type = "heading_3"
    return {
        "object": "block",
        "type": block_type,
        block_type: {"rich_text": _inline_rich_text(text)},
    }


def _paragraph_blocks(text: str, *, chunk_size: int) -> list[dict[str, Any]]:
    return [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": _inline_rich_text(chunk)},
        }
        for chunk in _chunk_markdown(text, chunk_size=chunk_size)
    ]


def _inline_rich_text(text: str) -> list[dict[str, Any]]:
    rich_text: list[dict[str, Any]] = []
    pos = 0
    token_pattern = re.compile(
        r"\[([^\]]+)\]\((https?://[^)]+)\)|"  # markdown link
        r"\*\*([^*]+)\*\*|"  # bold
        r"`([^`]+)`"  # inline code
    )
    for match in token_pattern.finditer(text):
        start, end = match.span()
        if start > pos:
            rich_text.extend(_plain_text_chunks(text[pos:start]))
        if match.group(1) is not None and match.group(2) is not None:
            rich_text.extend(_link_text_chunks(match.group(1), match.group(2)))
        elif match.group(3) is not None:
            rich_text.extend(_annotated_text_chunks(match.group(3), bold=True))
        elif match.group(4) is not None:
            rich_text.extend(_annotated_text_chunks(match.group(4), code=True))
        pos = end
    if pos < len(text):
        rich_text.extend(_plain_text_chunks(text[pos:]))
    return rich_text or [_text("")]


def _plain_text_chunks(text: str) -> list[dict[str, Any]]:
    return [_text(chunk) for chunk in _split_text_chunks(text)]


def _annotated_text_chunks(text: str, *, bold: bool = False, code: bool = False) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for chunk in _split_text_chunks(text):
        token = _text(chunk)
        token["annotations"] = {
            "bold": bold,
            "italic": False,
            "strikethrough": False,
            "underline": False,
            "code": code,
            "color": "default",
        }
        chunks.append(token)
    return chunks


def _link_text_chunks(label: str, url: str) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for chunk in _split_text_chunks(label):
        chunks.append(
            {
                "type": "text",
                "text": {"content": chunk, "link": {"url": url}},
                "annotations": {
                    "bold": False,
                    "italic": False,
                    "strikethrough": False,
                    "underline": False,
                    "code": False,
                    "color": "default",
                },
            }
        )
    return chunks


def _split_text_chunks(text: str, *, max_length: int = 2000) -> list[str]:
    if not text:
        return [""]
    return [text[i : i + max_length] for i in range(0, len(text), max_length)]


def _normalize_code_language(language: str) -> str:
    normalized = language.strip().lower()
    supported = {
        "plain text",
        "python",
        "javascript",
        "typescript",
        "json",
        "bash",
        "shell",
        "sql",
        "html",
        "css",
        "java",
        "c++",
        "c#",
        "go",
        "rust",
        "yaml",
        "toml",
        "markdown",
    }
    if normalized in supported:
        return normalized
    if normalized in {"sh", "zsh"}:
        return "shell"
    if normalized in {"py"}:
        return "python"
    if normalized in {"js"}:
        return "javascript"
    if normalized in {"ts"}:
        return "typescript"
    return "plain text"


@lru_cache(maxsize=1)
def _load_notion_settings() -> dict[str, int]:
    repo_root = Path(__file__).resolve().parents[3]
    config_path = repo_root / "config" / "integrations.toml"
    if not config_path.exists():
        return {"max_children_per_request": DEFAULT_MAX_CHILDREN_PER_REQUEST}
    payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    notion = payload.get("notion", {})
    max_children = int(notion.get("max_children_per_request", DEFAULT_MAX_CHILDREN_PER_REQUEST))
    return {"max_children_per_request": max_children}


def _chunk_markdown(markdown: str, *, chunk_size: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for line in markdown.splitlines():
        candidate = f"{current}\n{line}".strip() if current else line
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(line) > chunk_size:
            chunks.append(line[:chunk_size])
            line = line[chunk_size:]
        current = line
    if current:
        chunks.append(current)
    return chunks or [markdown[:chunk_size]]
