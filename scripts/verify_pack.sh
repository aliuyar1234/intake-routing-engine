#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PY_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PY_BIN" >/dev/null 2>&1; then
  PY_BIN="python"
fi
if ! command -v "$PY_BIN" >/dev/null 2>&1; then
  PY_BIN="python.exe"
fi
if ! command -v "$PY_BIN" >/dev/null 2>&1; then
  echo "PACK_VERIFICATION_FAILED: python interpreter not found (tried python3, python, python.exe)"
  exit 40
fi

"$PY_BIN" scripts/check_placeholders.py
"$PY_BIN" scripts/check_single_definition_rule.py
"$PY_BIN" scripts/validate_schemas.py
"$PY_BIN" scripts/check_label_consistency.py
"$PY_BIN" scripts/check_manifest_completeness.py

echo "PACK_VERIFICATION_OK"
