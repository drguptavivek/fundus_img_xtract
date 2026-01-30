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

# Check if web container is running
if ! $DC ps web | grep -q "Up"; then
    echo "❌ Web container is not running. Starting it..."
    $DC up -d web
    sleep 5
fi

# Export each dependency group to temporary files in the container
echo "📦 Generating requirements files..."
$DC exec web bash -c "
    set -e
    uv export --extra web --format requirements-txt --no-hashes > /tmp/requirements-web.txt
    uv export --extra ocr --format requirements-txt --no-hashes > /tmp/requirements-ocr.txt
    uv export --extra beat --format requirements-txt --no-hashes > /tmp/requirements-beat.txt
    uv export --extra general --format requirements-txt --no-hashes > /tmp/requirements-general.txt
    uv export --format requirements-txt --no-hashes > /tmp/requirements.txt
    echo '✅ Generated all requirement files in container'
"

# Copy files from container to host
echo ""
echo "📋 Copying files from container to host..."
$DC exec web cat /tmp/requirements-web.txt > requirements-web.txt
$DC exec web cat /tmp/requirements-ocr.txt > requirements-ocr.txt
$DC exec web cat /tmp/requirements-beat.txt > requirements-beat.txt
$DC exec web cat /tmp/requirements-general.txt > requirements-general.txt
$DC exec web cat /tmp/requirements.txt > requirements.txt

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
