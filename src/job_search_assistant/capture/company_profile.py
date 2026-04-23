from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


@dataclass
class CompanyNarrativeSection:
    heading: str
    paragraphs: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


@dataclass
class CompanyMetricRow:
    label: str
    values: dict[str, str] = field(default_factory=dict)


@dataclass
class CompanyMetricTable:
    title: str
    columns: list[str] = field(default_factory=list)
    rows: list[CompanyMetricRow] = field(default_factory=list)
    note: str | None = None


@dataclass
class TimeSeriesPoint:
    label: str
    value: str
    note: str | None = None


@dataclass
class CompanyTimeSeries:
    title: str
    points: list[TimeSeriesPoint] = field(default_factory=list)
    note: str | None = None


@dataclass
class NotableAlumnus:
    name: str
    degree: str | None = None
    current_role: str | None = None
    previous_role: str | None = None


@dataclass
class CompanyRelatedPage:
    label: str
    url: str | None = None
    relationship: str | None = None
    source: str | None = None
    note: str | None = None


@dataclass
class CompanyRawSection:
    heading: str
    text: str
    source_label: str | None = None
    note: str | None = None


@dataclass
class CompanySourceSnapshot:
    label: str
    source_url: str | None = None
    source_platform: str | None = None
    source_kind: str | None = None
    headline_metrics: dict[str, Any] = field(default_factory=dict)
    bridge_signals: list[str] = field(default_factory=list)
    competitor_names: list[str] = field(default_factory=list)
    narrative_sections: list[CompanyNarrativeSection] = field(default_factory=list)
    metric_tables: list[CompanyMetricTable] = field(default_factory=list)
    time_series: list[CompanyTimeSeries] = field(default_factory=list)
    notable_alumni: list[NotableAlumnus] = field(default_factory=list)
    related_pages: list[CompanyRelatedPage] = field(default_factory=list)
    available_signals: list[str] = field(default_factory=list)
    missing_signals: list[str] = field(default_factory=list)
    raw_sections: list[CompanyRawSection] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class CompanyProfileContent:
    company_name: str
    source_url: str
    source_platform: str | None = None
    company_tagline: str | None = None
    company_description: str | None = None
    industry: str | None = None
    headquarters: str | None = None
    followers_text: str | None = None
    employee_size_text: str | None = None
    employees_on_platform_text: str | None = None
    featured_customers: list[str] = field(default_factory=list)
    bridge_signals: list[str] = field(default_factory=list)
    competitor_names: list[str] = field(default_factory=list)
    headline_metrics: dict[str, Any] = field(default_factory=dict)
    narrative_sections: list[CompanyNarrativeSection] = field(default_factory=list)
    metric_tables: list[CompanyMetricTable] = field(default_factory=list)
    time_series: list[CompanyTimeSeries] = field(default_factory=list)
    notable_alumni: list[NotableAlumnus] = field(default_factory=list)
    related_pages: list[CompanyRelatedPage] = field(default_factory=list)
    available_signals: list[str] = field(default_factory=list)
    missing_signals: list[str] = field(default_factory=list)
    raw_sections: list[CompanyRawSection] = field(default_factory=list)
    source_snapshots: list[CompanySourceSnapshot] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CompanyProfileContent":
        company_name = _required_text(payload.get("company_name"), "company_name")
        source_url = _required_text(payload.get("source_url"), "source_url")

        sections = _parse_narrative_sections(payload.get("narrative_sections", payload.get("sections", [])))
        metric_tables = _parse_metric_tables(payload.get("metric_tables", []))
        time_series = _parse_time_series(payload.get("time_series", []))
        notable_alumni = _parse_notable_alumni(payload.get("notable_alumni", []))
        related_pages = _parse_related_pages(payload.get("related_pages", []))
        raw_sections = _parse_raw_sections(payload.get("raw_sections", []))
        source_snapshots = _parse_source_snapshots(payload.get("source_snapshots", []))

        source_platform = _optional_text(payload.get("source_platform")) or detect_source_platform(source_url)

        return cls(
            company_name=company_name,
            source_url=source_url,
            source_platform=source_platform,
            company_tagline=_optional_text(payload.get("company_tagline")),
            company_description=_optional_text(payload.get("company_description")),
            industry=_optional_text(payload.get("industry")),
            headquarters=_optional_text(payload.get("headquarters")),
            followers_text=_optional_text(payload.get("followers_text")),
            employee_size_text=_optional_text(payload.get("employee_size_text")),
            employees_on_platform_text=_optional_text(payload.get("employees_on_platform_text")),
            featured_customers=[_clean_text(item) for item in payload.get("featured_customers", []) if _clean_text(item)],
            bridge_signals=[_clean_text(item) for item in payload.get("bridge_signals", []) if _clean_text(item)],
            competitor_names=[_clean_text(item) for item in payload.get("competitor_names", []) if _clean_text(item)],
            headline_metrics={key: value for key, value in _normalize_metric_map(payload.get("headline_metrics")).items() if key},
            narrative_sections=sections,
            metric_tables=metric_tables,
            time_series=time_series,
            notable_alumni=notable_alumni,
            related_pages=related_pages,
            available_signals=[_clean_text(item) for item in payload.get("available_signals", []) if _clean_text(item)],
            missing_signals=[_clean_text(item) for item in payload.get("missing_signals", []) if _clean_text(item)],
            raw_sections=raw_sections,
            source_snapshots=source_snapshots,
            notes=[_clean_text(item) for item in payload.get("notes", []) if _clean_text(item)],
        )

    def subject_key(self) -> str:
        return build_company_subject_key(self.company_name, self.source_url)

    def split_cache_payloads(self) -> dict[str, dict[str, Any]]:
        static_fields: dict[str, Any] = {
            "company_name": self.company_name,
            "source_url": self.source_url,
        }
        for field_name in (
            "company_tagline",
            "company_description",
            "industry",
            "headquarters",
            "followers_text",
            "employee_size_text",
            "employees_on_platform_text",
        ):
            value = getattr(self, field_name)
            if value:
                static_fields[field_name] = value
        if self.featured_customers:
            static_fields["featured_customers"] = self.featured_customers

        insight_fields: dict[str, Any] = {
            "company_name": self.company_name,
            "source_url": self.source_url,
        }
        insight_fields.update(self.headline_metrics)
        if self.bridge_signals:
            insight_fields["bridge_signals"] = self.bridge_signals
        if self.competitor_names:
            insight_fields["competitor_names"] = self.competitor_names
        if self.narrative_sections:
            insight_fields["narrative_sections"] = [
                {
                    "heading": section.heading,
                    "paragraphs": section.paragraphs,
                    "bullets": section.bullets,
                    "sources": section.sources,
                }
                for section in self.narrative_sections
                if section.heading
            ]
        if self.metric_tables:
            insight_fields["metric_tables"] = [
                {
                    "title": table.title,
                    "columns": table.columns,
                    "rows": [
                        {
                            "label": row.label,
                            "values": row.values,
                        }
                        for row in table.rows
                        if row.label
                    ],
                    "note": table.note,
                }
                for table in self.metric_tables
                if table.title
            ]
        if self.time_series:
            insight_fields["time_series"] = [
                {
                    "title": series.title,
                    "points": [
                        {"label": point.label, "value": point.value, "note": point.note}
                        for point in series.points
                    ],
                    "note": series.note,
                }
                for series in self.time_series
                if series.title
            ]
        if self.notable_alumni:
            insight_fields["notable_alumni"] = [
                {
                    "name": alumnus.name,
                    "degree": alumnus.degree,
                    "current_role": alumnus.current_role,
                    "previous_role": alumnus.previous_role,
                }
                for alumnus in self.notable_alumni
            ]
        if self.related_pages:
            insight_fields["related_pages"] = [
                {
                    "label": page.label,
                    "url": page.url,
                    "relationship": page.relationship,
                    "source": page.source,
                    "note": page.note,
                }
                for page in self.related_pages
                if page.label
            ]
        if self.available_signals:
            insight_fields["available_signals"] = self.available_signals
        if self.missing_signals:
            insight_fields["missing_signals"] = self.missing_signals
        if self.raw_sections:
            insight_fields["raw_sections"] = [
                {
                    "heading": section.heading,
                    "text": section.text,
                    "source_label": section.source_label,
                    "note": section.note,
                }
                for section in self.raw_sections
                if section.heading or section.text
            ]
        if self.source_snapshots:
            insight_fields["source_snapshots"] = [
                {
                    "label": snapshot.label,
                    "source_url": snapshot.source_url,
                    "source_platform": snapshot.source_platform,
                    "source_kind": snapshot.source_kind,
                    "headline_metrics": snapshot.headline_metrics,
                    "bridge_signals": snapshot.bridge_signals,
                    "competitor_names": snapshot.competitor_names,
                    "narrative_sections": [
                        {
                            "heading": section.heading,
                            "paragraphs": section.paragraphs,
                            "bullets": section.bullets,
                            "sources": section.sources,
                        }
                        for section in snapshot.narrative_sections
                        if section.heading
                    ],
                    "metric_tables": [
                        {
                            "title": table.title,
                            "columns": table.columns,
                            "rows": [
                                {
                                    "label": row.label,
                                    "values": row.values,
                                }
                                for row in table.rows
                                if row.label
                            ],
                            "note": table.note,
                        }
                        for table in snapshot.metric_tables
                        if table.title
                    ],
                    "time_series": [
                        {
                            "title": series.title,
                            "points": [
                                {"label": point.label, "value": point.value, "note": point.note}
                                for point in series.points
                            ],
                            "note": series.note,
                        }
                        for series in snapshot.time_series
                        if series.title
                    ],
                    "notable_alumni": [
                        {
                            "name": alumnus.name,
                            "degree": alumnus.degree,
                            "current_role": alumnus.current_role,
                            "previous_role": alumnus.previous_role,
                        }
                        for alumnus in snapshot.notable_alumni
                    ],
                    "related_pages": [
                        {
                            "label": page.label,
                            "url": page.url,
                            "relationship": page.relationship,
                            "source": page.source,
                            "note": page.note,
                        }
                        for page in snapshot.related_pages
                        if page.label
                    ],
                    "available_signals": snapshot.available_signals,
                    "missing_signals": snapshot.missing_signals,
                    "raw_sections": [
                        {
                            "heading": section.heading,
                            "text": section.text,
                            "source_label": section.source_label,
                            "note": section.note,
                        }
                        for section in snapshot.raw_sections
                        if section.heading or section.text
                    ],
                    "notes": snapshot.notes,
                }
                for snapshot in self.source_snapshots
                if snapshot.label
            ]

        return {
            "company_profile_static": static_fields,
            "company_insights": insight_fields,
        }


