#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PATH="${JOB_SEARCH_VENV_PATH:-$ROOT/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

"$PYTHON_BIN" -m venv "$VENV_PATH"
source "$VENV_PATH/bin/activate"
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r "$ROOT/requirements.txt"

echo "Runtime virtualenv ready: $VENV_PATH"
