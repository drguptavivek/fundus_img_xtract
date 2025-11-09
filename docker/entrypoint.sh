#!/usr/bin/env bash
set -euo pipefail

# Ensure bind-mounted directories exist with safe permissions
mkdir -p /app/logs /app/files
mkdir -p /var/run/fundus-img-xtract

# Default to secure cookie/session settings when behind TLS-terminating proxy
export SESSION_COOKIE_SECURE="${SESSION_COOKIE_SECURE:-true}"
export SESSION_COOKIE_HTTPONLY="${SESSION_COOKIE_HTTPONLY:-true}"
export SESSION_COOKIE_SAMESITE="${SESSION_COOKIE_SAMESITE:-Lax}"
export PREFERRED_URL_SCHEME="${PREFERRED_URL_SCHEME:-https}"

# Wait for database to be ready
echo "Waiting for database to be ready..."
until uv run python -c "
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from utils.env_loader import load_environment

try:
    load_environment()
    from models import _build_database_url
    DATABASE_URL = _build_database_url(Path('/app'))
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        conn.execute(text('SELECT 1'))
    print('Database is ready')
except Exception as e:
    print(f'Database not ready: {e}')
    sys.exit(1)
"; do
  echo "Database unavailable, waiting 3 seconds..."
  sleep 3
done

# Run migrations automatically
echo "Running database migrations..."
uv run alembic upgrade head

# Check if core data seeding is needed
echo "Checking if core data seeding is needed..."
SEED_NEEDED=$(uv run python -c "
from db_transaction_manager import get_db_session
from models import Hospital, Disease

def check_core_data():
    with get_db_session() as db:
        # Check if core hospitals exist
        core_hospitals_exist = db.query(Hospital).filter(Hospital.id.in_([1, 2])).count() == 2
        # Check if core diseases exist
        core_diseases_exist = db.query(Disease).filter(Disease.id.in_([1, 2, 3])).count() == 3
        
        if not core_hospitals_exist or not core_diseases_exist:
            print('Core data seeding needed')
            return 'true'
        else:
            print('Core data already exists')
            return 'false'

result = check_core_data()
print(result)
")

if [ "$SEED_NEEDED" = "true" ]; then
    echo "Running core data seeding migration..."
    echo "NOTE: This will only add missing core data and sample features."
    echo "      Your custom grading features will be preserved."
    uv run alembic upgrade 691d42ba3fff
else
    echo "Core data already exists - skipping seeding migration"
fi

echo "✅ Database setup completed successfully!"

# Start cron daemon for log rotation
echo "Starting cron daemon for log rotation..."
service cron start
echo "✅ Cron daemon started"

exec "$@"
