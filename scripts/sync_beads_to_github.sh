#!/bin/bash
# Sync beads status with GitHub issues (IDEMPOTENT)
# Run this periodically (cron) to keep GitHub issues in sync with beads
# Maintains a local cache of open issues to avoid GitHub rate limits

set -e

# Config
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE_FILE="$SCRIPT_DIR/../.beads/open_issues_cache.txt"
CACHE_DIR="$(dirname "$CACHE_FILE")"
LOG_FILE="$CACHE_DIR/bead_sync.log"

# Ensure directories exist
mkdir -p "$CACHE_DIR" "$(dirname "$LOG_FILE")"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$LOG_FILE"; }

# Full mapping of all bead IDs to issue numbers
declare -A BEAD_TO_ISSUE=(
    ["9rb"]="22"
    ["ugh"]="23"
    ["5pi"]="24"
    ["s8t"]="25"
    ["snk"]="26"
    ["toj"]="4"
    ["awm"]="5"
    ["duv"]="6"
    ["4s9"]="10"
    ["b3g"]="7"
    ["8r1"]="8"
    ["b05"]="9"
    ["4uu"]="11"
    ["49p"]="12"
    ["d1h"]="13"
    ["62a"]="14"
    ["crn"]="15"
    ["y7z"]="16"
    ["ubr"]="17"
    ["jms"]="18"
    ["mzt"]="19"
    ["j9p"]="20"
    ["d18"]="21"
    ["8g7"]="27"
)

# Initialize cache file if it doesn't exist
init_cache() {
    if [ ! -f "$CACHE_FILE" ]; then
        log "Initializing cache with all open beads..."
        > "$CACHE_FILE"
        bd list --status=open 2>/dev/null | grep -oP 'fundus_img_xtract-\K[a-z0-9]+' | while read -r bead_id; do
            echo "$bead_id" >> "$CACHE_FILE"
        done
        log "Cache initialized with $(wc -l < "$CACHE_FILE") open beads"
    fi
}

# Remove bead from cache
remove_from_cache() {
    sed -i "/^$1$/d" "$CACHE_FILE" 2>/dev/null || true
}

# Add bead to cache
add_to_cache() {
    if ! grep -qx "$1" "$CACHE_FILE" 2>/dev/null; then
        echo "$1" >> "$CACHE_FILE"
    fi
}

# Get list of open beads from cache
get_cached_open_beads() {
    grep -v '^[[:space:]]*$' "$CACHE_FILE" 2>/dev/null || echo ""
}

log "Syncing beads with GitHub issues..."

# Initialize cache if needed
init_cache

# Counters
CHANGES=0
CLOSED_COUNT=0

# Process only cached open issues (optimization)
log "Checking $(wc -l < "$CACHE_FILE") cached open issues..."

while read -r bead_id; do
    [ -z "$bead_id" ] && continue

    issue_num="${BEAD_TO_ISSUE[$bead_id]}"
    [ -z "$issue_num" ] && continue

    # Get current bead status
    bead_info=$(bd list 2>/dev/null | grep "fundus_img_xtract-$bead_id" || echo "")
    [ -z "$bead_info" ] && continue

    # Determine bead status
    if echo "$bead_info" | grep -q "\[closed\]"; then
        bead_status="closed"
    else
        bead_status="open"
    fi

    # Get issue state from GitHub (only for cached open beads)
    issue_state=$(gh issue view "$issue_num" --json state --jq '.state' 2>/dev/null || echo "UNKNOWN")

    # Sync state (idempotent)
    if [ "$bead_status" = "closed" ] && [ "$issue_state" = "OPEN" ]; then
        log "Closing #$issue_num (bead: $bead_id)"
        gh issue close "$issue_num" --comment "Completed (bead: fundus_img_xtract-$bead_id)" >/dev/null 2>&1
        remove_from_cache "$bead_id"
        ((CHANGES++))
        ((CLOSED_COUNT++))
    elif [ "$bead_status" = "open" ] && [ "$issue_state" = "CLOSED" ]; then
        log "Reopening #$issue_num (bead: $bead_id)"
        gh issue reopen "$issue_num" --comment "Reopened (bead: fundus_img_xtract-$bead_id)" >/dev/null 2>&1
        ((CHANGES++))
    fi
done < "$CACHE_FILE"

# Check for newly opened beads (not in cache) - only do this occasionally
# Use a daily marker file to limit this check to once per day
DAILY_CHECK_MARKER="$CACHE_DIR/.last_full_check"
TODAY=$(date +%Y-%m-%d)

if [ ! -f "$DAILY_CHECK_MARKER" ] || [ "$(cat "$DAILY_CHECK_MARKER" 2>/dev/null)" != "$TODAY" ]; then
    log "Running daily full check for newly opened beads..."

    OPEN_BEADS=$(bd list --status=open 2>/dev/null | grep -oP 'fundus_img_xtract-\K[a-z0-9]+' || echo "")

    for bead_id in $OPEN_BEADS; do
        if ! grep -qx "$bead_id" "$CACHE_FILE" 2>/dev/null; then
            issue_num="${BEAD_TO_ISSUE[$bead_id]}"
            [ -z "$issue_num" ] && continue

            # Check if GitHub issue is closed
            issue_state=$(gh issue view "$issue_num" --json state --jq '.state' 2>/dev/null || echo "UNKNOWN")

            if [ "$issue_state" = "CLOSED" ]; then
                log "Reopening newly opened bead #$issue_num (bead: $bead_id)"
                gh issue reopen "$issue_num" --comment "Reopened (bead: fundus_img_xtract-$bead_id)" >/dev/null 2>&1
                ((CHANGES++))
            fi

            # Add to cache
            add_to_cache "$bead_id"
        fi
    done

    # Update daily check marker
    echo "$TODAY" > "$DAILY_CHECK_MARKER"
fi

# Summary
[ $CHANGES -eq 0 ] && log "No changes - in sync ($(wc -l < "$CACHE_FILE") open)" || log "Synced $CHANGES issue(s) ($CLOSED_COUNT closed, $(wc -l < "$CACHE_FILE") remain open)"
