#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
V2_ROOT="$ROOT/v2"
TMP_ROOT="${TMPDIR:-/tmp}"
TMP_ROOT="${TMP_ROOT%/}"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$TMP_ROOT/wiki-polis-uv-cache}"
export PRE_COMMIT_HOME="${PRE_COMMIT_HOME:-$TMP_ROOT/wiki-polis-pre-commit-cache}"
export PYLINTHOME="${PYLINTHOME:-$TMP_ROOT/wiki-polis-pylint-cache}"

mkdir -p "$UV_CACHE_DIR" "$PRE_COMMIT_HOME" "$PYLINTHOME"

if command -v uv >/dev/null 2>&1; then
  UV_BIN="$(command -v uv)"
elif [ -x "$V2_ROOT/.venv/bin/uv" ]; then
  UV_BIN="$V2_ROOT/.venv/bin/uv"
else
  echo "uv is required. Install it with Homebrew or run: $V2_ROOT/.venv/bin/python -m pip install uv" >&2
  exit 127
fi

run_uv() {
  "$UV_BIN" run --project "$V2_ROOT" "$@"
}
