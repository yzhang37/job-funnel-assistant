from __future__ import annotations

import os
from pathlib import Path


def load_local_env(repo_root: Path, filename: str = ".env.local", overwrite: bool = False) -> Path | None:
    env_path = repo_root / filename
    if not env_path.exists():
        return None

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if not key:
            continue
        if overwrite or key not in os.environ:
            os.environ[key] = value
    return env_path
