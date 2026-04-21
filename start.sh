set -e

python manage.py bootstrap_acessos
gunicorn backend.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --timeout 120
