from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .cache import write_company_profile_cache, write_job_posting_cache
from .company_profile import CompanyProfileContent, render_company_profile_markdown
from .jd_markdown import JobPostingContent, render_jd_markdown


BUNDLE_VERSION = "0.1"


@dataclass
class BundleAttachment:
    path: Path
    kind: str = "file"
    label: str | None = None
    note: str | None = None

    @classmethod
    def from_value(cls, value: str | Path | dict[str, Any]) -> "BundleAttachment":
        if isinstance(value, (str, Path)):
            return cls(path=Path(value).expanduser().resolve())

        raw_path = value.get("path")
        if not raw_path:
            raise ValueError("Attachment payload requires a non-empty 'path'.")
        return cls(
            path=Path(raw_path).expanduser().resolve(),
            kind=_clean_text(value.get("kind")) or "file",
            label=_clean_text(value.get("label")),
            note=_clean_text(value.get("note")),
        )


def build_job_capture_bundle(
    *,
    output_dir: str | Path,
    posting: JobPostingContent,
    company_profile: CompanyProfileContent | None = None,
    attachments: list[str | Path | dict[str, Any]] | None = None,
    source_inputs: dict[str, Any] | None = None,
    notes: list[str] | None = None,
    repo_root: str | Path | None = None,
    cache_db: str | Path | None = None,
    cache_config: str | Path | None = None,
) -> Path:
    bundle_dir = Path(output_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    artifacts: list[dict[str, Any]] = []
    copied_attachments = _copy_attachments(bundle_dir, attachments or [])

    job_payload_path = bundle_dir / "job_posting.json"
    _write_json(job_payload_path, asdict(posting))
    artifacts.append(_artifact_entry("job_posting", "json", job_payload_path, bundle_dir))

    jd_markdown_path = bundle_dir / "jd.md"
    jd_markdown_path.write_text(render_jd_markdown(posting), encoding="utf-8")
    artifacts.append(_artifact_entry("jd_markdown", "markdown", jd_markdown_path, bundle_dir))

    available_outputs = ["job_posting", "jd_markdown"]
    company_name = posting.company
    cache_summary: dict[str, dict[str, int]] = {}

    if repo_root is not None:
        cache_summary["job_posting"] = write_job_posting_cache(
            posting,
            repo_root=Path(repo_root).expanduser().resolve(),
            cache_db=Path(cache_db).expanduser().resolve() if cache_db else None,
            cache_config=Path(cache_config).expanduser().resolve() if cache_config else None,
            metadata={
                "bundle_kind": "job_capture",
                "bundle_dir": str(bundle_dir),
            },
        )

    if company_profile is not None:
        company_payload_path = bundle_dir / "company_profile.json"
        _write_json(company_payload_path, asdict(company_profile))
        artifacts.append(_artifact_entry("company_profile", "json", company_payload_path, bundle_dir))

        company_markdown_path = bundle_dir / "company_profile.md"
        company_markdown_path.write_text(render_company_profile_markdown(company_profile), encoding="utf-8")
        artifacts.append(_artifact_entry("company_profile_markdown", "markdown", company_markdown_path, bundle_dir))
        available_outputs.extend(["company_profile", "company_profile_markdown"])
        company_name = company_name or company_profile.company_name
        if repo_root is not None:
            cache_summary["company_profile"] = write_company_profile_cache(
                company_profile,
                repo_root=Path(repo_root).expanduser().resolve(),
                cache_db=Path(cache_db).expanduser().resolve() if cache_db else None,
                cache_config=Path(cache_config).expanduser().resolve() if cache_config else None,
                metadata={
                    "bundle_kind": "job_capture",
                    "bundle_dir": str(bundle_dir),
                },
            )

    manifest = {
        "bundle_version": BUNDLE_VERSION,
        "bundle_kind": "job_capture",
        "generated_at": _iso_utc_now(),
        "subject": {
            "company_name": company_name,
            "job_title": posting.title,
        },
        "source_inputs": _compact_dict(
            {
                "job_url": posting.source_url,
                "company_name": company_name,
                **(source_inputs or {}),
            }
        ),
        "artifacts": artifacts,
        "attachments": copied_attachments,
        "available_outputs": available_outputs,
        "cache": _compact_dict(
            {
                **cache_summary,
            }
        ),
        "notes": [note for note in (notes or []) if note],
    }
    manifest_path = bundle_dir / "manifest.json"
    _write_json(manifest_path, manifest)
    return manifest_path


def build_company_profile_bundle(
    *,
    output_dir: str | Path,
    company_profile: CompanyProfileContent,
    attachments: list[str | Path | dict[str, Any]] | None = None,
    source_inputs: dict[str, Any] | None = None,
    notes: list[str] | None = None,
    repo_root: str | Path | None = None,
    cache_db: str | Path | None = None,
    cache_config: str | Path | None = None,
) -> Path:
    bundle_dir = Path(output_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    artifacts: list[dict[str, Any]] = []
    copied_attachments = _copy_attachments(bundle_dir, attachments or [])
    cache_summary: dict[str, int] = {}

    company_payload_path = bundle_dir / "company_profile.json"
    _write_json(company_payload_path, asdict(company_profile))
    artifacts.append(_artifact_entry("company_profile", "json", company_payload_path, bundle_dir))

    company_markdown_path = bundle_dir / "company_profile.md"
    company_markdown_path.write_text(render_company_profile_markdown(company_profile), encoding="utf-8")
    artifacts.append(_artifact_entry("company_profile_markdown", "markdown", company_markdown_path, bundle_dir))
    if repo_root is not None:
        cache_summary = write_company_profile_cache(
            company_profile,
            repo_root=Path(repo_root).expanduser().resolve(),
            cache_db=Path(cache_db).expanduser().resolve() if cache_db else None,
            cache_config=Path(cache_config).expanduser().resolve() if cache_config else None,
            metadata={
                "bundle_kind": "company_profile_capture",
                "bundle_dir": str(bundle_dir),
            },
        )

    manifest = {
        "bundle_version": BUNDLE_VERSION,
        "bundle_kind": "company_profile_capture",
        "generated_at": _iso_utc_now(),
        "subject": {
            "company_name": company_profile.company_name,
        },
        "source_inputs": _compact_dict(
            {
                "company_name": company_profile.company_name,
                "company_url": company_profile.source_url,
                **(source_inputs or {}),
            }
        ),
        "artifacts": artifacts,
        "attachments": copied_attachments,
        "available_outputs": ["company_profile", "company_profile_markdown"],
        "cache": _compact_dict(
            {
                "company_profile": cache_summary or None,
            }
        ),
        "notes": [note for note in (notes or []) if note],
    }
    manifest_path = bundle_dir / "manifest.json"
    _write_json(manifest_path, manifest)
    return manifest_path


def _copy_attachments(bundle_dir: Path, values: list[str | Path | dict[str, Any]]) -> list[dict[str, Any]]:
    if not values:
        return []

    attachments_dir = bundle_dir / "attachments"
    attachments_dir.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, Any]] = []
    used_names: set[str] = set()

    for raw in values:
        attachment = BundleAttachment.from_value(raw)
        if not attachment.path.exists():
            raise FileNotFoundError(f"Attachment path does not exist: {attachment.path}")

        target_name = _unique_attachment_name(attachments_dir, used_names, attachment.path.name)
        target_path = attachments_dir / target_name
        shutil.copy2(attachment.path, target_path)
        used_names.add(target_name)

        copied.append(
            _compact_dict(
                {
                    "path": str(target_path.relative_to(bundle_dir)),
                    "kind": attachment.kind,
                    "label": attachment.label,
                    "note": attachment.note,
                    "original_name": attachment.path.name,
                }
            )
        )
    return copied


def _unique_attachment_name(attachments_dir: Path, used_names: set[str], file_name: str) -> str:
    candidate = _sanitize_file_name(file_name)
    stem = Path(candidate).stem or "attachment"
    suffix = Path(candidate).suffix
    counter = 2
    while candidate in used_names or (attachments_dir / candidate).exists():
        candidate = f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate


def _sanitize_file_name(file_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", file_name).strip("-")
    return cleaned or "attachment"


def _artifact_entry(role: str, kind: str, path: Path, bundle_dir: Path) -> dict[str, str]:
    return {
        "role": role,
        "kind": kind,
        "path": str(path.relative_to(bundle_dir)),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _compact_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
