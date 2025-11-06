#!/usr/bin/env bash
set -euo pipefail

# Ensure bind-mounted directories exist with safe permissions
mkdir -p /app/logs /app/files

# Default to secure cookie/session settings when behind TLS-terminating proxy
export SESSION_COOKIE_SECURE="${SESSION_COOKIE_SECURE:-true}"
export SESSION_COOKIE_HTTPONLY="${SESSION_COOKIE_HTTPONLY:-true}"
export SESSION_COOKIE_SAMESITE="${SESSION_COOKIE_SAMESITE:-Lax}"
export PREFERRED_URL_SCHEME="${PREFERRED_URL_SCHEME:-https}"

exec "$@"