def render_company_profile_markdown(profile: CompanyProfileContent) -> str:
    lines: list[str] = [f"# {profile.company_name}", ""]

    meta_lines = []
    if profile.source_platform:
        meta_lines.append(f"- 来源平台: {profile.source_platform}")
    if profile.source_url:
        meta_lines.append(f"- 原始链接: {profile.source_url}")
    if profile.headquarters:
        meta_lines.append(f"- 总部: {profile.headquarters}")
    if profile.industry:
        meta_lines.append(f"- 行业: {profile.industry}")
    if profile.followers_text:
        meta_lines.append(f"- Followers: {profile.followers_text}")
    if profile.employee_size_text:
        meta_lines.append(f"- 员工规模: {profile.employee_size_text}")
    if profile.employees_on_platform_text:
        meta_lines.append(f"- 平台员工数: {profile.employees_on_platform_text}")
    if meta_lines:
        lines.extend(meta_lines)
        lines.append("")

    if profile.company_tagline:
        lines.append("## Company Tagline")
        lines.append("")
        lines.append(profile.company_tagline)
        lines.append("")

    if profile.company_description:
        lines.append("## Company Description")
        lines.append("")
        lines.append(profile.company_description)
        lines.append("")

    if profile.headline_metrics:
        lines.append("## Headline Metrics")
        lines.append("")
        for key, value in profile.headline_metrics.items():
            lines.append(f"- {humanize_metric_name(key)}: {value}")
        lines.append("")

    if profile.bridge_signals:
        lines.append("## Bridge Signals")
        lines.append("")
        for item in profile.bridge_signals:
            lines.append(f"- {item}")
        lines.append("")

    if profile.competitor_names:
        lines.append("## Competitors")
        lines.append("")
        for name in profile.competitor_names:
            lines.append(f"- {name}")
        lines.append("")

    if profile.featured_customers:
        lines.append("## Featured Customers")
        lines.append("")
        for customer in profile.featured_customers:
            lines.append(f"- {customer}")
        lines.append("")

    for section in profile.narrative_sections:
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
        if section.sources:
            lines.append(f"Sources: {', '.join(section.sources)}")
            lines.append("")

    for table in profile.metric_tables:
        if not table.title:
            continue
        lines.append(f"## {table.title}")
        lines.append("")
        if table.note:
            lines.append(table.note)
            lines.append("")
        if table.columns:
            lines.append(f"Columns: {', '.join(table.columns)}")
            lines.append("")
        for row in table.rows:
            if not row.label:
                continue
            value_summary = ", ".join(f"{column}: {value}" for column, value in row.values.items())
            lines.append(f"- {row.label}: {value_summary}" if value_summary else f"- {row.label}")
        if table.rows:
            lines.append("")

    for series in profile.time_series:
        if not series.title:
            continue
        lines.append(f"## {series.title}")
        lines.append("")
        if series.note:
            lines.append(series.note)
            lines.append("")
        for point in series.points:
            point_line = f"- {point.label}: {point.value}"
            if point.note:
                point_line += f" ({point.note})"
            lines.append(point_line)
        if series.points:
            lines.append("")

    if profile.notable_alumni:
        lines.append("## Notable Alumni")
        lines.append("")
        for alumnus in profile.notable_alumni:
            parts = [alumnus.name]
            if alumnus.degree:
                parts.append(alumnus.degree)
            if alumnus.current_role:
                parts.append(f"current: {alumnus.current_role}")
            if alumnus.previous_role:
                parts.append(f"previous: {alumnus.previous_role}")
            lines.append(f"- {' | '.join(parts)}")
        lines.append("")

    if profile.related_pages:
        lines.append("## Related Pages")
        lines.append("")
        for page in profile.related_pages:
            parts = [page.label]
            if page.relationship:
                parts.append(f"relationship: {page.relationship}")
            if page.source:
                parts.append(f"source: {page.source}")
            if page.url:
                parts.append(page.url)
            if page.note:
                parts.append(f"note: {page.note}")
            lines.append(f"- {' | '.join(parts)}")
        lines.append("")

    if profile.available_signals:
        lines.append("## Available Signals")
        lines.append("")
        for signal in profile.available_signals:
            lines.append(f"- {signal}")
        lines.append("")

    if profile.missing_signals:
        lines.append("## Missing Signals")
        lines.append("")
        for signal in profile.missing_signals:
            lines.append(f"- {signal}")
        lines.append("")

    if profile.raw_sections:
        lines.append("## Raw Sections")
        lines.append("")
        for section in profile.raw_sections:
            title = section.heading or "Untitled"
            lines.append(f"### {title}")
            lines.append("")
            if section.source_label:
                lines.append(f"- Source: {section.source_label}")
            if section.note:
                lines.append(f"- Note: {section.note}")
            if section.source_label or section.note:
                lines.append("")
            lines.append(section.text)
            lines.append("")

    if profile.source_snapshots:
        lines.append("## Source Snapshots")
        lines.append("")
        for snapshot in profile.source_snapshots:
            if not snapshot.label:
                continue
            lines.append(f"### {snapshot.label}")
            lines.append("")
            snapshot_meta = []
            if snapshot.source_kind:
                snapshot_meta.append(f"- 类型: {snapshot.source_kind}")
            if snapshot.source_platform:
                snapshot_meta.append(f"- 平台: {snapshot.source_platform}")
            if snapshot.source_url:
                snapshot_meta.append(f"- 链接: {snapshot.source_url}")
            if snapshot_meta:
                lines.extend(snapshot_meta)
                lines.append("")
            if snapshot.headline_metrics:
                for key, value in snapshot.headline_metrics.items():
                    lines.append(f"- {humanize_metric_name(key)}: {value}")
                lines.append("")
            for item in snapshot.bridge_signals:
                lines.append(f"- Bridge signal: {item}")
            if snapshot.bridge_signals:
                lines.append("")
            for name in snapshot.competitor_names:
                lines.append(f"- Competitor: {name}")
            if snapshot.competitor_names:
                lines.append("")
            for section in snapshot.narrative_sections:
                if not section.heading:
                    continue
                lines.append(f"- Section: {section.heading}")
            if snapshot.narrative_sections:
                lines.append("")
            for table in snapshot.metric_tables:
                if not table.title:
                    continue
                lines.append(f"- Table: {table.title}")
            if snapshot.metric_tables:
                lines.append("")
            for series in snapshot.time_series:
                if not series.title:
                    continue
                lines.append(f"- Time series: {series.title}")
            if snapshot.time_series:
                lines.append("")
            for alumnus in snapshot.notable_alumni:
                lines.append(f"- Alumnus: {alumnus.name}")
            if snapshot.notable_alumni:
                lines.append("")
            for page in snapshot.related_pages:
                parts = [page.label]
                if page.relationship:
                    parts.append(page.relationship)
                if page.url:
                    parts.append(page.url)
                lines.append(f"- Related page: {' | '.join(parts)}")
            if snapshot.related_pages:
                lines.append("")
            for signal in snapshot.available_signals:
                lines.append(f"- Available signal: {signal}")
            if snapshot.available_signals:
                lines.append("")
            for signal in snapshot.missing_signals:
                lines.append(f"- Missing signal: {signal}")
            if snapshot.missing_signals:
                lines.append("")
            for section in snapshot.raw_sections:
                title = section.heading or "Untitled"
                lines.append(f"- Raw section: {title}")
            if snapshot.raw_sections:
                lines.append("")
            for note in snapshot.notes:
                lines.append(f"- Note: {note}")
            if snapshot.notes:
                lines.append("")

    if profile.notes:
        lines.append("## Capture Notes")
        lines.append("")
        for note in profile.notes:
            lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def build_company_subject_key(company_name: str, source_url: str | None = None) -> str:
    slug = _slugify(company_name)
    platform = detect_source_platform(source_url) if source_url else None
    if platform:
        return f"{platform}:{slug}"
    return slug


