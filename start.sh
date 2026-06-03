#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"

# ── Provisionamento das contas de demonstração (App Store / Play Store) ──────
# O preDeployCommand do render.yaml é uma configuração do Blueprint e só passa
# a valer no serviço após um "sync" manual no painel do Render. Para garantir
# que as contas demo (Guideline 2.1 da Apple) existam a CADA deploy — sem
# depender desse sync — provisionamos aqui, a partir do código já implantado.
# É idempotente (--upsert: cria o que faltar, reseta senhas conhecidas) e
# nunca bloqueia a subida do servidor. Roda com o usuário owner do banco
# (APP_DATABASE_URL vazio) para não esbarrar em RLS.
if [ "${SKIP_DEMO_PROVISION:-false}" != "true" ]; then
  APP_DATABASE_URL= "$PYTHON_BIN" manage.py demo_setup --upsert || \
    echo "⚠ demo_setup --upsert falhou (seguindo com a subida do servidor)"
fi

exec "$PYTHON_BIN" -m gunicorn backend.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers "${WEB_CONCURRENCY:-2}" --worker-class gthread --threads "${WEB_THREADS:-4}" --timeout 120
