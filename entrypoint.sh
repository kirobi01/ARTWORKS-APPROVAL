#!/bin/sh
set -e

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.production}"

# Only the web container should migrate / collectstatic / setup groups.
# Worker and beat skip this to avoid parallel-migration races.
RUN_DB_SETUP=0
case " $* " in
  *" gunicorn "*|*" manage.py "*) RUN_DB_SETUP=1 ;;
esac

if [ "$RUN_DB_SETUP" = "1" ] || [ "${RUN_DB_SETUP_FORCE:-0}" = "1" ]; then
  echo "Waiting for database..."
  python - <<'PY'
import time
import django
django.setup()
from django.db import connection
from django.db.utils import OperationalError

for i in range(30):
    try:
        connection.ensure_connection()
        print("Database is ready.")
        break
    except OperationalError as exc:
        print(f"Database not ready ({i+1}/30): {exc}")
        time.sleep(2)
else:
    raise SystemExit("Database unavailable after retries.")
PY

  echo "Running migrations..."
  python manage.py migrate --noinput

  echo "Collecting static files..."
  python manage.py collectstatic --noinput

  echo "Ensuring artwork groups..."
  python manage.py setup_artwork_groups || true
else
  echo "Waiting for database (no migrate)..."
  python - <<'PY'
import time
import django
django.setup()
from django.db import connection
from django.db.utils import OperationalError

for i in range(60):
    try:
        connection.ensure_connection()
        print("Database is ready.")
        break
    except OperationalError as exc:
        print(f"Database not ready ({i+1}/60): {exc}")
        time.sleep(2)
else:
    raise SystemExit("Database unavailable after retries.")
PY
fi

echo "Starting: $*"
exec "$@"