def detect_source_platform(url: str | None) -> str | None:
    if not url:
        return None
    host = urlparse(url).netloc.lower()
    if not host:
        return None
    host = re.sub(r"^www\.", "", host)
    if host.endswith("linkedin.com"):
        return "linkedin"
    if host.endswith("indeed.com"):
        return "indeed"
    if host.endswith("glassdoor.com"):
        return "glassdoor"
    if host.endswith("ycombinator.com"):
        return "ycombinator"
    if "meeboss" in host:
        return "meeboss"
    return host


def humanize_metric_name(metric_name: str) -> str:
    text = metric_name.replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else metric_name


def _parse_narrative_sections(values: list[dict[str, Any]]) -> list[CompanyNarrativeSection]:
    sections: list[CompanyNarrativeSection] = []
    for raw in values:
        sections.append(
            CompanyNarrativeSection(
                heading=str(raw.get("heading", "")).strip(),
                paragraphs=[_clean_text(item) for item in raw.get("paragraphs", []) if _clean_text(item)],
                bullets=[_clean_text(item) for item in raw.get("bullets", []) if _clean_text(item)],
                sources=[_clean_text(item) for item in raw.get("sources", []) if _clean_text(item)],
            )
        )
    return sections


def _parse_metric_tables(values: list[dict[str, Any]]) -> list[CompanyMetricTable]:
    metric_tables: list[CompanyMetricTable] = []
    for raw_table in values:
        rows = []
        for raw_row in raw_table.get("rows", []):
            rows.append(
                CompanyMetricRow(
                    label=str(raw_row.get("label", "")).strip(),
                    values={
                        str(key).strip(): str(value).strip()
                        for key, value in _normalize_metric_map(raw_row.get("values", raw_row.get("cells"))).items()
                        if str(key).strip() and str(value).strip()
                    },
                )
            )
        metric_tables.append(
            CompanyMetricTable(
                title=str(raw_table.get("title", "")).strip(),
                columns=[_clean_text(item) for item in raw_table.get("columns", []) if _clean_text(item)],
                rows=rows,
                note=_optional_text(raw_table.get("note")),
            )
        )
    return metric_tables


