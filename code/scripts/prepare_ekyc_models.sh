#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-config/.env.staging}"

cd "$ROOT_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Env file not found: $ENV_FILE" >&2
  exit 1
fi

echo "Preparing eKYC ONNX models with env: $ENV_FILE"

docker compose --env-file "$ENV_FILE" run --rm ai-modules \
  python -m scripts.download_models --models-dir /app/models

docker compose --env-file "$ENV_FILE" run --rm ai-modules \
  python -m scripts.check_models

docker compose --env-file "$ENV_FILE" up -d ai-modules ai-worker

echo "eKYC ONNX models are ready in the /app/models Docker volume."
