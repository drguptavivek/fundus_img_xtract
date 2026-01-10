"""
Pytest configuration with PostgreSQL test database.

This conftest.py provides fixtures for the restructured test suite with:
- PostgreSQL test database (instead of SQLite)
- Transaction-based test isolation
- Category-specific fixtures
- Test data factories and utilities
"""

import os
import sys
from pathlib import Path

# Add the project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from flask_login import FlaskLoginClient

from models import Base
from app import create_app


# ==============================================================================
# Database Configuration
# ==============================================================================

# Test database URL - uses dedicated test-db container
# From inside docker, connect to 'test-db' service (not localhost)
# From host, use localhost:5433
TEST_DATABASE_URL = os.getenv(
    'TEST_DATABASE_URL',
    'postgresql://test_user:test_password_change_in_production@test-db:5432/fundus_test'
)


# ==============================================================================
# Session-Scoped Fixtures (created once per test session)
# ==============================================================================

@pytest.fixture(scope="session")
def test_engine():
    """
    Create a test database engine (session-scoped).
    Creates all tables at the start of test session and drops them at the end.
    """
    engine = create_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,  # No connection pooling for tests
        echo=False,  # Set to True for SQL debugging
    )
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    yield engine
    
    # Cleanup: Drop all tables after test session
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


# ==============================================================================
# Function-Scoped Fixtures (created for each test)
# ==============================================================================

@pytest.fixture(scope="function")
def db_session(test_engine):
    """
    Create a database session for each test function.
    Uses transactions with automatic rollback for isolation.
    
    This ensures:
    - Each test starts with a clean state
    - Tests don't interfere with each other
    - Fast cleanup (rollback instead of DELETE)
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    
    # Create session bound to this connection
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=connection
    )
    session = TestingSessionLocal()
    
    yield session
    
    # Rollback transaction to cleanup
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def app(db_session):
    """
    Create a Flask app configured for testing.
    Uses the test database and in-memory rate limiting.
    """
    app = create_app()
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI=TEST_DATABASE_URL,
        LOGIN_DISABLED=False,
        # Rate limiting for tests
        RATELIMIT_ENABLED=True,
        RATELIMIT_STORAGE_URI='memory://',
        REDIS_URL='memory://',
        RATELIMIT_DEFAULT='500 per hour, 50 per minute',
        RATELIMIT_APPLICATION='1000 per hour, 100 per minute',
        RATELIMIT_SWALLOW_ERRORS=False,
    )
    
    # Re-initialize rate limiting with test config
    from utils.rate_limiter import init_rate_limiting
    init_rate_limiting(app)
    
    # Use FlaskLoginClient for testing
    app.test_client_class = FlaskLoginClient
    
    with app.app_context():
        yield app


@pytest.fixture(scope="function")
def client(app):
    """Create a test client for making HTTP requests"""
    return app.test_client()


# ==============================================================================
# SQLite Compatibility Fixtures (for unit tests that need simple DB)
# ==============================================================================

@pytest.fixture(scope="function")
def sqlite_session():
    """
    Simple in-memory SQLite session for pure unit tests.
    Use this only when you need a very lightweight DB for mocking.
    
    Note: Some features may not work due to SQLite limitations.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    engine = create_engine('sqlite:///:memory:')
    
    # Try to create tables, skip constraints that fail
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        # Log warning but continue - some tables may have been created
        print(f"Warning: SQLite table creation had issues: {e}")
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    yield session
    
    session.close()
    engine.dispose()


# ==============================================================================
# Cleanup and Utility Fixtures
# ==============================================================================

@pytest.fixture(autouse=True, scope="function")
def reset_sequences(request, db_session):
    """
    Reset sequences after each test for consistent IDs.
    Only runs for tests marked with @pytest.mark.reset_sequences
    """
    # This runs after the test
    yield
    
    # Check if test requested sequence reset
    if 'reset_sequences' in request.keywords:
        from tests.helpers.db_utils import reset_all_sequences
        reset_all_sequences(db_session)


@pytest.fixture
def db_utils(db_session):
    """
    Provide database utilities for tests.
    Usage: db_utils.truncate_tables(['users', 'roles'])
    """
    from tests.helpers import db_utils as utils
    
    class DBUtils:
        def truncate_tables(self, table_names=None):
            return utils.truncate_tables(db_session, table_names)
        
        def reset_sequences(self):
            return utils.reset_all_sequences(db_session)
        
        def get_row_count(self, table_name):
            return utils.get_table_row_count(db_session, table_name)
        
        def get_all_counts(self):
            return utils.get_all_table_counts(db_session)
    
    return DBUtils()


# ==============================================================================
# Legacy Fixtures (for backward compatibility)
# ==============================================================================

@pytest.fixture
def test_db(test_engine):
    """
    Legacy fixture for backward compatibility.
    Returns a session factory.
    """
    return sessionmaker(bind=test_engine)


# ==============================================================================
# Configuration
# ==============================================================================

def pytest_configure(config):
    """Pytest configuration hook"""
    # Add custom markers if not already present
    config.addinivalue_line(
        "markers", "reset_sequences: Reset database sequences after test"
    )
    config.addinivalue_line(
        "markers", "skip_postgres: Skip test if using PostgreSQL"
    )
    config.addinivalue_line(
        "markers", "skip_sqlite: Skip test if using SQLite"
    )