#!/usr/bin/env python3
"""
Migration script to add viewer settings and presets tables to the database.
Run this script once to update the database schema.
"""

import sys
import os
from pathlib import Path

# Add the project root to the path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
from models import Base, ViewerSettings, ViewerPresets, engine, Session
from sqlalchemy import inspect, text

load_dotenv()

def create_migration_table(table_name, sql):
    """Create a migration record for the table creation."""
    migration_sql = f"""
    INSERT INTO schema_migrations (table_name, migration_sql, applied_at)
    VALUES ('{table_name}', '{sql}', datetime('now'))
    ON CONFLICT(table_name) DO UPDATE SET
        migration_sql = '{sql}',
        applied_at = datetime('now')
    WHERE table_name = '{table_name}';
    """
    return migration_sql

def ensure_schema_migrations_table():
    """Ensure the schema_migrations table exists."""
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        table_name TEXT NOT NULL UNIQUE,
        migration_sql TEXT NOT NULL,
        applied_at DATETIME NOT NULL
    )
    """
    with engine.connect() as conn:
        conn.execute(text(create_table_sql))
        conn.commit()

def main():
    """Main migration function."""
    print("Starting viewer settings migration...")
    
    try:
        # Ensure schema_migrations table exists
        ensure_schema_migrations_table()
        
        # Check if viewer_settings table already exists
        inspector = inspect(engine)
        if 'viewer_settings' not in inspector.get_table_names():
            print("Creating viewer_settings table...")
            ViewerSettings.__table__.create(engine)
            migration_sql = create_migration_table(
                'viewer_settings',
                str(ViewerSettings.__table__.compile(engine).compile(compile_kwargs={"literal_binds": True}))
            )
            with engine.connect() as conn:
                conn.execute(text(migration_sql))
                conn.commit()
            print("✓ viewer_settings table created successfully")
        else:
            print("✓ viewer_settings table already exists")
        
        # Check if viewer_presets table already exists
        if 'viewer_presets' not in inspector.get_table_names():
            print("Creating viewer_presets table...")
            ViewerPresets.__table__.create(engine)
            migration_sql = create_migration_table(
                'viewer_presets',
                str(ViewerPresets.__table__.compile(engine).compile(compile_kwargs={"literal_binds": True}))
            )
            with engine.connect() as conn:
                conn.execute(text(migration_sql))
                conn.commit()
            print("✓ viewer_presets table created successfully")
        else:
            print("✓ viewer_presets table already exists")
        
        print("Migration completed successfully!")
        
    except Exception as e:
        print(f"Error during migration: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()