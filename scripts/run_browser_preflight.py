#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_search_assistant.runtime import format_kv, get_logger
from job_search_assistant.runtime.bootstrap import bootstrap_runtime, ensure_runtime_ready
from job_search_assistant.runtime.browser_broker import BrowserPreflightError


logger = get_logger("scripts.browser_preflight")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run browser node preflight for Codex + Computer Use.")
    parser.add_argument("--model", default="", help="Model to use for the Codex Computer Use preflight probe.")
    parser.add_argument("--force", action="store_true", help="Ignore cached preflight marker and probe again.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runtime = bootstrap_runtime(ROOT, force_logging=True)
    try:
        ensure_runtime_ready(runtime)
        model = args.model or str(runtime.settings.capture.extras.get("model", "gpt-5.4"))
        result = runtime.browser_broker.preflight(model=model, force=args.force)
        logger.info(
            format_kv(
                "browser_preflight.script.done",
                model=result.model,
                node_id=result.node_id,
                lane_name=result.lane_name,
                cached=result.cached,
                checked_at_utc=result.checked_at_utc,
                observed_app=result.observed_app,
                observed_url=result.observed_url,
                marker_path=result.marker_path,
            )
        )
    except BrowserPreflightError as exc:
        logger.error(
            format_kv(
                "browser_preflight.script.failed",
                code=exc.code,
                detail=exc.detail,
                remediation=exc.remediation,
            )
        )
        raise SystemExit(f"{exc.detail}\n{exc.remediation}") from exc
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
