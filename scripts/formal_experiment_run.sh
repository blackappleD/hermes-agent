#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PYTHON_BIN="${PYTHON:-}"
if [ -z "$PYTHON_BIN" ] && [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
  PYTHON_BIN="$VIRTUAL_ENV/bin/python"
fi
if [ -z "$PYTHON_BIN" ]; then
  for candidate in "$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/venv/bin/python" "$HOME/.hermes/hermes-agent/venv/bin/python"; do
    if [ -x "$candidate" ]; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi
if [ -z "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3 || command -v python || true)"
fi
if [ -z "$PYTHON_BIN" ]; then
  echo "error: no Python interpreter found; create a venv with: python3 -m venv .venv && . .venv/bin/activate && python -m pip install -e ." >&2
  exit 1
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/formal_experiment_lib.py" run "$@"
