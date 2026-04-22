from __future__ import annotations

import base64
import json
import mimetypes
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


RESPONSES_API_URL = "https://api.openai.com/v1/responses"


@dataclass
class ProviderRequest:
    repo_root: Path
    developer_prompt: str
    user_text: str
    image_paths: list[Path]
    schema: dict[str, Any]
    model: str
    analysis_mode: str
    enable_web_search: bool


class OpenAIResponsesProvider:
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL") or RESPONSES_API_URL
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")

    def run(self, request: ProviderRequest) -> dict[str, Any]:
        payload = {
            "model": request.model,
            "input": [
                {
                    "role": "developer",
                    "content": [{"type": "input_text", "text": request.developer_prompt}],
                },
                {
                    "role": "user",
                    "content": self._build_user_content(request.user_text, request.image_paths),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": request.schema["name"],
                    "strict": request.schema["strict"],
                    "schema": request.schema["schema"],
                }
            },
        }
        if request.enable_web_search:
            payload["tools"] = [{"type": "web_search_preview"}]

        response = requests.post(
            self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=180,
        )
        response.raise_for_status()
        body = response.json()
        text = _extract_output_text(body)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Model returned non-JSON output: {text}") from exc

    def _build_user_content(self, user_text: str, image_paths: list[Path]) -> list[dict[str, str]]:
        content: list[dict[str, str]] = [{"type": "input_text", "text": user_text}]
        for path in image_paths:
            content.append({"type": "input_image", "image_url": _image_to_data_url(path)})
        return content


