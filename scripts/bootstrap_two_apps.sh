#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

for APP in app_saude app_ocupacional; do
  APP_DIR="$ROOT_DIR/$APP"
  if [[ ! -d "$APP_DIR" ]]; then
    echo "[ERRO] App não encontrado: $APP_DIR"
    exit 1
  fi

  echo "[INFO] Preparando $APP ..."
  cd "$APP_DIR"

  flutter create . --platforms=ios,android,web
  flutter pub get

  if [[ -d ios ]] && command -v pod >/dev/null 2>&1; then
    (cd ios && pod install)
  fi
done

echo "[OK] Dois apps preparados: app_saude e app_ocupacional"
