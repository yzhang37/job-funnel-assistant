from __future__ import annotations

import shutil
from pathlib import Path


DEFAULT_TEMPLATE_MAP = {
    "config/cache_policy.toml": "config_templates/cache_policy.toml",
    "config/integrations.toml": "config_templates/integrations.toml",
    "config/runtime.toml": "config_templates/runtime.toml",
    "config/trackers.toml": "config_templates/trackers.toml",
}


def ensure_config_file(repo_root: Path, config_path: str | Path) -> Path:
    path = Path(config_path)
    target = path if path.is_absolute() else repo_root / path
    if target.exists():
        return target

    relative_key = _relative_key(repo_root, target)
    template_relative = DEFAULT_TEMPLATE_MAP.get(relative_key)
    if template_relative is None:
        raise FileNotFoundError(f"Missing config file and no template is registered: {target}")

    template = repo_root / template_relative
    if not template.exists():
        raise FileNotFoundError(f"Missing config template for {target}: {template}")

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, target)
    return target


def ensure_config_files(repo_root: Path, config_paths: list[str | Path] | tuple[str | Path, ...]) -> list[Path]:
    return [ensure_config_file(repo_root, config_path) for config_path in config_paths]


def _relative_key(repo_root: Path, target: Path) -> str:
    try:
        return target.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return target.as_posix()
