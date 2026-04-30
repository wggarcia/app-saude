#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"

"$PYTHON_BIN" -m pip install -r requirements.txt
"$PYTHON_BIN" manage.py collectstatic --noinput

if [ "${SKIP_BUILD_MIGRATIONS:-false}" != "true" ]; then
  "$PYTHON_BIN" manage.py migrate --noinput
  "$PYTHON_BIN" manage.py bootstrap_acessos
fi
