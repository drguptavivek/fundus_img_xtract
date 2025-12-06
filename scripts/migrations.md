# Database Migration Scripts

## Overview

This directory contains scripts for database management and migration. The Fundus Image Manager project has transitioned from custom migration scripts to using **Alembic** for database schema management.

## Current Migration System

### Alembic (Primary System)

The project now uses **Alembic** as the primary database migration system. All new database schema changes should be made using Alembic.

**Key Documentation**: [Alembic Database Migrations](../docs/alembic-migrations.md)

#### Quick Start with Alembic

```bash
# Create a new migration
uv run alembic revision --autogenerate -m "Description of changes"

# Apply migrations
uv run alembic upgrade head

# Check current status
uv run alembic current
```

#### Alembic Configuration Files

- [`alembic.ini`](../alembic.ini) - Main configuration
- [`migrations/env.py`](../migrations/env.py) - Environment setup
- [`migrations/versions/`](../migrations/versions/) - Migration files

## Legacy Migration Scripts

The following scripts are maintained for backward compatibility and special operations:

### Database Setup Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| [`setup_db.py`](setup_db.py) | Initialize database with basic schema | `python -m scripts.setup_db` |
| [`clear_db.py`](clear_db.py) | Clear all data from database | `python -m scripts.clear_db` |
| [`backup_db.py`](backup_db.py) | Create database backup | `python -m scripts.backup_db` |
| [`restore_db.py`](restore_db.py) | Restore database from backup | `python -m scripts.restore_db` |

### Data Management Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| [`initial_setup.py`](initial_setup.py) | Populate initial master data | `python -m scripts.initial_setup` |
| [`setup_core_entities.py`](setup_core_entities.py) | Setup core entities (diseases, hospitals) | `python -m scripts.setup_core_entities` |

## Migration Best Practices

### 1. Use Alembic for Schema Changes

All database schema changes should use Alembic:

```bash
# 1. Modify models.py
# 2. Generate migration
uv run alembic revision --autogenerate -m "Add new field to users table"

# 3. Review and edit the migration if needed
# 4. Apply migration
uv run alembic upgrade head
```

### 2. Use Scripts for Data Operations

For data population or bulk operations:

```bash
# Use existing scripts or create new ones in this directory
python -m scripts.your_data_script
```

### 3. Testing Migrations

Always test migrations before production:

1. Test on development database
2. Verify both upgrade and downgrade paths
3. Test with realistic data volumes

## Migration Workflow

### New Project Setup

```bash
# 1. Set up database (if using PostgreSQL)
createdb fundus_image_manager

# 2. Run Alembic migrations
uv run alembic upgrade head

# 3. Populate initial data
python -m scripts.initial_setup
python -m scripts.setup_core_entities

# 4. Create admin user
python -m scripts.create_user
python -m scripts.assign_roles admin --roles admin
```

### Existing Project Upgrade

```bash
# 1. Backup current database
python -m scripts.backup_db

# 2. Apply any pending Alembic migrations
uv run alembic upgrade head

# 3. Run any data migration scripts if needed
```

## Troubleshooting

### Migration Conflicts

If you encounter migration conflicts:

1. Identify the current revision: `uv run alembic current`
2. Check migration history: `uv run alembic history`
3. Resolve conflicts by manually editing migration files
4. Use `alembic stamp` if needed to mark database state

### Database State Issues

If database state doesn't match migration history:

```bash
# Mark database as current (use with caution)
uv run alembic stamp head

# Or mark at specific revision
uv run alembic stamp <revision_id>
```

## Creating New Migration Scripts

When creating custom data migration scripts:

1. Follow the existing naming convention
2. Include proper error handling
3. Add logging for debugging
4. Test with small datasets first
5. Document the script's purpose and usage

Example script structure:

```python
#!/usr/bin/env python3
"""
Description of what this script does
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.utils import with_session
from models import YourModel

@with_session()
def migrate_data(db):
    """Main migration function"""
    try:
        # Your migration logic here
        db.commit()
        print("Migration completed successfully")
    except Exception as e:
        db.rollback()
        print(f"Migration failed: {e}")
        raise

if __name__ == "__main__":
    migrate_data()
```

## References

- [Alembic Documentation](../docs/alembic-migrations.md)
- [Database Models](../docs/00-Core/models.md)
- [Development Conventions](../docs/10-DEVELOP/CONVENTIONS.md)