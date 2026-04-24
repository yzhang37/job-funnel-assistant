from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

from job_search_assistant.runtime.config_files import ensure_config_file

from .frequency import SUPPORTED_TRACKER_FREQUENCIES, normalize_source_frequency
from .models import TrackerConfig, TrackerDefinition


VALID_FREQUENCIES = set(SUPPORTED_TRACKER_FREQUENCIES)
TRACKER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def load_tracker_config(path: str | Path) -> TrackerConfig:
    config_path = Path(path)
    if not config_path.exists() and not config_path.is_absolute():
        repo_root = Path(__file__).resolve().parents[3]
        config_path = ensure_config_file(repo_root, config_path)
    payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    version = _parse_positive_int(payload.get("version", 1), field_name="version")
    raw_trackers = payload.get("trackers")
    if not isinstance(raw_trackers, list) or not raw_trackers:
        raise ValueError("Tracker config requires a non-empty 'trackers' array.")

    trackers: list[TrackerDefinition] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_trackers, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Tracker entry #{index} must be a table/object.")
        tracker = _parse_tracker(raw)
        if tracker.id in seen_ids:
            raise ValueError(f"Duplicate tracker id found: {tracker.id}")
        seen_ids.add(tracker.id)
        trackers.append(tracker)

    return TrackerConfig(version=version, trackers=trackers)


def _parse_tracker(payload: dict[str, Any]) -> TrackerDefinition:
    tracker_id = _required_text(payload.get("id"), field_name="id")
    if not TRACKER_ID_PATTERN.match(tracker_id):
        raise ValueError(
            "Tracker id must match ^[a-z0-9][a-z0-9_-]*$ "
            f"(got {tracker_id!r})."
        )

    source_frequency = normalize_source_frequency(
        _required_text(payload.get("source_frequency"), field_name="source_frequency")
    )
    if source_frequency not in VALID_FREQUENCIES:
        raise ValueError(
            f"Unsupported source_frequency {source_frequency!r}. "
            f"Expected one of: {', '.join(sorted(VALID_FREQUENCIES))}."
        )

    return TrackerDefinition(
        id=tracker_id,
        label=_required_text(payload.get("label"), field_name="label"),
        url=_required_text(payload.get("url"), field_name="url"),
        source_frequency=source_frequency,
        target_new_jobs=_parse_positive_int(payload.get("target_new_jobs", 30), field_name="target_new_jobs"),
        enabled=_parse_bool(payload.get("enabled", True), field_name="enabled"),
    )


def _required_text(value: Any, *, field_name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"Tracker config field {field_name!r} must be a non-empty string.")
    return text


def _parse_positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Tracker config field {field_name!r} must be an integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Tracker config field {field_name!r} must be an integer.") from exc
    if parsed <= 0:
        raise ValueError(f"Tracker config field {field_name!r} must be > 0.")
    return parsed


def _parse_bool(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"Tracker config field {field_name!r} must be true or false.")
