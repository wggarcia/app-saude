#!/usr/bin/env bash
# Build leve para cron jobs — só instala dependências Python.
# collectstatic e migrations são desnecessários para comandos de management.
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install --no-cache-dir --force-reinstall -r requirements.txt
