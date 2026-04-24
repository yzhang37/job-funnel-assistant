#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_search_assistant.runtime import configure_logging, format_kv, get_logger
from job_search_assistant.runtime.config_files import DEFAULT_TEMPLATE_MAP, ensure_config_files


logger = get_logger("runtime.config")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize missing local config files from tracked templates.")
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        help="Specific config path to initialize. Defaults to all known local config files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(force=True)
    config_paths = args.config or sorted(DEFAULT_TEMPLATE_MAP)
    created_or_existing = ensure_config_files(ROOT, config_paths)
    logger.info(
        format_kv(
            "runtime.config.initialized",
            files=",".join(str(path.relative_to(ROOT)) for path in created_or_existing),
        )
    )


if __name__ == "__main__":
    main()
