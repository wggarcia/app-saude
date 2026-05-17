#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

[[ -d "$ROOT_DIR/app_saude" ]] || { echo "[ERRO] app_saude ausente"; exit 1; }
[[ -d "$ROOT_DIR/app_ocupacional" ]] || { echo "[ERRO] app_ocupacional ausente"; exit 1; }
[[ -f "$ROOT_DIR/app_saude/lib/main.dart" ]] || { echo "[ERRO] main.dart ausente em app_saude"; exit 1; }
[[ -f "$ROOT_DIR/app_ocupacional/lib/main.dart" ]] || { echo "[ERRO] main.dart ausente em app_ocupacional"; exit 1; }
[[ -f "$ROOT_DIR/manage.py" ]] || { echo "[ERRO] backend Django deve ficar na raiz do repositório"; exit 1; }

for DIR in android ios linux macos windows web lib test backend/app-saude app_saude/app_ocupacional; do
  if [[ -e "$ROOT_DIR/$DIR" ]]; then
    echo "[ERRO] Ambiente duplicado ou fora do lugar: $DIR"
    exit 1
  fi
done

[[ -d "$ROOT_DIR/app_saude/android" ]] || { echo "[ERRO] app_saude precisa conter Android"; exit 1; }
[[ -d "$ROOT_DIR/app_saude/ios" ]] || { echo "[ERRO] app_saude precisa conter iOS"; exit 1; }
[[ -d "$ROOT_DIR/app_saude/web" ]] || { echo "[ERRO] app_saude precisa conter Web"; exit 1; }
[[ -d "$ROOT_DIR/app_ocupacional/android" ]] || { echo "[ERRO] app_ocupacional precisa conter Android"; exit 1; }
[[ -d "$ROOT_DIR/app_ocupacional/ios" ]] || { echo "[ERRO] app_ocupacional precisa conter iOS"; exit 1; }
[[ -d "$ROOT_DIR/app_ocupacional/web" ]] || { echo "[ERRO] app_ocupacional precisa conter Web"; exit 1; }

echo "[OK] Estrutura validada."
