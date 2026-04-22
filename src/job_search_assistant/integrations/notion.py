from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests


NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2025-09-03"
DEFAULT_ANALYSIS_DATA_SOURCE_ID = "913694d8-d6dd-4379-8153-22a36bf0f0c1"


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
    ) -> None:
        self.api_token = api_token or os.getenv("NOTION_API_TOKEN")
        self.analysis_data_source_id = analysis_data_source_id or os.getenv("NOTION_ANALYSIS_DATA_SOURCE_ID")
        self.analysis_data_source_id = self.analysis_data_source_id or DEFAULT_ANALYSIS_DATA_SOURCE_ID
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
                "children": children[:100],
            },
            timeout=60,
        )
        response.raise_for_status()
        body = response.json()
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


def _text(value: str) -> dict[str, Any]:
    return {"type": "text", "text": {"content": value[:2000]}}


def _maybe_text(value: str | None) -> list[dict[str, Any]]:
    return [_text(value)] if value else []


def _heading_block(text: str) -> list[dict[str, Any]]:
    return [
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [_text(text)]},
        }
    ]


def _markdown_blocks(markdown: str, chunk_size: int = 1800) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for paragraph in _chunk_markdown(markdown, chunk_size=chunk_size):
        blocks.append(
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [_text(paragraph)]},
            }
        )
    return blocks


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