class CodexExecProvider:
    def __init__(self, codex_bin: str | None = None) -> None:
        self.codex_bin = codex_bin or shutil.which("codex")
        if not self.codex_bin:
            raise RuntimeError("codex CLI is not installed or not on PATH.")

    def run(self, request: ProviderRequest) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="codex-provider-") as temp_dir:
            temp_root = Path(temp_dir)
            schema_path = temp_root / "output_schema.json"
            schema_path.write_text(
                json.dumps(request.schema["schema"], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            output_path = temp_root / "last_message.json"
            prompt_text = self._build_prompt(request)

            command = [
                self.codex_bin,
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
                request.model,
            ]
            if request.enable_web_search:
                command.append("--search")
            for image_path in request.image_paths:
                command.extend(["-i", str(image_path)])
            command.extend(["-",])

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
                raise RuntimeError(f"codex exec failed with code {result.returncode}: {combined}")
            if not output_path.exists():
                raise RuntimeError("codex exec finished without writing the last-message file.")
            raw = output_path.read_text(encoding="utf-8").strip()
            try:
                return json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Codex provider returned non-JSON output: {raw}") from exc

    def _build_prompt(self, request: ProviderRequest) -> str:
        return f"""你现在是这个本地工作流里的 Analyzer。

## Developer Instructions
{request.developer_prompt}

## User Input
{request.user_text}

要求：
- 严格遵守 developer instructions。
- 最终只输出符合 JSON schema 的 JSON 对象。
- 不要输出 markdown 代码块。
""".strip()


class MockProvider:
    def run(self, request: ProviderRequest) -> dict[str, Any]:
        text = request.user_text.lower()
        backend = any(keyword in text for keyword in ["backend", "platform", "infra", "distributed", "workflow"])
        ml_research = any(keyword in text for keyword in ["research scientist", "ml scientist", "phd", "model training"])
        senior_too_high = any(keyword in text for keyword in ["staff engineer", "principal engineer", "director"])
        visa_risk = any(keyword in text for keyword in ["no sponsorship", "usc only", "citizenship required", "clearance"])

        category = "主攻" if backend and not (senior_too_high or ml_research or visa_risk) else "备胎"
        if ml_research or senior_too_high or visa_risk:
            category = "放弃" if sum([ml_research, senior_too_high, visa_risk]) >= 2 else category

        fit_score = 8 if category == "主攻" else 5 if category == "备胎" else 2
        title = _extract_field(request.user_text, "guessed_title") or "未知岗位"
        company = _extract_field(request.user_text, "company_name") or "未知公司"

        reasons = []
        if backend:
            reasons.append("JD 明显偏 backend / platform / infra，和默认候选人画像主轴一致。")
        if senior_too_high:
            reasons.append("岗位 seniority 可能高于当前默认画像的可控区间。")
        if ml_research:
            reasons.append("岗位更偏纯研究或模型训练，不是默认画像最优切面。")
        if visa_risk:
            reasons.append("JD 文本里出现了 work authorization / clearance 相关硬限制，需要高优先级核验。")
        if not reasons:
            reasons.append("当前只有 JD 文本，缺少 careers/ATS 交叉验证。")
        reasons = reasons[:3]

        return {
            "analysis_metadata": {
                "analysis_mode": request.analysis_mode,
                "evidence_sources": [
                    {
                        "label": "Provided JD text",
                        "url": "",
                        "source_type": "user_input",
                        "note": "Mock mode only used the provided JD packet and did not verify official careers or ATS pages.",
                    }
                ],
            },
            "report": {
                "executive_verdict": {
                    "one_sentence": f"{company} 的 {title} 当前更适合作为{category}机会处理。",
                    "funnel_category": category,
                    "reasons": reasons,
                },
                "part_a": {
                    "judgment_result": "更接近基于 JD 文本的初筛结论，不足以单独证明是真岗位或 ghost job。",
                    "support_signals": [
                        "JD 文本本身出现了较明确的职责或技能关键词。" if backend else "JD 文本可以看出岗位方向，但不够说明真实需求强度。",
                        "当前至少有职位名称和核心技能描述可用于初步匹配。",
                    ],
                    "risk_signals": [
                        "未验证官方 careers / ATS 当前状态。",
                        "posting time、repost、同类岗位数量均未知。",
                    ],
                    "final_conclusion": "目前只能做 Quick Screening，不能把这份结论当成完整尽调。",
                },
                "part_b": {
                    "company_business_judgment": "仅凭 JD 文本无法稳健判断公司业务和真实 hiring urgency，只能做有限推断。",
                    "buyer_need_clusters": [
                        "后端 / 平台 / 基础设施能力" if backend else "待补证据后再确认的工程能力簇",
                        "系统可靠性、workflow automation、可观测性相关能力" if backend else "职位文本中未充分展开的买方需求",
                    ],
                    "company_vs_jd": "当前更适合把它视作一个待验证入口；是否公司值得打、以及该 JD 是否最优切入口，都需要官方 openings 聚类补证据。",
                },
                "part_c": {
                    "reachability_rating": "低",
                    "contact_types": [
                        "目标 team 的 hiring manager 或 tech lead",
                        "相近职能工程经理",
                        "recruiter / sourcer",
                    ],
                    "natural_bridges": [
                        "若能找到 ByteDance / TikTok alumni 或相近平台工程背景联系人，桥梁价值更高。"
                    ],
                    "ats_black_box_assessment": "未验证 ATS，当前默认视为中到高黑箱。",
                    "entry_strategy": "不要只做单纯海投；更适合先验证 openings 簇，再决定是否找真人切入。",
                },
                "buyer_cluster_map": {
                    "disclaimer": "以下仅按相近职能聚类，不代表真实 team 结构。",
                    "same_team": [],
                    "adjacent_functions": [
                        {
                            "role_or_group": "Backend / Platform / Infra",
                            "purchased_capability": "系统设计、可靠性、workflow automation、平台工程",
                            "evidence_note": "基于 JD 文本关键词的有限聚类。",
                        }
                    ]
                    if backend
                    else [],
                    "unrelated": [
                        {
                            "role_or_group": "纯 ML Research / Scientist",
                            "purchased_capability": "算法研究或模型训练导向能力",
                            "evidence_note": "与默认候选人画像不是最优重叠。",
                        }
                    ]
                    if ml_research
                    else [],
                },
                "candidate_fit_analysis": {
                    "strong_match": [
                        "backend / platform / infra 主轴与默认长期画像一致。"
                    ]
                    if backend
                    else ["暂未发现明显强匹配主轴。"],
                    "medium_match": [
                        "workflow automation、系统可靠性、troubleshooting narrative 可能可迁移。"
                    ],
                    "clear_gaps": [
                        "seniority 可能偏高。" if senior_too_high else "需要更多业务上下文来判断产品理解要求。",
                        "work authorization / clearance 需要以 JD 原文或官方政策再核验。" if visa_risk else "缺少官方 openings 交叉验证。",
                    ],
                    "narrative_bridge": "可以把 TikTok 的合规、workflow、oncall、RCA、DR 经验包装成复杂系统工程 narrative，但不能覆盖硬门槛缺口。",
                    "overall_fit_score": fit_score,
                },
                "recommended_actions": [
                    "先补齐官方 careers / ATS 链接，确认岗位是否仍开放、是否存在相近 openings。",
                    "核验 JD 是否写明 sponsorship、clearance、citizenship 或 location 硬限制。",
                    "如果确认公司还在集中招相近职能，再决定是否主攻并寻找 hiring manager / recruiter。",
                ],
                "risk_unknowns": {
                    "unknowns": [
                        "官方 careers 当前状态未知。",
                        "同 location / 同 function openings 数量未知。",
                        "posting time 与 repost 信息未知。",
                    ],
                    "inferences": [
                        "所有买方需求簇判断都主要依赖 JD 文本和默认候选人画像。",
                    ],
                    "evidence_gaps": [
                        "缺少截图结构化信息。",
                        "缺少公司公开业务与 hiring trend 证据。",
                    ],
                    "needed_materials": [
                        "岗位原始链接或官方 careers 页面链接。",
                        "LinkedIn / Sales Navigator 截图（如有）。",
                    ],
                },
            },
        }


def _image_to_data_url(path: Path) -> str:
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _extract_output_text(body: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in body.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                parts.append(content.get("text", ""))
            if content.get("type") == "refusal":
                raise ValueError(content.get("refusal", "Model refused to answer."))
    if not parts and isinstance(body.get("output_text"), str):
        parts.append(body["output_text"])
    if not parts:
        raise ValueError(f"Could not extract output text from response payload: {body}")
    return "".join(parts).strip()


def _extract_field(text: str, field_name: str) -> str | None:
    marker = f'"{field_name}": '
    if marker not in text:
        return None
    tail = text.split(marker, 1)[1].split("\n", 1)[0].strip()
    return tail.strip('",')


def codex_cli_is_ready(codex_bin: str | None = None) -> bool:
    bin_path = codex_bin or shutil.which("codex")
    if not bin_path:
        return False
    result = subprocess.run(
        [bin_path, "login", "status"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    combined = "\n".join(part for part in (result.stdout, result.stderr) if part)
    return result.returncode == 0 and "Logged in" in combined
