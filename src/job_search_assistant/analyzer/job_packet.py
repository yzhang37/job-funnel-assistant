from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


TITLE_HINTS = [
    r"(?P<title>Senior [A-Za-z /-]+Engineer)",
    r"(?P<title>Software Engineer(?: [IVX]+)?)",
    r"(?P<title>Backend Engineer)",
    r"(?P<title>Platform Engineer)",
    r"(?P<title>Infrastructure Engineer)",
]


@dataclass
class JobPacket:
    company_name: str | None
    guessed_title: str | None
    job_url: str | None
    raw_jd_text: str
    special_questions: str | None
    image_paths: list[Path]
    notes: str | None

    def to_payload(self) -> dict[str, object]:
        return {
            "company_name": self.company_name,
            "guessed_title": self.guessed_title,
            "job_url": self.job_url,
            "raw_jd_text": self.raw_jd_text,
            "special_questions": self.special_questions,
            "attached_image_paths": [str(path) for path in self.image_paths],
            "notes": self.notes,
        }


def build_job_packet(
    *,
    jd_text: str,
    company_name: str | None = None,
    job_url: str | None = None,
    special_questions: str | None = None,
    image_paths: list[str] | None = None,
    notes: str | None = None,
) -> JobPacket:
    resolved_images = [Path(path).resolve() for path in (image_paths or [])]
    return JobPacket(
        company_name=company_name or infer_company_name(jd_text),
        guessed_title=infer_title(jd_text),
        job_url=job_url,
        raw_jd_text=jd_text.strip(),
        special_questions=special_questions.strip() if special_questions else None,
        image_paths=resolved_images,
        notes=notes.strip() if notes else None,
    )


def load_text_input(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def infer_company_name(jd_text: str) -> str | None:
    lines = [line.strip() for line in jd_text.splitlines() if line.strip()]
    if not lines:
        return None
    for line in lines[:8]:
        if re.search(r"\b(at|@)\b", line, flags=re.IGNORECASE):
            parts = re.split(r"\b(?:at|@)\b", line, maxsplit=1, flags=re.IGNORECASE)
            if len(parts) == 2 and parts[1].strip():
                return parts[1].strip(" -|")
    if len(lines) >= 2 and len(lines[1].split()) <= 8:
        return lines[1]
    return None


def infer_title(jd_text: str) -> str | None:
    lines = [line.strip() for line in jd_text.splitlines() if line.strip()]
    for line in lines[:12]:
        for pattern in TITLE_HINTS:
            match = re.search(pattern, line)
            if match:
                return match.group("title")
    return lines[0] if lines else None


def write_json(path: str | Path, payload: dict[str, object]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

