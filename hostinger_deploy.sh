#!/usr/bin/env bash
# Deploy no Hostinger VPS.
# Uso: cd /opt/soluscrt && bash hostinger_deploy.sh
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$APP_DIR/../.env"

# Carrega .env se existir fora do diretório de código
if [ -f "$ENV_FILE" ]; then
    set -a; source "$ENV_FILE"; set +a
fi
# .env dentro do diretório também é aceito
if [ -f "$APP_DIR/.env" ]; then
    set -a; source "$APP_DIR/.env"; set +a
fi

echo "==> [1/5] git pull"
git -C "$APP_DIR" pull origin main

echo "==> [2/5] pip install"
"$PYTHON_BIN" -m pip install --quiet --upgrade pip
"$PYTHON_BIN" -m pip install --quiet --no-cache-dir -r "$APP_DIR/requirements.txt"

echo "==> [3/5] migrate"
# APP_DATABASE_URL= força uso do usuário owner (bypassa RLS) igual ao Render preDeployCommand
APP_DATABASE_URL= "$PYTHON_BIN" "$APP_DIR/manage.py" migrate --noinput

echo "==> [4/5] collectstatic"
"$PYTHON_BIN" "$APP_DIR/manage.py" collectstatic --noinput --clear

echo "==> [5/5] restart service"
systemctl restart soluscrt

echo ""
echo "Deploy concluído. Status:"
systemctl status soluscrt --no-pager -l
