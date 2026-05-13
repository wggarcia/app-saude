#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if ! command -v flutter >/dev/null 2>&1; then
  echo "[ERRO] Flutter não encontrado no PATH."
  exit 1
fi

for APP in app_saude app_ocupacional; do
  APP_DIR="$ROOT_DIR/$APP"
  if [[ ! -d "$APP_DIR" ]]; then
    echo "[ERRO] App não encontrado: $APP_DIR"
    exit 1
  fi

  echo "[INFO] Preparando $APP ..."
  cd "$APP_DIR"

  # Só gera plataformas que estiverem ausentes para não tocar no app existente.
  MISSING_PLATFORMS=()
  [[ -d ios ]] || MISSING_PLATFORMS+=(ios)
  [[ -d android ]] || MISSING_PLATFORMS+=(android)
  [[ -d web ]] || MISSING_PLATFORMS+=(web)

  if [[ ${#MISSING_PLATFORMS[@]} -gt 0 ]]; then
    PLATFORMS_CSV="$(IFS=, ; echo "${MISSING_PLATFORMS[*]}")"
    echo "[INFO] Gerando plataformas ausentes em $APP: $PLATFORMS_CSV"
    flutter create . --platforms="$PLATFORMS_CSV"
  else
    echo "[INFO] Todas as plataformas principais já existem em $APP; sem flutter create."
  fi

  flutter pub get

  if [[ -d ios ]] && command -v pod >/dev/null 2>&1; then
    (cd ios && pod install)
  fi

done

echo "[OK] Dois apps preparados: app_saude e app_ocupacional"
