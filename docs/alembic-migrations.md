# Alembic Database Migrations

## Overview

Alembic is a database migration tool for SQLAlchemy that provides a structured approach to managing database schema changes. The Fundus Image Manager project has integrated Alembic to replace the custom migration system, providing a more robust and standardized way to handle database schema evolution.

## Why Alembic Was Added

1. **Standardization**: Alembic is the de facto standard for SQLAlchemy migrations
2. **Version Control**: Tracks all schema changes with unique revision IDs
3. **Rollback Support**: Easy to upgrade and downgrade database schemas
4. **Autogeneration**: Can automatically generate migration scripts from model changes
5. **Team Collaboration**: Provides a consistent workflow for multiple developers

## Configuration

### Key Files

- [`alembic.ini`](../alembic.ini) - Main configuration file
- [`migrations/env.py`](../migrations/env.py) - Environment configuration for migrations
- [`migrations/script.py.mako`](../migrations/script.py.mako) - Template for new migration files
- [`migrations/versions/`](../migrations/versions/) - Directory containing all migration files

### Database Configuration

Alembic is configured to use the same database connection as the application:
- Reads `DATABASE_URL` from environment variables
- Falls back to SQLite for development: `sqlite:///image_manager.db`
- Supports both PostgreSQL and SQLite databases

## Common Commands

### Basic Migration Workflow

```bash
# Create a new migration (autogenerate)
uv run alembic revision --autogenerate -m "Description of changes"

# Apply migrations to the database
uv run alembic upgrade head

# Check current migration status
uv run alembic current

# View migration history
uv run alembic history

# Rollback to a specific revision
uv run alembic downgrade <revision_id>

# Rollback one migration
uv run alembic downgrade -1
```

### Development Commands

```bash
# Show SQL that would be executed (dry run)
uv run alembic upgrade head --sql

# Create a migration without autogenerate (manual)
uv run alembic revision -m "Manual migration description"

# Edit the most recent migration
uv run alembic edit head
```

## Migration Workflow

### 1. Making Model Changes

When you need to modify the database schema:

1. Update your models in [`models.py`](../models.py)
2. Generate a migration:
   ```bash
   uv run alembic revision --autogenerate -m "Describe your changes"
   ```
3. Review the generated migration file in `migrations/versions/`
4. Apply the migration:
   ```bash
   uv run alembic upgrade head
   ```

### 2. Manual Migrations

For complex changes that autogenerate can't handle:

1. Create an empty migration:
   ```bash
   uv run alembic revision -m "Manual migration description"
   ```
2. Edit the migration file to add custom `upgrade()` and `downgrade()` functions
3. Apply the migration as usual

### 3. Testing Migrations

Before applying migrations to production:

1. Test on a development database
2. Verify both upgrade and downgrade work:
   ```bash
   uv run alembic upgrade head
   uv run alembic downgrade -1
   uv run alembic upgrade head
   ```

## Best Practices

### Migration Naming

- Use descriptive, concise messages
- Include the purpose of the change
- Example: `"add_user_email_index"` or `"create_patient_encounters_table"`

### Migration Structure

Each migration should have:
- Clear `upgrade()` function that applies changes
- Complete `downgrade()` function that reverses changes
- Proper error handling for complex operations

### Data Migrations

For migrations that involve data transformation:

1. Use batch operations for large datasets
2. Consider performance impact
3. Add appropriate indexes before data operations
4. Clean up temporary indexes after completion

### Production Deployment

1. Always test migrations on a staging environment first
2. Create a database backup before applying migrations
3. Apply migrations during maintenance windows if they might cause downtime
4. Monitor the application after migration deployment

## Troubleshooting

### Common Issues

1. **Autogenerate doesn't detect changes**
   - Ensure your models are properly imported
   - Check that SQLAlchemy metadata is correctly configured

2. **Migration conflicts**
   - When multiple developers create migrations with the same base revision
   - Resolve by merging migration branches or rebase migrations

3. **Database state mismatch**
   - Use `alembic stamp` to mark the current database state
   - Example: `uv run alembic stamp head` to mark as up-to-date

### Recovery Commands

```bash
# Mark database as current without running migrations
uv run alembic stamp head

# Mark database as at a specific revision
uv run alembic stamp <revision_id>

# Get the current revision ID
uv run alembic current --verbose
```

## Integration with Application

### Database Initialization

For new installations, the complete workflow is:

1. Set up the database (create database/user if using PostgreSQL)
2. Run all migrations:
   ```bash
   uv run alembic upgrade head
   ```
3. Create initial data using scripts in [`scripts/`](../scripts/)

### Application Startup

The application automatically checks for pending migrations on startup and will log warnings if the database is not up-to-date.

## Migration History

The project's migration history includes:

- **5a49784f68f1**: Initial migration with complete schema
  - Creates all tables, indexes, and constraints
  - Establishes the base database structure

Future migrations will build upon this foundation.

## References

- [Official Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Alembic Tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [SQLAlchemy Migration Patterns](https://docs.sqlalchemy.org/en/latest/orm/migration_patterns.html)