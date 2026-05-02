#!/usr/bin/env bash
#
# Export per-container requirements files from pyproject.toml dependency groups
# This script auto-generates all requirements-*.txt files using uv export
#
# Usage: ./scripts/export_requirements.sh

set -euo pipefail

DC="${DC:-docker compose}"

echo "🔄 Exporting per-container requirements files..."
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
    requirements-exporter sh -lc "
    set -e
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
echo "✅ Done! Now run:"
echo "   git add requirements*.txt"
echo "   git commit -m 'chore: regenerate requirements files'"
