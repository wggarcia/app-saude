#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"

"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install --no-cache-dir -r requirements.txt
"$PYTHON_BIN" manage.py collectstatic --noinput

if [ "${SKIP_BUILD_MIGRATIONS:-false}" != "true" ]; then
  # Migrations e bootstrap devem rodar com DATABASE_URL (usuário owner),
  # nunca com APP_DATABASE_URL (usuário restrito/RLS).

  # Reconcilia django_migrations com o schema real do banco: aplica as
  # pendentes uma a uma e marca como --fake qualquer uma cujo objeto já
  # exista (schema à frente dos registros de controle). Migrations
  # genuinamente novas e data migrations rodam normalmente.
  APP_DATABASE_URL= "$PYTHON_BIN" manage.py reconcile_migrations

  # Verificação final — deve ser no-op se a reconciliação cobriu tudo.
  APP_DATABASE_URL= "$PYTHON_BIN" manage.py migrate --noinput
  APP_DATABASE_URL= "$PYTHON_BIN" manage.py bootstrap_acessos
fi
