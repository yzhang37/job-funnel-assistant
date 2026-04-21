from __future__ import annotations

from typing import Any


def render_markdown(payload: dict[str, Any]) -> str:
    report = payload["report"]
    lines: list[str] = []

    lines.extend(
        [
            "#### 1. Executive Verdict",
            f"- 一句话结论：{report['executive_verdict']['one_sentence']}",
            f"- Funnel 分类：{report['executive_verdict']['funnel_category']}",
            "- 原因：",
        ]
    )
    lines.extend(_bullets(report["executive_verdict"]["reasons"]))

    lines.extend(
        [
            "",
            "#### 2. Part A — Hiring Signal",
            f"- 判断结果：{report['part_a']['judgment_result']}",
            "- 支持信号：",
        ]
    )
    lines.extend(_bullets(report["part_a"]["support_signals"]))
    lines.append("- 风险信号：")
    lines.extend(_bullets(report["part_a"]["risk_signals"]))
    lines.append(f"- 最终结论：{report['part_a']['final_conclusion']}")

    lines.extend(
        [
            "",
            "#### 3. Part B — Business / Company / Buyer Need",
            f"- 公司/业务判断：{report['part_b']['company_business_judgment']}",
            "- 当前买方需求簇：",
        ]
    )
    lines.extend(_bullets(report["part_b"]["buyer_need_clusters"]))
    lines.append(f"- “公司值得打”与“该 JD 是否值得主攻”的区别：{report['part_b']['company_vs_jd']}")

    lines.extend(
        [
            "",
            "#### 4. Part C — Access / 真人可达性",
            f"- 真人可达性评级：{report['part_c']['reachability_rating']}",
            "- 可打联系人类型：",
        ]
    )
    lines.extend(_bullets(report["part_c"]["contact_types"]))
    lines.append("- 是否存在天然桥梁（校友、前公司、相近职能等）：")
    lines.extend(_bullets(report["part_c"]["natural_bridges"]))
    lines.append(f"- ATS 黑箱程度：{report['part_c']['ats_black_box_assessment']}")
    lines.append(f"- 更合适的切入方式：{report['part_c']['entry_strategy']}")

    lines.extend(
        [
            "",
            "#### 5. Buyer Cluster Map",
            report["buyer_cluster_map"]["disclaimer"],
            "- 同团队（仅当证据足够时）：",
        ]
    )
    lines.extend(_cluster_lines(report["buyer_cluster_map"]["same_team"]))
    lines.append("- 相近职能：")
    lines.extend(_cluster_lines(report["buyer_cluster_map"]["adjacent_functions"]))
    lines.append("- 明显无关：")
    lines.extend(_cluster_lines(report["buyer_cluster_map"]["unrelated"]))

    lines.extend(
        [
            "",
            "#### 6. Candidate Fit Analysis",
            "- 强匹配：",
        ]
    )
    lines.extend(_bullets(report["candidate_fit_analysis"]["strong_match"]))
    lines.append("- 中等匹配：")
    lines.extend(_bullets(report["candidate_fit_analysis"]["medium_match"]))
    lines.append("- 明显缺口：")
    lines.extend(_bullets(report["candidate_fit_analysis"]["clear_gaps"]))
    lines.append(f"- 是否可以通过 narrative 补足：{report['candidate_fit_analysis']['narrative_bridge']}")
    lines.append(f"- 总体匹配度：{report['candidate_fit_analysis']['overall_fit_score']} / 10")

    lines.extend(["", "#### 7. Recommended Actions"])
    lines.extend(_numbered(report["recommended_actions"]))

    lines.extend(
        [
            "",
            "#### 8. Risk / Unknowns",
            "- 未知项：",
        ]
    )
    lines.extend(_bullets(report["risk_unknowns"]["unknowns"]))
    lines.append("- 推断项：")
    lines.extend(_bullets(report["risk_unknowns"]["inferences"]))
    lines.append("- 证据不足项：")
    lines.extend(_bullets(report["risk_unknowns"]["evidence_gaps"]))
    lines.append("- 还需要我补充的材料：")
    lines.extend(_bullets(report["risk_unknowns"]["needed_materials"]))

    return "\n".join(lines).strip()


def _bullets(items: list[str]) -> list[str]:
    if not items:
        return ["- 无"]
    return [f"- {item}" for item in items]


def _numbered(items: list[str]) -> list[str]:
    return [f"{index}. {item}" for index, item in enumerate(items, start=1)]


def _cluster_lines(items: list[dict[str, str]]) -> list[str]:
    if not items:
        return ["- 无"]
    return [
        f"- {item['role_or_group']}：买的是 {item['purchased_capability']}；证据：{item['evidence_note']}"
        for item in items
    ]

