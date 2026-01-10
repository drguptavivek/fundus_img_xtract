"""Database utilities for testing"""

from sqlalchemy import text
from typing import List, Optional


def truncate_tables(db_session, table_names: Optional[List[str]] = None):
    """
    Truncate specified tables or all tables.
    Useful for cleaning up between tests.
    
    Args:
        db_session: Database session
        table_names: List of table names to truncate. If None, truncates all tables.
    """
    if table_names is None:
        # Get all table names from public schema
        result = db_session.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        ))
        table_names = [row[0] for row in result]
    
    # Disable foreign key checks temporarily (PostgreSQL way)
    db_session.execute(text("SET session_replication_role = 'replica'"))
    
    try:
        for table in table_names:
            db_session.execute(text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE'))
        db_session.commit()
    finally:
        # Re-enable foreign key checks
        db_session.execute(text("SET session_replication_role = 'origin'"))


def reset_all_sequences(db_session):
    """
    Reset all sequences to start from 1.
    Useful for ensuring deterministic IDs in tests.
    """
    result = db_session.execute(text("""
        SELECT sequence_name 
        FROM information_schema.sequences 
        WHERE sequence_schema = 'public'
    """))
    
    for (sequence_name,) in result:
        db_session.execute(text(f"ALTER SEQUENCE {sequence_name} RESTART WITH 1"))
    
    db_session.commit()


def get_table_row_count(db_session, table_name: str) -> int:
    """
    Get row count for a specific table.
    
    Args:
        db_session: Database session
        table_name: Name of the table
        
    Returns:
        Number of rows in the table
    """
    result = db_session.execute(
        text(f'SELECT COUNT(*) FROM "{table_name}"')
    )
    return result.scalar()


def get_all_table_counts(db_session) -> dict:
    """
    Get row counts for all tables.
    Useful for debugging test state.
    
    Returns:
        Dictionary mapping table names to row counts
    """
    result = db_session.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public'"
    ))
    tables = [row[0] for row in result]
    
    counts = {}
    for table in tables:
        counts[table] = get_table_row_count(db_session, table)
    
    return counts


def create_savepoint(db_session, name: str = 'test_savepoint'):
    """
    Create a savepoint for nested transaction testing.
    
    Args:
        db_session: Database session
        name: Name of the savepoint
    """
    db_session.execute(text(f"SAVEPOINT {name}"))


def rollback_to_savepoint(db_session, name: str = 'test_savepoint'):
    """
    Rollback to a previously created savepoint.
    
    Args:
        db_session: Database session
        name: Name of the savepoint
    """
    db_session.execute(text(f"ROLLBACK TO SAVEPOINT {name}"))


def release_savepoint(db_session, name: str = 'test_savepoint'):
    """
    Release a savepoint (commit its changes within the transaction).
    
    Args:
        db_session: Database session
        name: Name of the savepoint
    """
    db_session.execute(text(f"RELEASE SAVEPOINT {name}"))
