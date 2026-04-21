from __future__ import annotations

from typing import Any


REPORT_JSON_SCHEMA: dict[str, Any] = {
    "name": "job_funnel_analysis_report",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "analysis_metadata": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "analysis_mode": {"type": "string", "enum": ["quick", "full"]},
                    "evidence_sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "label": {"type": "string"},
                                "url": {"type": "string"},
                                "source_type": {"type": "string"},
                                "note": {"type": "string"},
                            },
                            "required": ["label", "url", "source_type", "note"],
                        },
                    },
                },
                "required": ["analysis_mode", "evidence_sources"],
            },
            "report": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "executive_verdict": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "one_sentence": {"type": "string"},
                            "funnel_category": {"type": "string", "enum": ["主攻", "备胎", "放弃"]},
                            "reasons": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["one_sentence", "funnel_category", "reasons"],
                    },
                    "part_a": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "judgment_result": {"type": "string"},
                            "support_signals": {"type": "array", "items": {"type": "string"}},
                            "risk_signals": {"type": "array", "items": {"type": "string"}},
                            "final_conclusion": {"type": "string"},
                        },
                        "required": ["judgment_result", "support_signals", "risk_signals", "final_conclusion"],
                    },
                    "part_b": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "company_business_judgment": {"type": "string"},
                            "buyer_need_clusters": {"type": "array", "items": {"type": "string"}},
                            "company_vs_jd": {"type": "string"},
                        },
                        "required": ["company_business_judgment", "buyer_need_clusters", "company_vs_jd"],
                    },
                    "part_c": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "reachability_rating": {"type": "string", "enum": ["高", "中", "低"]},
                            "contact_types": {"type": "array", "items": {"type": "string"}},
                            "natural_bridges": {"type": "array", "items": {"type": "string"}},
                            "ats_black_box_assessment": {"type": "string"},
                            "entry_strategy": {"type": "string"},
                        },
                        "required": [
                            "reachability_rating",
                            "contact_types",
                            "natural_bridges",
                            "ats_black_box_assessment",
                            "entry_strategy",
                        ],
                    },
                    "buyer_cluster_map": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "disclaimer": {"type": "string"},
                            "same_team": {"type": "array", "items": {"$ref": "#/$defs/cluster_item"}},
                            "adjacent_functions": {"type": "array", "items": {"$ref": "#/$defs/cluster_item"}},
                            "unrelated": {"type": "array", "items": {"$ref": "#/$defs/cluster_item"}},
                        },
                        "required": ["disclaimer", "same_team", "adjacent_functions", "unrelated"],
                    },
                    "candidate_fit_analysis": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "strong_match": {"type": "array", "items": {"type": "string"}},
                            "medium_match": {"type": "array", "items": {"type": "string"}},
                            "clear_gaps": {"type": "array", "items": {"type": "string"}},
                            "narrative_bridge": {"type": "string"},
                            "overall_fit_score": {"type": "integer", "minimum": 0, "maximum": 10},
                        },
                        "required": [
                            "strong_match",
                            "medium_match",
                            "clear_gaps",
                            "narrative_bridge",
                            "overall_fit_score",
                        ],
                    },
                    "recommended_actions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 3,
                        "maxItems": 5,
                    },
                    "risk_unknowns": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "unknowns": {"type": "array", "items": {"type": "string"}},
                            "inferences": {"type": "array", "items": {"type": "string"}},
                            "evidence_gaps": {"type": "array", "items": {"type": "string"}},
                            "needed_materials": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["unknowns", "inferences", "evidence_gaps", "needed_materials"],
                    },
                },
                "required": [
                    "executive_verdict",
                    "part_a",
                    "part_b",
                    "part_c",
                    "buyer_cluster_map",
                    "candidate_fit_analysis",
                    "recommended_actions",
                    "risk_unknowns",
                ],
            },
        },
        "required": ["analysis_metadata", "report"],
        "$defs": {
            "cluster_item": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "role_or_group": {"type": "string"},
                    "purchased_capability": {"type": "string"},
                    "evidence_note": {"type": "string"},
                },
                "required": ["role_or_group", "purchased_capability", "evidence_note"],
            }
        },
    },
}


def validate_report_shape(payload: dict[str, Any]) -> None:
    report = payload["report"]
    if len(report["executive_verdict"]["reasons"]) > 3:
        raise ValueError("Executive verdict reasons must contain at most 3 items.")
    if not 3 <= len(report["recommended_actions"]) <= 5:
        raise ValueError("Recommended actions must contain 3 to 5 items.")

