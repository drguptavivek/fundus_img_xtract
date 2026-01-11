#!/bin/bash
# Helper: Generate bead->issue mapping from GitHub
# Usage: ./scripts/generate_bead_mapping.sh

echo "# Bead to Issue Mapping - add to sync_beads_to_github.sh"
echo ""

docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec -T web bash -c '
for issue in $(gh issue list --state all --limit 200 --json number --jq ".[].number"); do
    body=$(gh issue view "$issue" --json body --jq ".body" 2>/dev/null)
    if echo "$body" | grep -q "fundus_img_xtract-"; then
        bead=$(echo "$body" | grep -oP "fundus_img_xtract-\K[a-z0-9]+" | head -1)
        echo "[\"$bead\"]=\"$issue\""
    fi
done
' 2>/dev/null | grep '^\['
