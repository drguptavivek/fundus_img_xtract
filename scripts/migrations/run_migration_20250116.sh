#!/bin/bash

# Script to run the migration for adding 'review' role_slot
# Usage: ./run_migration_20250116.sh

echo "Running migration to add 'review' role_slot to grades table..."

# Get the database path from environment or use default
DB_PATH="${DATABASE_URL#sqlite:///}"
if [ -z "$DB_PATH" ]; then
    DB_PATH="image_manager.db"
fi

echo "Using database: $DB_PATH"

# Run the migration
sqlite3 "$DB_PATH" < "$(dirname "$0")/20250116_add_review_role_slot.sql"

if [ $? -eq 0 ]; then
    echo "Migration completed successfully!"
else
    echo "Migration failed!"
    exit 1
fi