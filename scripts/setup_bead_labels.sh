#!/bin/bash
# One-time setup: Create all bead-specific labels in GitHub
# Run this once to initialize all labels

set -e

log() { echo -e "\033[0;32m[$(date '+%Y-%m-%d %H:%M:%S')]\033[0m $1"; }

log "Creating bead-specific labels..."

# All bead IDs
BEAD_IDS=(
    "9rb" "ugh" "5pi" "s8t" "snk" "toj" "awm" "duv" "4s9"
    "b3g" "8r1" "b05" "4uu" "49p" "d1h" "62a" "crn" "y7z"
    "ubr" "jms" "mzt" "j9p" "d18" "8g7"
)

# Priority labels
log "Creating priority labels..."
gh label create "p0" --color "#b60205" --description "Priority P0 - Critical" 2>/dev/null || log "p0 already exists"
gh label create "p1" --color "#ff9f1c" --description "Priority P1 - High" 2>/dev/null || log "p1 already exists"
gh label create "p2" --color "#ffcd56" --description "Priority P2 - Medium" 2>/dev/null || log "p2 already exists"
gh label create "p3" --color "#C5DEF5" --description "Priority P3 - Low" 2>/dev/null || log "p3 already exists"
gh label create "p4" --color "#1D76DB" --description "Priority P4 - Backlog" 2>/dev/null || log "p4 already exists"

# Type labels
log "Creating type labels..."
gh label create "type-feature" --color "#a2eeef" --description "Feature request" 2>/dev/null || log "type-feature already exists"
gh label create "type-bug" --color "#d73a4a" --description "Bug report" 2>/dev/null || log "type-bug already exists"
gh label create "type-task" --color "#5319e7" --description "Task item" 2>/dev/null || log "type-task already exists"

# Bead ID labels
log "Creating bead ID labels..."
for bead_id in "${BEAD_IDS[@]}"; do
    gh label create "bead-$bead_id" --color "#1a63c9" --description "Bead ID: $bead_id" 2>/dev/null || log "bead-$bead_id already exists"
done

log "Label setup complete!"
