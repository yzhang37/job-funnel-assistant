from __future__ import annotations

from datetime import timedelta


FREQUENCY_TO_INTERVAL = {
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
}


def resolve_frequency_interval(source_frequency: str) -> timedelta:
    try:
        return FREQUENCY_TO_INTERVAL[source_frequency]
    except KeyError as exc:
        raise ValueError(f"Unsupported source_frequency: {source_frequency!r}") from exc
