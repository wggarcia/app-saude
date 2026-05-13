#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$ROOT_DIR/app_ocupacional"

if [[ ! -d "$APP_DIR" ]]; then
  echo "[ERRO] app_ocupacional nao encontrado em: $APP_DIR"
  echo "Execute este script dentro do repositorio correto (app-saude)."
  exit 1
fi

cd "$APP_DIR"
echo "[INFO] Diretorio: $(pwd)"

if ! command -v flutter >/dev/null 2>&1; then
  echo "[ERRO] Flutter nao encontrado no PATH."
  exit 1
fi

# Evita sobrescrever lib/main.dart com template Demo.
if [[ ! -d ios ]]; then
  echo "[INFO] Plataforma iOS ausente; criando somente ios para app_ocupacional..."
  flutter create . --platforms=ios
else
  echo "[INFO] Plataforma iOS ja existe; preservando codigo Flutter atual."
fi

flutter pub get

cd ios
if ! command -v pod >/dev/null 2>&1; then
  echo "[ERRO] CocoaPods (pod) nao encontrado. Instale com: sudo gem install cocoapods"
  exit 1
fi
pod install

open Runner.xcworkspace

echo "[OK] Xcode aberto em app_ocupacional/ios/Runner.xcworkspace"
