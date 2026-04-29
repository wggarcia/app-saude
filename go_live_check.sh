#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"

pass_count=0
fail_count=0
warn_count=0

pass() {
  echo "[PASS] $1"
  pass_count=$((pass_count + 1))
}

fail() {
  echo "[FAIL] $1"
  fail_count=$((fail_count + 1))
}

warn() {
  echo "[WARN] $1"
  warn_count=$((warn_count + 1))
}

run_check() {
  local label="$1"
  shift
  if "$@" >/tmp/soluscrt_check.out 2>/tmp/soluscrt_check.err; then
    pass "$label"
  else
    fail "$label"
    sed -n '1,80p' /tmp/soluscrt_check.err
    sed -n '1,80p' /tmp/soluscrt_check.out
  fi
}

echo "=== SolusCRT • Go-Live Check ==="

aif_git_dirty=0
if git rev-parse --git-dir >/dev/null 2>&1; then
  if [ -n "$(git status --porcelain)" ]; then
    warn "Repositório com alterações locais não commitadas"
    aif_git_dirty=1
  else
    pass "Repositório limpo"
  fi
else
  warn "Sem repositório git detectado"
fi

run_check "Django check" "$PYTHON_BIN" manage.py check
run_check "Migrações consistentes" "$PYTHON_BIN" manage.py makemigrations --check --dry-run
run_check "Testes automatizados" "$PYTHON_BIN" manage.py test

# Deploy-safety check com ambiente simulado seguro.
run_check "Check deploy (config de produção)" env \
  DJANGO_ENV=production \
  DJANGO_DEBUG=false \
  DJANGO_SECRET_KEY='S0lusCRT_Prod_Secret_Key_2026_Change_Me_At_Deploy_!@#12345' \
  JWT_SECRET_KEY='JWT_S0lusCRT_Prod_Secret_Key_2026_Change_Me_At_Deploy_!@#67890' \
  DJANGO_ALLOWED_HOSTS='app-saude-p9n8.onrender.com' \
  CSRF_TRUSTED_ORIGINS='https://app-saude-p9n8.onrender.com' \
  SECURE_SSL_REDIRECT=true \
  DATABASE_URL='sqlite:///tmp/prod.sqlite3' \
  "$PYTHON_BIN" manage.py check --deploy

# Verifica presença dos segredos críticos no ambiente atual (sem exibir valores).
required_envs=(
  DJANGO_ENV
  DJANGO_DEBUG
  DJANGO_SECRET_KEY
  JWT_SECRET_KEY
  DATABASE_URL
  PUBLIC_BASE_URL
  MERCADO_PAGO_ACCESS_TOKEN
  MERCADO_PAGO_WEBHOOK_SECRET
)

missing_envs=()
for k in "${required_envs[@]}"; do
  if [ -z "${!k:-}" ]; then
    missing_envs+=("$k")
  fi
done

if [ ${#missing_envs[@]} -eq 0 ]; then
  pass "Variáveis críticas de produção presentes no ambiente"
else
  warn "Variáveis críticas ausentes no ambiente atual: ${missing_envs[*]}"
fi

if command -v flutter >/dev/null 2>&1 && [ -d "app_saude" ]; then
  run_check "Flutter analyze (app_saude)" bash -lc "cd app_saude && flutter analyze"
  run_check "Flutter test (app_saude)" bash -lc "cd app_saude && flutter test"
else
  warn "Flutter não disponível localmente (ou pasta app_saude ausente)"
fi

echo
echo "=== Resumo ==="
echo "PASS: $pass_count"
echo "WARN: $warn_count"
echo "FAIL: $fail_count"

if [ $fail_count -gt 0 ]; then
  echo "STATUS FINAL: REPROVADO"
  exit 1
fi

if [ $warn_count -gt 0 ]; then
  echo "STATUS FINAL: APROVADO COM RESSALVAS"
  exit 0
fi

echo "STATUS FINAL: APROVADO"
