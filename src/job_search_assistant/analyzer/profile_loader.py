from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LoadedProfile:
    fragments: list[Path]
    combined_markdown: str


def load_profile_stack(
    repo_root: Path,
    stack_path: str | Path,
    extra_fragments: list[str] | None = None,
) -> LoadedProfile:
    stack_file = _resolve_path(repo_root, Path(stack_path))
    config = json.loads(stack_file.read_text(encoding="utf-8"))
    fragment_specs = list(config.get("fragments", []))
    if extra_fragments:
        fragment_specs.extend(extra_fragments)

    resolved = [_resolve_fragment(stack_file.parent, repo_root, spec) for spec in fragment_specs]
    combined = []
    for path in resolved:
        combined.append(f"## Fragment: {path.stem}\n")
        combined.append(path.read_text(encoding="utf-8").strip())
        combined.append("\n")
    return LoadedProfile(fragments=resolved, combined_markdown="\n".join(combined).strip())


def _resolve_fragment(stack_dir: Path, repo_root: Path, fragment_spec: str) -> Path:
    candidate = Path(fragment_spec)
    if candidate.is_absolute():
        return candidate
    stack_relative = (stack_dir / candidate).resolve()
    if stack_relative.exists():
        return stack_relative
    return _resolve_path(repo_root, candidate)


def _resolve_path(repo_root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    resolved = (repo_root / path).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Path not found: {resolved}")
    return resolved

