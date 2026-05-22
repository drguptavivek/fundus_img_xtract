"""
Pytest configuration with PostgreSQL test database.

This conftest.py provides fixtures for the restructured test suite with:
- PostgreSQL test database (instead of SQLite)
- Transaction-based test isolation
- Category-specific fixtures
- Test data factories and utilities
"""

# Load security fixtures for hospital isolation testing
pytest_plugins = ['fixtures.security', 'fixtures.metadata', 'fixtures.workflow']

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
from urllib.parse import urlparse

# Test database URL - uses dedicated test-db container
# From inside docker, connect to 'test-db' service (not localhost)
# From host, use localhost:5433
TEST_DATABASE_URL = os.getenv(
    'TEST_DATABASE_URL',
    'postgresql://test_user:test_password_change_in_production@test-db:5432/fundus_test'
)
_parsed_test_db = urlparse(TEST_DATABASE_URL)
if "test" not in (_parsed_test_db.path or "").lower():
    raise RuntimeError("Refusing to run pytest: TEST_DATABASE_URL must point to a test database.")

# Ensure all model and alembic imports resolve to the test DB. Docker runtime
# containers already set DATABASE_URL to the application database, so setdefault
# is not safe for pytest.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from models import Base

# Global test session holder for monkeypatching
_test_db_session = None

from contextlib import contextmanager
@contextmanager
def _mock_get_db_session():
    global _test_db_session
    if _test_db_session:
        print(f"DEBUG: Entering GLOBAL MOCK get_db_session (session id: {id(_test_db_session)})")
        yield _test_db_session
    else:
        # Fallback to original if not set (should not happen during request)
        from models import Session as DbSession
        db = DbSession()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

class _TestSessionWrapper:
    """Wrapper that prevents accidental closure or commit of the test session."""
    def __init__(self, session):
        self._session = session
    
    def __getattr__(self, name):
        return getattr(self._session, name)

    def commit(self):
        # Prevent commit during tests to maintain transaction isolation
        # print("DEBUG: Ignoring session.commit() in test wrapper")
        self._session.flush()

    def close(self):
        # Prevent closure of the shared test session
        # print("DEBUG: Ignoring session.close() in test wrapper")
        pass
    
    def rollback(self):
        # Allow rollback but log it
        # print("DEBUG: session.rollback() called in test wrapper")
        self._session.rollback()

# Monkeypatch db_transaction_manager BEFORE any other imports that might use it
import db_transaction_manager
db_transaction_manager.get_db_session = _mock_get_db_session
db_transaction_manager.transaction_scope = _mock_get_db_session

# Deferred import for create_app to allow patching


# ==============================================================================
# Database Configuration
# ==============================================================================

# Test database URL - uses dedicated test-db container
# From inside docker, connect to 'test-db' service (not localhost)
# From host, use localhost:5433
# (Defined above to ensure models bind to test DB.)


# ==============================================================================
# Session-Scoped Fixtures (created once per test session)
# ==============================================================================

@pytest.fixture(scope="session")
def test_engine():
    """
    Create a test database engine (session-scoped).
    Runs Alembic migrations to create tables and seed core entities.

    Uses migrations to ensure:
    1. All tables are created with correct schema
    2. Core entities are seeded with production IDs (hospitals, diseases, etc.)
    3. PostgreSQL sequences are properly synchronized
    """
    from alembic.config import Config

    engine = create_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,  # No connection pooling for tests
        echo=False,  # Set to True for SQL debugging
    )

    # Drop and recreate schema for a clean slate at session start.
    # Using raw SQL with CASCADE to handle materialized views and dependencies.
    # This ensures idempotent test runs even if previous session crashed.
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()

    # Run Alembic migrations to create schema and seed core data
    alembic_cfg = Config()
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    alembic_cfg.set_main_option("script_location", str(project_root / "migrations"))

    from alembic import command
    try:
        # Force Alembic env.py to target the test database
        os.environ["DATABASE_URL"] = TEST_DATABASE_URL
        # Run all migrations from scratch (schema was just recreated)
        # Use "heads" to support multiple heads in test-only context.
        command.upgrade(alembic_cfg, "heads")

        print("✅ Test database migrations applied successfully")
    except Exception as e:
        print(f"❌ Error running migrations: {e}")
        # Fallback to metadata.create_all if migrations fail
        # NOTE: This creates empty tables without seed data - tests may fail
        Base.metadata.create_all(bind=engine)
        print("⚠️  Fell back to metadata.create_all() - seed data NOT available!")

    yield engine

    # Cleanup: Drop schema with CASCADE to handle materialized views
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()
    engine.dispose()


# ==============================================================================
# Function-Scoped Fixtures (created for each test)
# ==============================================================================

