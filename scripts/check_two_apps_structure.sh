#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

fail() { echo "[ERRO] $1"; exit 1; }

[[ -d "$ROOT_DIR/app_saude" ]] || fail "app_saude ausente"
[[ -d "$ROOT_DIR/app_ocupacional" ]] || fail "app_ocupacional ausente"
[[ ! -d "$ROOT_DIR/app_funcionario" ]] || fail "app_funcionario não deve existir (duplicação)"

[[ -f "$ROOT_DIR/app_saude/lib/main.dart" ]] || fail "main.dart ausente em app_saude"
[[ -f "$ROOT_DIR/app_ocupacional/lib/main.dart" ]] || fail "main.dart ausente em app_ocupacional"

echo "[OK] Estrutura validada: 2 apps separados e sem duplicação." 
