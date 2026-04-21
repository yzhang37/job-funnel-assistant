from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_FIELDS = ["title", "company", "location", "description", "requirements"]


@dataclass
class RuleResult:
    name: str
    passed: bool
    matched_keywords: list[str]
    weight: int
    message: str


@dataclass
class AnalysisResult:
    decision: str
    score: int
    hard_requirements_passed: bool
    summary: str
    must: list[RuleResult]
    prefer: list[RuleResult]
    avoid: list[RuleResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "score": self.score,
            "hard_requirements_passed": self.hard_requirements_passed,
            "summary": self.summary,
            "must": [asdict(item) for item in self.must],
            "prefer": [asdict(item) for item in self.prefer],
            "avoid": [asdict(item) for item in self.avoid],
        }


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def analyze_job_fit(job: dict[str, Any], profile: dict[str, Any]) -> AnalysisResult:
    must_results = _evaluate_rules(job, profile.get("must", []), kind="must")
    prefer_results = _evaluate_rules(job, profile.get("prefer", []), kind="prefer")
    avoid_results = _evaluate_rules(job, profile.get("avoid", []), kind="avoid")

    must_passed = all(result.passed for result in must_results)

    score = 0
    for result in prefer_results:
        if result.passed:
            score += result.weight
    for result in avoid_results:
        if result.passed:
            score -= result.weight

    thresholds = profile.get("thresholds", {})
    strong_match_threshold = int(thresholds.get("strong_match", 70))
    consider_threshold = int(thresholds.get("consider", 40))

    if not must_passed:
        decision = "reject"
    elif score >= strong_match_threshold:
        decision = "strong_match"
    elif score >= consider_threshold:
        decision = "consider"
    else:
        decision = "reject"

    summary = _build_summary(job, decision, score, must_results, prefer_results, avoid_results)

    return AnalysisResult(
        decision=decision,
        score=score,
        hard_requirements_passed=must_passed,
        summary=summary,
        must=must_results,
        prefer=prefer_results,
        avoid=avoid_results,
    )


def _evaluate_rules(job: dict[str, Any], rules: list[dict[str, Any]], kind: str) -> list[RuleResult]:
    results: list[RuleResult] = []
    for rule in rules:
        name = str(rule.get("name", "Unnamed Rule"))
        fields = rule.get("fields") or DEFAULT_FIELDS
        text = _collect_text(job, fields)
        match_any = [item.lower() for item in rule.get("match_any", [])]
        match_all = [item.lower() for item in rule.get("match_all", [])]
        weight = int(rule.get("weight", 0))

        matched_keywords = [keyword for keyword in match_any if keyword in text]
        all_keywords_found = all(keyword in text for keyword in match_all)

        if match_any and match_all:
            passed = bool(matched_keywords) and all_keywords_found
        elif match_all:
            passed = all_keywords_found
        else:
            passed = bool(matched_keywords)

        if match_all:
            matched_keywords.extend(
                [
                    keyword
                    for keyword in match_all
                    if keyword in text and keyword not in matched_keywords
                ]
            )

        message = _build_rule_message(kind, name, passed, matched_keywords)
        results.append(
            RuleResult(
                name=name,
                passed=passed,
                matched_keywords=matched_keywords,
                weight=weight,
                message=message,
            )
        )
    return results


def _collect_text(job: dict[str, Any], fields: list[str]) -> str:
    chunks: list[str] = []
    for field in fields:
        value = job.get(field, "")
        if isinstance(value, list):
            chunks.extend(str(item) for item in value)
        else:
            chunks.append(str(value))
    return " \n".join(chunks).lower()


def _build_rule_message(kind: str, name: str, passed: bool, matched_keywords: list[str]) -> str:
    if passed and matched_keywords:
        return f"{name} matched: {', '.join(matched_keywords)}"
    if passed:
        return f"{name} passed"
    if kind == "must":
        return f"{name} missing"
    return f"{name} not triggered"


def _build_summary(
    job: dict[str, Any],
    decision: str,
    score: int,
    must_results: list[RuleResult],
    prefer_results: list[RuleResult],
    avoid_results: list[RuleResult],
) -> str:
    title = job.get("title", "Unknown Title")
    company = job.get("company", "Unknown Company")
    passed_prefer = [item.name for item in prefer_results if item.passed]
    triggered_avoid = [item.name for item in avoid_results if item.passed]
    failed_must = [item.name for item in must_results if not item.passed]

    parts = [f"{company} / {title}", f"decision={decision}", f"score={score}"]
    if failed_must:
        parts.append("failed_must=" + ", ".join(failed_must))
    if passed_prefer:
        parts.append("matched=" + ", ".join(passed_prefer))
    if triggered_avoid:
        parts.append("risks=" + ", ".join(triggered_avoid))
    return " | ".join(parts)

