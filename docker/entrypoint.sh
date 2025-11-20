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

echo "✅ Database is ready!"

# Check if virtual environment exists and is valid
if [ -d "/app/.venv" ] && [ -f "/app/.venv/bin/python" ]; then
    echo "✅ Virtual environment already exists - skipping recreation"
else
    echo "🔄 Virtual environment missing or invalid - creating..."
    uv sync
fi

# Run initial migration first
echo "Running initial database migration..."
uv run alembic upgrade 5a49784f68f1

# Wait 5 seconds for transaction to commit
echo "Waiting 5 seconds for migration to settle..."
sleep 5

# Run all remaining migrations
echo "Running remaining database migrations..."
uv run alembic upgrade head
echo "✅ Database migrations completed successfully!"

# Start cron daemon for log rotation
echo "Starting cron daemon for log rotation..."
service cron start
echo "✅ Cron daemon started"

exec "$@"
