#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-8080}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$ROOT_DIR/app_ocupacional"

if [[ ! -d "$APP_DIR" ]]; then
  echo "[ERRO] app_ocupacional nao encontrado em: $APP_DIR"
  exit 1
fi

cd "$APP_DIR"
if ! command -v flutter >/dev/null 2>&1; then
  echo "[ERRO] Flutter nao encontrado no PATH."
  exit 1
fi

flutter pub get
flutter run -d chrome --web-port "$PORT"
