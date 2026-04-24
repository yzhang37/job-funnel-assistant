from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo


SUPPORTED_TRACKER_FREQUENCIES = (
    "daily",
    "weekly",
    "biweekly",
    "monthly",
    "bimonthly",
    "quarterly",
)
DEFAULT_TRACKER_TIMEZONE = "America/Los_Angeles"
_BIWEEKLY_ANCHOR = date(1970, 1, 5)

FREQUENCY_TO_INTERVAL = {
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
    "biweekly": timedelta(days=14),
    "monthly": timedelta(days=31),
    "bimonthly": timedelta(days=62),
    "quarterly": timedelta(days=92),
}


def resolve_frequency_interval(source_frequency: str) -> timedelta:
    frequency = normalize_source_frequency(source_frequency)
    try:
        return FREQUENCY_TO_INTERVAL[frequency]
    except KeyError as exc:
        raise ValueError(f"Unsupported source_frequency: {source_frequency!r}") from exc


def normalize_source_frequency(source_frequency: str) -> str:
    text = re.sub(r"[\s-]+", "_", str(source_frequency).strip().lower())
    aliases = {
        "2_monthly": "bimonthly",
        "two_monthly": "bimonthly",
        "every_2_months": "bimonthly",
        "every_two_months": "bimonthly",
    }
    normalized = aliases.get(text, text)
    if normalized not in SUPPORTED_TRACKER_FREQUENCIES:
        expected = ", ".join(SUPPORTED_TRACKER_FREQUENCIES)
        raise ValueError(f"Unsupported source_frequency: {source_frequency!r}. Expected one of: {expected}.")
    return normalized


def tracker_period_key(
    source_frequency: str,
    moment: datetime,
    *,
    timezone_name: str = DEFAULT_TRACKER_TIMEZONE,
) -> str:
    frequency = normalize_source_frequency(source_frequency)
    local = _as_local(moment, timezone_name)

    if frequency == "daily":
        return f"daily:{local:%Y-%m-%d}"
    if frequency == "weekly":
        iso = local.isocalendar()
        return f"weekly:{iso.year}-W{iso.week:02d}"
    if frequency == "biweekly":
        week_index = (local.date() - _BIWEEKLY_ANCHOR).days // 7
        return f"biweekly:{week_index // 2}"
    if frequency == "monthly":
        return f"monthly:{local:%Y-%m}"
    if frequency == "bimonthly":
        period_index = (local.month - 1) // 2 + 1
        return f"bimonthly:{local.year}-B{period_index}"
    if frequency == "quarterly":
        quarter = (local.month - 1) // 3 + 1
        return f"quarterly:{local.year}-Q{quarter}"

    raise ValueError(f"Unsupported source_frequency: {source_frequency!r}")


def _as_local(moment: datetime, timezone_name: str) -> datetime:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(ZoneInfo(timezone_name))
