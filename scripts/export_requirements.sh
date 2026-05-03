#!/usr/bin/env bash
#
# Export per-container requirements files from pyproject.toml dependency groups
# This script auto-generates all requirements-*.txt files using uv export
#
# Usage: ./scripts/export_requirements.sh

set -euo pipefail

DC="${DC:-docker compose}"
UV_LOCK_ARGS="${UV_LOCK_ARGS:-}"
SHOW_UV_TREE="${SHOW_UV_TREE:-1}"
UV_TREE_ARGS="${UV_TREE_ARGS:---outdated --universal --package redis --invert}"
LOCK_BACKUP_DIR="${LOCK_BACKUP_DIR:-backups/requirements-locks}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCK_BACKUP_PATH="${LOCK_BACKUP_DIR}/uv.lock.${TIMESTAMP}.bak"

echo "🔄 Exporting per-container requirements files..."
echo ""

# Keep a rollback copy before uv gets a chance to rewrite dependency resolution.
mkdir -p "$LOCK_BACKUP_DIR"
cp uv.lock "$LOCK_BACKUP_PATH"
echo "🧾 Backed up current uv.lock to $LOCK_BACKUP_PATH"
echo ""

# Export each dependency group using the lightweight exporter container
echo "📦 Generating requirements files..."
$DC run --rm -u "$(id -u):$(id -g)" \
    -e HOME=/tmp \
    -e XDG_DATA_HOME=/tmp/.local/share \
    -e XDG_CACHE_HOME=/tmp/.cache \
    -e UV_CACHE_DIR=/tmp/.uv-cache-local \
    -e UV_PYTHON=/usr/local/bin/python3.13 \
    -e UV_NO_MANAGED_PYTHON=1 \
    -e UV_NO_PROJECT_ENVIRONMENT=1 \
    -e UV_LOCK_ARGS="$UV_LOCK_ARGS" \
    requirements-exporter sh -lc "
    set -e
    uv lock \$UV_LOCK_ARGS
    uv export --extra web --format requirements-txt --no-hashes > requirements-web.txt
    uv export --extra ocr --format requirements-txt --no-hashes > requirements-ocr.txt
    uv export --extra beat --format requirements-txt --no-hashes > requirements-beat.txt
    uv export --extra general --format requirements-txt --no-hashes > requirements-general.txt
    uv export --format requirements-txt --no-hashes > requirements.txt
    echo '✅ Generated all requirement files in container'
"

# Show summary
echo ""
echo "✅ Successfully exported requirements files:"
echo ""
wc -l requirements*.txt
echo ""
echo "📊 Package counts by container:"
echo "  Core only:     $(grep -v '^#' requirements.txt | grep -v '^$' | wc -l) packages"
echo "  Web:           $(grep -v '^#' requirements-web.txt | grep -v '^$' | wc -l) packages"
echo "  OCR:           $(grep -v '^#' requirements-ocr.txt | grep -v '^$' | wc -l) packages"
echo "  Beat:          $(grep -v '^#' requirements-beat.txt | grep -v '^$' | wc -l) packages"
echo "  General:       $(grep -v '^#' requirements-general.txt | grep -v '^$' | wc -l) packages"
echo ""

if [ "$SHOW_UV_TREE" != "0" ]; then
    echo "📊 uv tree summary:"
    $DC run --rm \
        -e HOME=/tmp \
        -e XDG_DATA_HOME=/tmp/.local/share \
        -e XDG_CACHE_HOME=/tmp/.cache \
        -e UV_CACHE_DIR=/tmp/.uv-cache-local \
        -e UV_PYTHON=/usr/local/bin/python3.13 \
        -e UV_NO_MANAGED_PYTHON=1 \
        -e UV_NO_PROJECT_ENVIRONMENT=1 \
        requirements-exporter uv tree $UV_TREE_ARGS
    echo ""
fi

echo "✅ Done! Now run:"
echo "   git add pyproject.toml uv.lock requirements*.txt"
echo "   git commit -m 'chore: refresh Python lock and requirements'"
