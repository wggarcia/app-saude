#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"

"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install --no-cache-dir -r requirements.txt
"$PYTHON_BIN" manage.py collectstatic --noinput

if [ "${SKIP_BUILD_MIGRATIONS:-false}" != "true" ]; then
  # Migrations e bootstrap devem rodar com DATABASE_URL (usuário owner),
  # nunca com APP_DATABASE_URL (usuário restrito/RLS).
  APP_DATABASE_URL= "$PYTHON_BIN" manage.py migrate --noinput
  APP_DATABASE_URL= "$PYTHON_BIN" manage.py bootstrap_acessos
fi
