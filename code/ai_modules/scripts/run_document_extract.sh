#!/usr/bin/env bash
# Trích xuất thông tin CCCD từ terminal (OCR + parser + LLM).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON="$ROOT/.venv/bin/python"
  else
    PYTHON="python3"
  fi
fi

FRONT="${FRONT:-../data/Thach/front_cccd.png}"
BACK="${BACK:-../data/Thach/after_cccd.png}"
DOC_TYPE="${DOC_TYPE:-CCCD}"

OUTPUT_MODE=(--fields-only)
PASSTHROUGH=()
for arg in "$@"; do
  case "$arg" in
    --full)
      OUTPUT_MODE=(--full)
      ;;
    *)
      PASSTHROUGH+=("$arg")
      ;;
  esac
done

exec "$PYTHON" -m ekyc_document.pipeline \
  "$FRONT" \
  --back "$BACK" \
  --type "$DOC_TYPE" \
  "${OUTPUT_MODE[@]}" \
  --no-face \
  --no-save \
  "${PASSTHROUGH[@]+"${PASSTHROUGH[@]}"}"
