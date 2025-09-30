"""
Database transaction management utilities for consistent session handling
across the application.
"""
from contextlib import contextmanager
from typing import Generator, Optional
from sqlalchemy.orm import Session
from models import Session as DbSession


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions that ensures proper cleanup.
    
    Usage:
    with get_db_session() as db:
        # Perform database operations
        result = db.query(SomeModel).all()
        db.commit()  # Optional, will be called automatically if no exception
    """
    db = DbSession()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def transaction_scope() -> Generator[Session, None, None]:
    """
    Context manager for database transactions that provides a consistent
    transaction boundary for related operations.
    
    Usage:
    with transaction_scope() as db:
        # Perform multiple related database operations
        grade = Grade(...)
        db.add(grade)
        task.state = 'updated'
        db.add(task)
        # Commit happens automatically at the end if no exception occurs
    """
    db = DbSession()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def execute_in_transaction(operation_func, *args, **kwargs):
    """
    Execute a function within a database transaction.
    
    Args:
        operation_func: Function that takes db session as first argument
        *args, **kwargs: Arguments to pass to the operation function
        
    Returns:
        Result of the operation function
    """
    db = DbSession()
    try:
        result = operation_func(db, *args, **kwargs)
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()