from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo


_UTC = timezone.utc
_SEATTLE = ZoneInfo("America/Los_Angeles")
_LEVEL_NAMES = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARN",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "ERROR",
}


class _MaxLevelFilter(logging.Filter):
    def __init__(self, max_level: int) -> None:
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.max_level


class JobSearchLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        utc_dt = datetime.fromtimestamp(record.created, _UTC)
        seattle_dt = utc_dt.astimezone(_SEATTLE)
        record.utc_iso = utc_dt.isoformat(timespec="seconds").replace("+00:00", "Z")
        record.seattle_human = seattle_dt.strftime("%Y-%m-%d %H:%M:%S %Z")
        record.level_short = _LEVEL_NAMES.get(record.levelno, record.levelname)
        return super().format(record)


def configure_logging(level: str | int | None = None, *, force: bool = False) -> None:
    resolved_level = _resolve_level(level or os.getenv("JOB_SEARCH_LOG_LEVEL") or "INFO")
    root = logging.getLogger()
    if root.handlers and not force:
        root.setLevel(resolved_level)
        return

    root.handlers.clear()
    root.setLevel(resolved_level)

    formatter = JobSearchLogFormatter(
        fmt="%(utc_iso)s [%(seattle_human)s] %(level_short)s %(name)s %(message)s"
    )

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.addFilter(_MaxLevelFilter(logging.INFO))
    stdout_handler.setFormatter(formatter)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(formatter)

    root.addHandler(stdout_handler)
    root.addHandler(stderr_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def format_kv(event: str, /, **fields: Any) -> str:
    parts = [f"event={event}"]
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={_stringify_value(value)}")
    return " ".join(parts)


def _resolve_level(level: str | int) -> int:
    if isinstance(level, int):
        return level
    normalized = str(level).strip().upper()
    aliases = {
        "WARN": logging.WARNING,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
    }
    return aliases.get(normalized, logging.INFO)


def _stringify_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\n", "\\n")
    if not text:
        return '""'
    if any(ch.isspace() for ch in text) or any(ch in text for ch in "\"'=[]{}(),"):
        return json.dumps(text, ensure_ascii=False)
    return text
