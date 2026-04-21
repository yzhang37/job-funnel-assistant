from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any


DURATION_PATTERN = re.compile(r"(?P<value>\d+)(?P<unit>[smhdw])")


@dataclass(frozen=True)
class ResolvedCachePolicy:
    namespace: str
    field_name: str | None
    source_platform: str | None
    subject_key: str | None
    fresh_for: timedelta
    stale_for: timedelta
    matched_rule: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "field_name": self.field_name,
            "source_platform": self.source_platform,
            "subject_key": self.subject_key,
            "fresh_for_seconds": int(self.fresh_for.total_seconds()),
            "stale_for_seconds": int(self.stale_for.total_seconds()),
            "matched_rule": self.matched_rule,
        }


class CachePolicyRegistry:
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._defaults = config.get("defaults", {})
        self._profiles = config.get("profiles", {})
        self._rules = list(config.get("rules", []))

    @classmethod
    def from_file(cls, path: str | Path) -> "CachePolicyRegistry":
        config_path = Path(path)
        with config_path.open("rb") as fh:
            return cls(tomllib.load(fh))

    def resolve(
        self,
        *,
        namespace: str,
        field_name: str | None = None,
        source_platform: str | None = None,
        subject_key: str | None = None,
    ) -> ResolvedCachePolicy:
        merged = dict(self._defaults)
        merged.update(self._profiles.get(namespace, {}))
        matched_rule = self._pick_rule(
            namespace=namespace,
            field_name=field_name,
            source_platform=source_platform,
            subject_key=subject_key,
        )
        if matched_rule:
            merged.update(
                {
                    key: value
                    for key, value in matched_rule.items()
                    if key not in {"namespace", "field", "source_platform", "subject_key_prefix"}
                }
            )

        if "fresh_for" not in merged or "stale_for" not in merged:
            raise ValueError(f"Cache policy for namespace={namespace!r} is missing fresh_for/stale_for.")

        fresh_for = parse_duration(merged["fresh_for"])
        stale_for = parse_duration(merged["stale_for"])
        if stale_for < fresh_for:
            raise ValueError(
                f"Cache policy for namespace={namespace!r} has stale_for earlier than fresh_for."
            )

        return ResolvedCachePolicy(
            namespace=namespace,
            field_name=field_name,
            source_platform=source_platform,
            subject_key=subject_key,
            fresh_for=fresh_for,
            stale_for=stale_for,
            matched_rule=matched_rule,
        )

    def _pick_rule(
        self,
        *,
        namespace: str,
        field_name: str | None,
        source_platform: str | None,
        subject_key: str | None,
    ) -> dict[str, Any] | None:
        winner: tuple[int, int, dict[str, Any]] | None = None
        for index, rule in enumerate(self._rules):
            if rule.get("namespace") and rule["namespace"] != namespace:
                continue
            if rule.get("field") and rule["field"] != field_name:
                continue
            if rule.get("source_platform") and rule["source_platform"] != source_platform:
                continue
            if rule.get("subject_key_prefix"):
                if not subject_key or not subject_key.startswith(rule["subject_key_prefix"]):
                    continue

            specificity = sum(
                1
                for selector in ("namespace", "field", "source_platform", "subject_key_prefix")
                if rule.get(selector)
            )
            candidate = (specificity, index, rule)
            if winner is None or candidate[:2] > winner[:2]:
                winner = candidate
        return winner[2] if winner else None


def parse_duration(raw: str) -> timedelta:
    text = raw.strip().lower()
    if not text:
        raise ValueError("Duration cannot be empty.")

    position = 0
    total_seconds = 0
    for match in DURATION_PATTERN.finditer(text):
        if match.start() != position:
            raise ValueError(f"Unsupported duration segment in {raw!r}.")
        value = int(match.group("value"))
        unit = match.group("unit")
        position = match.end()

        multiplier = {
            "s": 1,
            "m": 60,
            "h": 3600,
            "d": 86400,
            "w": 604800,
        }[unit]
        total_seconds += value * multiplier

    if position != len(text):
        raise ValueError(f"Unsupported duration format: {raw!r}")
    return timedelta(seconds=total_seconds)