def _parse_time_series(values: list[dict[str, Any]]) -> list[CompanyTimeSeries]:
    time_series: list[CompanyTimeSeries] = []
    for raw_series in values:
        points = []
        for raw_point in raw_series.get("points", []):
            label = _clean_text(raw_point.get("label"))
            value = _clean_text(raw_point.get("value"))
            if not label or not value:
                continue
            points.append(
                TimeSeriesPoint(
                    label=label,
                    value=value,
                    note=_optional_text(raw_point.get("note")),
                )
            )
        time_series.append(
            CompanyTimeSeries(
                title=str(raw_series.get("title", "")).strip(),
                points=points,
                note=_optional_text(raw_series.get("note")),
            )
        )
    return time_series


def _parse_notable_alumni(values: list[dict[str, Any]]) -> list[NotableAlumnus]:
    notable_alumni: list[NotableAlumnus] = []
    for raw in values:
        name = _clean_text(raw.get("name"))
        if not name:
            continue
        notable_alumni.append(
            NotableAlumnus(
                name=name,
                degree=_optional_text(raw.get("degree")),
                current_role=_optional_text(raw.get("current_role")),
                previous_role=_optional_text(raw.get("previous_role")),
            )
        )
    return notable_alumni


def _parse_related_pages(values: list[dict[str, Any]]) -> list[CompanyRelatedPage]:
    related_pages: list[CompanyRelatedPage] = []
    for raw in values:
        label = _clean_text(raw.get("label"))
        if not label:
            continue
        related_pages.append(
            CompanyRelatedPage(
                label=label,
                url=_optional_text(raw.get("url")),
                relationship=_optional_text(raw.get("relationship")),
                source=_optional_text(raw.get("source")),
                note=_optional_text(raw.get("note")),
            )
        )
    return related_pages


