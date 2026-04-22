from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .job_packet import JobPacket, build_job_packet
from .profile_loader import load_profile_stack
from .providers import MockProvider, OpenAIResponsesProvider, ProviderRequest
from .renderer import render_markdown
from .schema import REPORT_JSON_SCHEMA, validate_report_shape


@dataclass
class RunResult:
    payload: dict[str, Any]
    markdown: str


def run_analysis(
    *,
    repo_root: Path,
    jd_text: str,
    profile_stack_path: str | Path,
    extra_profile_fragments: list[str] | None = None,
    provider_name: str = "auto",
    model: str = "gpt-5.2",
    analysis_mode: str = "quick",
    enable_web_search: bool = False,
    company_name: str | None = None,
    job_url: str | None = None,
    special_questions: str | None = None,
    image_paths: list[str] | None = None,
    notes: str | None = None,
    company_profile_payload: dict[str, Any] | None = None,
    bundle_manifest: dict[str, Any] | None = None,
) -> RunResult:
    loaded_profile = load_profile_stack(repo_root, profile_stack_path, extra_profile_fragments)
    packet = build_job_packet(
        jd_text=jd_text,
        company_name=company_name,
        job_url=job_url,
        special_questions=special_questions,
        image_paths=image_paths,
        notes=notes,
        company_profile_payload=company_profile_payload,
        bundle_manifest=bundle_manifest,
    )
    developer_prompt = _build_developer_prompt(repo_root, loaded_profile.combined_markdown, analysis_mode)
    user_text = _build_user_text(packet, loaded_profile.fragments)

    provider = _select_provider(provider_name)
    response = provider.run(
        ProviderRequest(
            developer_prompt=developer_prompt,
            user_text=user_text,
            image_paths=packet.image_paths,
            schema=REPORT_JSON_SCHEMA,
            model=model,
            analysis_mode=analysis_mode,
            enable_web_search=enable_web_search,
        )
    )
    validate_report_shape(response)

    payload = {
        "run_metadata": {
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "provider": provider.__class__.__name__,
            "model": model,
            "analysis_mode": analysis_mode,
            "profile_fragments": [str(path) for path in loaded_profile.fragments],
            "job_packet": packet.to_payload(),
            "web_search_enabled": enable_web_search,
        },
        **response,
    }
    markdown = render_markdown(payload)
    return RunResult(payload=payload, markdown=markdown)


def save_outputs(result: RunResult, markdown_path: str | Path | None, json_path: str | Path | None) -> None:
    if markdown_path:
        output = Path(markdown_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result.markdown, encoding="utf-8")
    if json_path:
        output = Path(json_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result.payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _select_provider(provider_name: str) -> MockProvider | OpenAIResponsesProvider:
    if provider_name == "mock":
        return MockProvider()
    if provider_name == "openai":
        return OpenAIResponsesProvider()
    try:
        return OpenAIResponsesProvider()
    except RuntimeError:
        return MockProvider()


def _build_developer_prompt(repo_root: Path, combined_profile: str, analysis_mode: str) -> str:
    spec_path = repo_root / "prompts" / "job_funnel_resume_fit_analyst_spec.md"
    spec_text = spec_path.read_text(encoding="utf-8").strip()
    runtime_rules = f"""

================ RUNTIME ORCHESTRATION LAYER ================
你必须遵守上面的 analyzer spec 原文，不要改写它的分析框架。

补充运行规则：
1. 当前分析模式是 `{analysis_mode}`。如果证据不足，请按 spec 中的 Quick Screening / Full Analysis 规则处理。
2. 下方 `Authoritative Candidate Profile Stack` 是当前候选人画像的权威版本；若与 spec 原文中的长期背景描述冲突，以这里为准。
3. 输出必须使用简洁中文；但候选人经历里的英文原句、岗位名、技术词、公司名、制度名不要强行翻译。
4. 不要把未知写成已确认事实。凡是未核验内容，明确标注“未知”“无法验证”或“基于有限证据推断”。
5. 推荐动作必须具体、可执行，且数量严格控制在 3 到 5 条。
6. `analysis_metadata.evidence_sources` 中只写你实际检查或实际使用过的证据来源。

## Authoritative Candidate Profile Stack
{combined_profile}
""".strip()
    return f"{spec_text}\n\n{runtime_rules}"


def _build_user_text(packet: JobPacket, profile_fragments: list[Path]) -> str:
    return f"""请基于以下输入运行完整分析。

## Analysis Input Packet
{json.dumps(packet.to_payload(), ensure_ascii=False, indent=2)}

## Active Profile Fragments
{json.dumps([str(path) for path in profile_fragments], ensure_ascii=False, indent=2)}

要求：
- 先最大化利用已有输入。
- 如果可以验证外部公开信息，就按 spec 优先级验证。
- 如果不能验证，也必须完成结构化分析，并在 Risk / Unknowns 中说明。
""".strip()