@pytest.fixture(scope="function")
def db_session(test_engine):
    """
    Create a database session for each test function.
    Uses transactions with automatic rollback for isolation.
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
    global _test_db_session
    # Wrap the db_session to prevent accidental closure
    wrapped_session = _TestSessionWrapper(db_session)
    old_session = _test_db_session
    _test_db_session = wrapped_session

    from unittest.mock import patch
    
    # Also patch models.Session for those who use it directly
    patcher_models = patch('models.Session', return_value=wrapped_session)
    patcher_models.start()
    
    # Patch DbSession in db_transaction_manager as well
    import db_transaction_manager
    patcher_dbsession = patch('db_transaction_manager.DbSession', return_value=wrapped_session)
    patcher_dbsession.start()
    
    # Patch DbSession in server_side_session (CRITICAL for session persistence)
    import server_side_session
    patcher_session_interface = patch('server_side_session.DbSession', return_value=wrapped_session)
    patcher_session_interface.start()
    
    # Patch Session in auth.routes (CRITICAL for load_user to see test users)
    patcher_auth_routes = patch('auth.routes.Session', return_value=wrapped_session)
    patcher_auth_routes.start()
    
    # Patch Session in preprocess.anonymize_image (CRITICAL for anonymization workflow tests)
    patcher_preprocess = patch('preprocess.anonymize_image.Session', return_value=wrapped_session)
    patcher_preprocess.start()

    # Patch environ to force settings that can't be set via config alone
    # This must happen before create_app() reads env vars
    env_patcher = patch.dict(os.environ, {
        "FORCE_HTTPS": "false", 
        "SESSION_COOKIE_SECURE": "false",
        "SESSION_COOKIE_SAMESITE": "Lax",
        "THUMBNAIL_MAINTENANCE_ENABLED": "false",
        "MATERIALIZED_VIEW_SCHEDULE_ENABLED": "false",
        "RATELIMIT_ENABLED": "false"  # Disable rate limiting for tests significantly speeds them up
    })
    env_patcher.start()

    # Patch CaptchaManager to always pass validation in tests
    patcher_captcha = patch('utils.captcha.CaptchaManager.validate_captcha', return_value=(True, "Success"))
    patcher_captcha.start()

    # Patch EmailConfigService to avoid database queries during app initialization
    # This prevents transaction aborts when email_settings table doesn't exist
    patcher_email_config = patch('utils.email_config.EmailConfigService.get_email_config', return_value=None)
    patcher_email_config.start()

    from app import create_app
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
    
    # Catch and print exceptions in tests to see tracebacks
    @app.errorhandler(500)
    def handle_500(e):
        import traceback
        import sys
        print("\n!!! EXCEPTION IN APP (500) !!!", file=sys.stderr)
        traceback.print_exc()
        return "Internal Server Error", 500

    try:
        with app.app_context():
            yield app
    finally:
        patcher_models.stop()
        patcher_dbsession.stop()
        patcher_session_interface.stop()
        patcher_auth_routes.stop()
        patcher_preprocess.stop()
        env_patcher.stop()
        patcher_captcha.stop()
        _test_db_session = old_session


@pytest.fixture(scope="function")
def client(app):
    """Create a test client for making HTTP requests"""
    return app.test_client()


# ==============================================================================
# Test Data Fixtures
# ==============================================================================

@pytest.fixture(scope="session")
def core_test_data(test_engine, seed_test_database):
    """
    Create core test data once per session (hospitals, lab units, diseases, roles).
    This persists for the entire test session for efficiency.

    Depends on seed_test_database to ensure correct lab units are created first.
    """
    from tests.helpers.factories import CoreEntityFactory
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=test_engine)
    session = Session()
    
    try:
        entities = CoreEntityFactory.setup_core_entities(session)
        session.commit()
        yield entities
    finally:
        session.close()


@pytest.fixture
def run_runner_test(db_session, clean_db):
    """Fixture to run runner tests cleanly."""
    pass


def create_authenticated_client(app, user, db_session=None):
    """
    Helper to create a test client authenticated as a specific user.
    Uses Flask-Login's session management to simulate login.

    Args:
        app: Flask application
        user: User object (may be session-scoped/detached)
        db_session: Optional session to merge detached users (Pattern 2)
    """
    # Pattern 2: Always merge if db_session is provided to ensure fresh attachment
    # This prevents DetachedInstanceError when user is from session-scoped fixture
    if db_session:
        user = db_session.merge(user)

    with app.test_client() as client:
        with client.session_transaction() as sess:
            # Set the user_id in session directly, simulating login
            # Flask-Login uses '_user_id' key by default
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
        return client


@pytest.fixture
def admin_user(db_session, core_test_data):
    """Create an admin user for testing"""
    from tests.helpers.factories import UserFactory
    
    user = UserFactory.create_admin(db_session)
    db_session.flush()
    return user


@pytest.fixture
def ophthalmologist_user(db_session, core_test_data):
    """Create an ophthalmologist user with lab unit assignment"""
    from tests.helpers.factories import UserFactory
    from models import LabUnit
    
    # Merge lab_unit into current session
    lab_unit = db_session.merge(core_test_data['lab_unit'])
    user = UserFactory.create_ophthalmologist(
        db_session,
        lab_units=[lab_unit]
    )
    db_session.flush()
    return user


@pytest.fixture
def resident_user(db_session, core_test_data):
    """Create a resident user with grading permissions"""
    from tests.helpers.factories import UserFactory
    
    user = UserFactory.create_with_permissions(
        db_session,
        role_name='resident',
        disease_id=core_test_data['glaucoma'].id,
        lab_unit_id=core_test_data['lab_unit'].id,
        can_grade_resident=True
    )
    db_session.flush()
    return user


@pytest.fixture
def arbitrator_user(db_session, core_test_data):
    """Create an arbitrator user with arbitration permissions"""
    from tests.helpers.factories import UserFactory
    
    user = UserFactory.create_with_permissions(
        db_session,
        role_name='ophthalmologist',
        username='test_arbitrator',
        disease_id=core_test_data['glaucoma'].id,
        lab_unit_id=core_test_data['lab_unit'].id,
        can_arbitrate=True
    )
    db_session.flush()
    return user


@pytest.fixture
def test_users(db_session, core_test_data):
    """
    Create a complete set of test users for comprehensive testing.
    Returns a dict with all user types.

    Note: This fixture first checks if users exist in the seeded data
    (from seed_test_database) before creating new ones to avoid
    UniqueViolation errors.
    """
    from tests.helpers.factories import UserFactory
    from models import LabUnit, Disease, User

    # Merge entities into current session
    lab_unit = db_session.merge(core_test_data['lab_unit'])
    glaucoma = db_session.merge(core_test_data['glaucoma'])

    # Check for existing seeded users first (Pattern 8 from patterns.md)
    existing_admin = db_session.query(User).filter_by(username='test_admin').first()
    if existing_admin:
        admin_user = db_session.merge(existing_admin)
    else:
        admin_user = UserFactory.create_admin(db_session, username='test_admin')

    users = {
        'admin': admin_user,
        'ophthalmologist': UserFactory.create_ophthalmologist(
            db_session,
            username='test_ophthalmologist',
            lab_units=[lab_unit]
        ),
        'resident': UserFactory.create_with_permissions(
            db_session,
            role_name='resident',
            username='test_resident',
            disease_id=glaucoma.id,
            lab_unit_id=lab_unit.id,
            can_grade_resident=True
        ),
        'arbitrator': UserFactory.create_with_permissions(
            db_session,
            role_name='ophthalmologist',
            username='test_arbitrator',
            disease_id=glaucoma.id,
            lab_unit_id=lab_unit.id,
            can_arbitrate=True
        ),
    }

    db_session.flush()
    return users


@pytest.fixture
def authenticated_client(client, admin_user):
    """
    Create a client that's authenticated as admin user.
    Useful for integration tests that need authenticated requests.
    """
    with client.session_transaction() as sess:
        sess['user_id'] = admin_user.id
        sess['_fresh'] = True
    return client


@pytest.fixture
def login_user(client):
    """
    Helper fixture to perform actual login via POST to /login.
    Returns a function that logs in a user and returns the response.
    
    Usage:
        def test_something(login_user, admin_user):
            response = login_user(admin_user.username, 'Test@2026')
            assert response.status_code == 302
    """
    def do_login(username, password='Test@2026', follow_redirects=False):
        """
        Perform login via POST request.
        
        Args:
            username: Username to login with
            password: Password (default: 'Test@2026')
            follow_redirects: Whether to follow redirects
            
        Returns:
            Response object
        """
        # Get CSRF token from login page
        login_page = client.get('/login')
        
        # Extract CSRF token (if CSRF is enabled)
        csrf_token = None
        if b'csrf_token' in login_page.data:
            import re
            match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', login_page.data)
            if match:
                csrf_token = match.group(1).decode('utf-8')
        
        # Perform login
        data = {
            'username': username,
            'password': password,
        }
        if csrf_token:
            data['csrf_token'] = csrf_token
        
        response = client.post(
            '/login',
            data=data,
            follow_redirects=follow_redirects
        )
        return response
    
    return do_login


@pytest.fixture
def logged_in_client(client, admin_user, login_user):
    """
    Client with admin user logged in via actual login flow.
    Uses real login POST request (not session manipulation).
    
    Usage:
        def test_something(logged_in_client):
            response = logged_in_client.get('/admin/dashboard')
            assert response.status_code == 200
    """
    login_user(admin_user.username, 'Test@2026')
    return client


@pytest.fixture
def auth_client_factory(client, login_user):
    """
    Factory to create authenticated clients for any user.
    
    Usage:
        def test_something(auth_client_factory, resident_user):
            resident_client = auth_client_factory(resident_user)
            response = resident_client.get('/grading/tasks')
            assert response.status_code == 200
    """
    def make_auth_client(user, password='Test@2026'):
        """Create authenticated client for given user"""
        login_user(user.username, password)
        return client
    return make_auth_client


@pytest.fixture
def csrf_token(client):
    """
    Get CSRF token from the application.
    Useful for forms that require CSRF protection.
    
    Usage:
        def test_form_submission(client, csrf_token, admin_user):
            response = client.post('/some/form', data={
                'csrf_token': csrf_token,
                'field': 'value'
            })
    """
    response = client.get('/login')  # Or any page with CSRF token
    
    import re
    match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', response.data)
    if match:
        return match.group(1).decode('utf-8')
    
    # Fallback: try to get from meta tag
    match = re.search(rb'<meta name="csrf-token" content="([^"]+)"', response.data)
    if match:
        return match.group(1).decode('utf-8')
    
    return None


@pytest.fixture
def make_request_with_auth(client, csrf_token):
    """
    Helper to make authenticated requests with CSRF token.
    
    Usage:
        def test_post_request(make_request_with_auth, logged_in_client):
            response = make_request_with_auth(
                'POST', 
                '/api/endpoint',
                json={'data': 'value'}
            )
    """
    def do_request(method, url, **kwargs):
        """Make request with CSRF token in headers"""
        headers = kwargs.pop('headers', {})
        if csrf_token:
            headers['X-CSRFToken'] = csrf_token
        
        kwargs['headers'] = headers
        
        if method.upper() == 'GET':
            return client.get(url, **kwargs)
        elif method.upper() == 'POST':
            return client.post(url, **kwargs)
        elif method.upper() == 'PUT':
            return client.put(url, **kwargs)
        elif method.upper() == 'DELETE':
            return client.delete(url, **kwargs)
        elif method.upper() == 'PATCH':
            return client.patch(url, **kwargs)
        else:
            raise ValueError(f"Unsupported method: {method}")
    
    return do_request


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
# ===================================================================
# Security Fixtures (Hospital Isolation)
# ===================================================================

# Import all security fixtures from fixtures/security.py
# Note: master_admin is also available from fixtures/seeded_data.py (session-scoped)
# The function-scoped one here takes precedence in tests that import it directly
from tests.fixtures.security import (
    test_hospitals,
    test_lab_units,
    master_admin,  # Function-scoped from security.py
    site_admin_hospital_a,
    site_admin_hospital_b,
    ophthalmologist_hospital_a,
    ophthalmologist_cross_hospital,
    optometrist_hospital_a,
    dataset_creator,
)


# Import grading pool fixtures
from tests.fixtures.hospital_grading_pools import (
    hospital_a_grading_pool,
    hospital_b_grading_pool,
    hosp_a_res_1, hosp_a_res_2, hosp_a_res_3, hosp_a_res_4,
    hosp_a_arb_1, hosp_a_arb_2,
    hosp_b_res_1, hosp_b_res_2, hosp_b_res_3, hosp_b_res_4,
    hosp_b_arb_1, hosp_b_arb_2,
    cross_grader_a_to_b, cross_grader_b_to_a,
)


# Import role-based user fixtures
from tests.fixtures.hospital_roles import (
    hosp_a_file_uploader, hosp_a_optometrist, hosp_a_data_manager,
    hosp_a_data_exporter, hosp_a_analyst, hosp_a_site_admin,
    hosp_b_file_uploader, hosp_b_optometrist, hosp_b_data_manager,
    hosp_b_data_exporter, hosp_b_analyst, hosp_b_site_admin,
    analytics_viewer_global,
    all_hospital_a_users, all_hospital_b_users,
)

# Import database seeding fixture (autouse=True, runs at session start)
from tests.fixtures.seed_database import seed_test_database

# Import simplified fixtures that query seeded data
from tests.fixtures.seeded_data import (
    test_hospitals, test_lab_units, test_metadata, hospital_data,
    site_admin_hospital_a, site_admin_hospital_b, master_admin,
    ophthalmologist_hospital_a, ophthalmologist_hospital_b,
    ophthalmologist_cross_hospital
)

# Import authentication fixtures
from tests.fixtures.auth_client import auth_client, multi_auth_clients
