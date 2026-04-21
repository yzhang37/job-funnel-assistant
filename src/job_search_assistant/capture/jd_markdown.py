from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

"""Generic markdown rendering for browser-captured job content.

This layer is intentionally platform-agnostic:
- no LinkedIn-specific required fields
- no fixed screenshot count
- no assumption that every source has the same sections
"""


@dataclass
class JobSection:
    heading: str
    paragraphs: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)


@dataclass
class JobPostingContent:
    title: str
    company: str | None = None
    location: str | None = None
    source_platform: str | None = None
    source_url: str | None = None
    signals: list[str] = field(default_factory=list)
    sections: list[JobSection] = field(default_factory=list)
    compensation_text: str | None = None
    benefits: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "JobPostingContent":
        """Build a generic posting object from loosely structured capture data."""
        sections = []
        for raw in payload.get("sections", []):
            sections.append(
                JobSection(
                    heading=str(raw.get("heading", "")).strip(),
                    paragraphs=[str(item).strip() for item in raw.get("paragraphs", []) if str(item).strip()],
                    bullets=[str(item).strip() for item in raw.get("bullets", []) if str(item).strip()],
                )
            )
        return cls(
            title=str(payload.get("title", "")).strip(),
            company=_optional_text(payload.get("company")),
            location=_optional_text(payload.get("location")),
            source_platform=_optional_text(payload.get("source_platform")),
            source_url=_optional_text(payload.get("source_url")),
            signals=[str(item).strip() for item in payload.get("signals", []) if str(item).strip()],
            sections=sections,
            compensation_text=_optional_text(payload.get("compensation_text")),
            benefits=[str(item).strip() for item in payload.get("benefits", []) if str(item).strip()],
            notes=[str(item).strip() for item in payload.get("notes", []) if str(item).strip()],
        )


def render_jd_markdown(posting: JobPostingContent) -> str:
    """Render the minimum reusable output for the first capture milestone: jd.md."""
    if not posting.title:
        raise ValueError("JobPostingContent.title is required to render jd markdown.")

    lines: list[str] = [f"# {posting.title}", ""]

    meta_lines = []
    if posting.company:
        meta_lines.append(f"- 公司: {posting.company}")
    if posting.location:
        meta_lines.append(f"- 地点: {posting.location}")
    if posting.source_platform:
        meta_lines.append(f"- 来源平台: {posting.source_platform}")
    if posting.source_url:
        meta_lines.append(f"- 原始链接: {posting.source_url}")
    if posting.signals:
        meta_lines.append(f"- 岗位信号: {' | '.join(posting.signals)}")

    if meta_lines:
        lines.extend(meta_lines)
        lines.append("")

    for section in posting.sections:
        if not section.heading:
            continue
        lines.append(f"## {section.heading}")
        lines.append("")
        for paragraph in section.paragraphs:
            lines.append(paragraph)
            lines.append("")
        for bullet in section.bullets:
            lines.append(f"- {bullet}")
        if section.bullets:
            lines.append("")

    if posting.compensation_text or posting.benefits:
        lines.append("## Compensation And Benefits")
        lines.append("")
        if posting.compensation_text:
            lines.append(posting.compensation_text)
            lines.append("")
        for benefit in posting.benefits:
            lines.append(f"- {benefit}")
        if posting.benefits:
            lines.append("")

    if posting.notes:
        lines.append("## Capture Notes")
        lines.append("")
        for note in posting.notes:
            lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
