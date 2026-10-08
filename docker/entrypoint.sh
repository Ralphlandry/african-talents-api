#!/bin/sh
set -e

if [ "${1:-}" = "pytest" ]; then
  export DJANGO_SETTINGS_MODULE="${PYTEST_DJANGO_SETTINGS_MODULE:-config.settings.test}"
fi

python /app/docker/wait_for_db.py

# Développement uniquement : génère les fichiers de migration s'ils manquent (à committer ensuite).
if [ "${AUTO_MAKEMIGRATIONS:-0}" = "1" ]; then
  python manage.py makemigrations --noinput
fi
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  python manage.py migrate --noinput
fi
if [ "${RUN_COLLECTSTATIC:-0}" = "1" ]; then
  python manage.py collectstatic --noinput
fi

exec "$@"