def _parse_raw_sections(values: list[dict[str, Any]]) -> list[CompanyRawSection]:
    raw_sections: list[CompanyRawSection] = []
    for raw in values:
        heading = _clean_text(raw.get("heading"))
        text = _clean_text(raw.get("text"))
        if not heading and not text:
            continue
        raw_sections.append(
            CompanyRawSection(
                heading=heading,
                text=text,
                source_label=_optional_text(raw.get("source_label")),
                note=_optional_text(raw.get("note")),
            )
        )
    return raw_sections


def _parse_source_snapshots(values: list[dict[str, Any]]) -> list[CompanySourceSnapshot]:
    snapshots: list[CompanySourceSnapshot] = []
    for raw in values:
        label = _clean_text(raw.get("label"))
        if not label:
            continue
        source_url = _optional_text(raw.get("source_url"))
        source_platform = _optional_text(raw.get("source_platform")) or detect_source_platform(source_url)
        snapshots.append(
            CompanySourceSnapshot(
                label=label,
                source_url=source_url,
                source_platform=source_platform,
                source_kind=_optional_text(raw.get("source_kind")),
                headline_metrics={key: value for key, value in _normalize_metric_map(raw.get("headline_metrics")).items() if key},
                bridge_signals=[_clean_text(item) for item in raw.get("bridge_signals", []) if _clean_text(item)],
                competitor_names=[_clean_text(item) for item in raw.get("competitor_names", []) if _clean_text(item)],
                narrative_sections=_parse_narrative_sections(raw.get("narrative_sections", raw.get("sections", []))),
                metric_tables=_parse_metric_tables(raw.get("metric_tables", [])),
                time_series=_parse_time_series(raw.get("time_series", [])),
                notable_alumni=_parse_notable_alumni(raw.get("notable_alumni", [])),
                related_pages=_parse_related_pages(raw.get("related_pages", [])),
                available_signals=[_clean_text(item) for item in raw.get("available_signals", []) if _clean_text(item)],
                missing_signals=[_clean_text(item) for item in raw.get("missing_signals", []) if _clean_text(item)],
                raw_sections=_parse_raw_sections(raw.get("raw_sections", [])),
                notes=[_clean_text(item) for item in raw.get("notes", []) if _clean_text(item)],
            )
        )
    return snapshots


def _required_text(value: Any, field_name: str) -> str:
    text = _optional_text(value)
    if not text:
        raise ValueError(f"{field_name} is required.")
    return text


def _optional_text(value: Any) -> str | None:
    text = _clean_text(value)
    return text or None


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_metric_map(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            str(key).strip(): raw_value
            for key, raw_value in value.items()
            if str(key).strip()
        }
    if isinstance(value, list):
        normalized: dict[str, Any] = {}
        for item in value:
            if not isinstance(item, dict):
                continue
            key = _clean_text(item.get("name") or item.get("label") or item.get("column"))
            raw_value = item.get("value")
            if not key or raw_value in (None, ""):
                continue
            normalized[key] = raw_value
        return normalized
    return {}


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower())
    return cleaned.strip("-") or "unknown-company"
