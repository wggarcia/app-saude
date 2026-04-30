#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"

exec "$PYTHON_BIN" -m gunicorn backend.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers "${WEB_CONCURRENCY:-2}" --worker-class gthread --threads "${WEB_THREADS:-4}" --timeout 120
