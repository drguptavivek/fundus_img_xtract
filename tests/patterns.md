# Test Fix Patterns - Common Mistakes and Solutions

This document captures common patterns of mistakes found in tests and their solutions,
learned from fixing test failures across the test suite.

## Common Patterns

### 1. Database Session Management Issues

**Problem Pattern:**
```python
# WRONG: Using Session() directly
from models import Session
db = Session()
result = db.query(Model).all()
db.close()
```

**Solution Pattern:**
```python
# CORRECT: Using get_db_session()
from db_transaction_manager import get_db_session
with get_db_session() as db:
    result = db.query(Model).all()
```

**Why:**
- `get_db_session()` is properly mocked in test infrastructure via `_mock_get_db_session()`
- Using `Session()` directly bypasses test mocks, creating unmocked database connections
- Context manager ensures proper cleanup and transaction handling

**Files Affected:**
- `screenings/routes.py` - Fixed 5 routes using `Session()` directly
- `admin/audit_routes.py` - Added missing `session` import from Flask

---

### 2. Session/Transaction Scope Mismatches

**Problem Pattern:**
```python
# WRONG: Using session-scoped fixture without merging
def test_something(master_admin):  # session-scoped
    # master_admin is from different session, causes DetachedInstanceError
    assert master_admin.is_master_admin == True
```

**Solution Pattern:**
```python
# CORRECT: Always merge session-scoped fixtures
def test_something(master_admin, db_session):  # db_session is function-scoped
    admin = db_session.merge(master_admin)  # Merge into current test session
    assert admin.is_master_admin == True
```

**Why:**
- Session-scoped fixtures (from `seed_test_database`) use a committed database session
- Function-scoped tests use transactional sessions that get rolled back
- Accessing lazy-loaded attributes on detached instances causes DetachedInstanceError
- `merge()` attaches the object to the current session

**Files Affected:**
- `tests/fixtures/security.py` - Updated `master_admin` fixture to check for existing seeded user first
- `tests/unit/security/test_analytics_isolation.py` - Tests now use seeded master_admin

---

### 3. Mock Object Setup Issues

**Problem Pattern:**
```python
# WRONG: Mock returns wrong type or missing attributes
query_mock.filter.return_value = "filtered_query"  # String, not query object!
model_mock = Mock()  # No spec, returns MagicMock for any attribute
```

**Solution Pattern:**
```python
# CORRECT: Proper mock setup
query_mock.filter.return_value = MagicMock()  # Returns proper mock object
model_mock = Mock(spec=['id', 'name'])  # Only allows defined attributes
model_mock.id = 1
model_mock.name = "Test"
model_mock.lab_units = []  # Initialize required relationships
```

**Why:**
- Strings don't have `.where()` or `.filter()` methods - causes AttributeError
- Untyped Mocks return new Mocks for undefined attributes, breaking `if hasattr()` checks
- SQLAlchemy expects specific attributes on model objects

**Files Affected:**
- `tests/unit/auth/test_new_roles.py` - Fixed mock return values and added spec parameters
- `tests/unit/utils/test_image_search.py` - Added proper mock chains with iterables
- `tests/unit/templates/test_pii_masking_templates.py` - Created `NoneReturningMock` class

---

### 4. UnboundLocalError with current_user

**Problem Pattern:**
```python
# WRONG: Referencing current_user before conditional import
def some_function():
    user = current_user  # UnboundLocalError!
    if need_user:
        from flask_login import current_user
    return user
```

**Solution Pattern:**
```python
# CORRECT: Import at top or pass as parameter
def some_function(user_for_scoping=None):
    from flask_login import current_user  # Import at top
    user = user_for_scoping or current_user
    return user
```

**Why:**
- Python treats variables assigned anywhere in function as local throughout
- Conditional imports don't change the scoping rules
- Passing as parameter makes function more testable

**Files Affected:**
- `api/kpis/encounter_files_kpis.py` - Added `user_for_scoping` parameter to `get_filtered_encounter_dataframe()`
- Updated 9 call sites to pass `user_for_scoping=current_user`

---

### 5. Incorrect Test Expectations

**Problem Pattern:**
```python
# WRONG: Test expects wrong behavior
assert response.status_code == 302  # Expected redirect
# But @roles_required returns 403 for authenticated users without role
```

**Solution Pattern:**
```python
# CORRECT: Match actual implementation behavior
assert response.status_code == 403  # Correct expectation
# Or: update implementation to match documented behavior
```

**Why:**
- Tests should verify actual behavior, not assumed behavior
- If test is wrong, fix the test; if implementation is wrong, fix the implementation
- Document why behavior differs from expectations if needed

**Files Affected:**
- `tests/unit/admin/test_audit_dashboard.py` - Changed expectation from 302 to 403
- `tests/unit/utils/test_rate_limiter.py` - Updated config value expectations to match actual `deploy.config.env`

---

### 6. Mock Chains and Iterables

**Problem Pattern:**
```python
# WRONG: Mock query doesn't return iterable
mock_query.all.return_value = mock_object  # Single object, not list!
# When code does: for item in query.all():  # Fails - can't iterate single object
```

**Solution Pattern:**
```python
# CORRECT: Return list of mock objects
mock_query.all.return_value = [mock_object1, mock_object2]
# Or use side_effect for sequential calls
mock_query.all.side_effect = [[obj1, obj2], [obj3, obj4]]
```

**Why:**
- SQLAlchemy queries return lists, not single objects
- Tests must simulate the actual return type
- Use `side_effect` when multiple calls to same method need different results

**Files Affected:**
- `tests/unit/utils/test_image_search.py` - Fixed 7 tests with proper iterable mock setup
- Added `side_effect` functions to handle sequential query calls

---

### 7. None Handling in Templates

**Problem Pattern:**
```python
# WRONG: Mock returns Mock for undefined attributes, not None
mock_obj = Mock()
# Template: {{ row.patient_encounter.patient_id }}
# Gets Mock object, not None, breaking {% if row.patient_encounter %} checks
```

**Solution Pattern:**
```python
# CORRECT: Custom mock that returns None for undefined attributes
class NoneReturningMock:
    def __getattr__(self, name):
        return None  # Return None, not another Mock
```

**Why:**
- Standard Mock objects create infinite chains of Mocks
- Jinja2 templates need actual None to trigger `|default()` filters
- `{% if obj %}` is True for Mock objects, False for None

**Files Affected:**
- `tests/unit/templates/test_pii_masking_templates.py` - Created `NoneReturningMock` class
- Changed `patient_id=None` to `patient_id=''` to avoid `|length` filter errors

---

## Fixture and Session Patterns

### 8. Fixture Name Conflicts

**Problem Pattern:**
```python
# WRONG: Same fixture name in multiple modules causes conflicts
# tests/fixtures/security.py
@pytest.fixture
def master_admin(db_session):
    return User(username='master_admin', is_master_admin=True)

# tests/fixtures/seeded_data.py
@pytest.fixture(scope="session")
def master_admin(seed_test_database):
    return seed_test_database['users']['master_admin']
# Pytest uses function-scoped fixture, breaking tests that expect session-scoped one
```

**Solution Pattern:**
```python
# CORRECT: Check for existing data before creating, or use different names
@pytest.fixture
def master_admin(db_session):
    # First check if seeded master_admin exists
    existing = db_session.query(User).filter(
        User.username == 'master_admin',
        User.is_master_admin == True
    ).first()

    if existing:
        return db_session.merge(existing)  # Use seeded data

    # Only create if doesn't exist (backwards compatibility)
    return User(username='master_admin', is_master_admin=True)
```

**Why:**
- Pytest resolves fixture names by scope: function-scoped overrides session-scoped
- Tests expecting seeded (committed) data get function-scoped (uncommitted) data
- Flask-Login's `load_user()` can't find uncommitted users via HTTP requests
- Always check for seeded data before creating new instances

**Files Affected:**
- `tests/fixtures/security.py` - Updated `master_admin` to check for existing seeded user first

---

### 9. Session Wrapping for Test Isolation

**Problem Pattern:**
```python
# WRONG: Direct session usage bypasses test mocks
@pytest.fixture(scope="function")
def db_session(test_engine):
    session = Session(bind=test_engine)
    yield session
    session.close()
    # No cleanup of shared state!
```

**Solution Pattern:**
```python
# CORRECT: Wrap session to prevent accidental commits/closes
class _TestSessionWrapper:
    def __init__(self, session):
        self._session = session

    def __getattr__(self, name):
        return getattr(self._session, name)

    def commit(self):
        # Prevent commit - use flush() instead
        self._session.flush()

    def close(self):
        # Prevent closure of shared test session
        pass

@pytest.fixture(scope="function")
def app(db_session):
    global _test_db_session
    wrapped_session = _TestSessionWrapper(db_session)
    _test_db_session = wrapped_session  # Monkeypatch target
    yield create_app()
```

**Why:**
- Tests share a single database session via monkeypatched `get_db_session()`
- Direct commits/closes break the transaction rollback strategy
- Wrapper ensures test isolation while allowing route code to work normally
- All database operations go through the same mocked session

**Files Affected:**
- `tests/conftest.py` - `_TestSessionWrapper` class and `app` fixture

---

### 10. Monkeypatching Database Imports

**Problem Pattern:**
```python
# WRONG: Forgetting to monkeypatch all Session imports
from db_transaction_manager import get_db_session

# But route code imports Session directly:
from models import Session  # Bypasses mock!
def route_handler():
    db = Session()
    return db.query(Model).all()
```

**Solution Pattern:**
```python
# CORRECT: Monkeypatch all Session imports in test setup
@pytest.fixture(scope="function")
def app(db_session):
    wrapped_session = _TestSessionWrapper(db_session)

    # Patch the main one
    patcher_dbsession = patch('db_transaction_manager.DbSession', return_value=wrapped_session)
    patcher_dbsession.start()

    # Patch models.Session (used by old code)
    patcher_models = patch('models.Session', return_value=wrapped_session)
    patcher_models.start()

    # Patch Session in specific modules
    patcher_auth_routes = patch('auth.routes.Session', return_value=wrapped_session)
    patcher_auth_routes.start()

    # Patch server_side_session (critical for session persistence)
    import server_side_session
    patcher_session_interface = patch('server_side_session.DbSession', return_value=wrapped_session)
    patcher_session_interface.start()

    yield app

    # Cleanup: stop all patchers
    patcher_session_interface.stop()
    patcher_auth_routes.stop()
    patcher_models.stop()
    patcher_dbsession.stop()
```

**Why:**
- Route code may import `Session` directly from various modules
- Each import creates a separate reference that must be patched individually
- Missing patches cause route code to use real database connections
- Systematic patching ensures consistent test behavior

**Files Affected:**
- `tests/conftest.py` - All Session import patches in `app` fixture

---

### 11. Fixture Dependency Order

**Problem Pattern:**
```python
# WRONG: Fixture depends on implicitly loaded fixture
@pytest.fixture
def my_test(client):  # Depends on 'app' but not declared
    # client depends on app, but app fixture hasn't run yet!
    # _test_db_session monkeypatch not set up
    response = client.get('/some-route')
```

**Solution Pattern:**
```python
# CORRECT: Explicitly declare all fixture dependencies
@pytest.fixture
def my_test(app, client):  # app runs first, sets up mocks
    # _test_db_session is now properly monkeypatched
    response = client.get('/some-route')
```

**Why:**
- Pytest resolves fixtures in declaration order
- Dependent fixtures must be explicitly listed
- `client` depends on `app`, but if only `client` is listed, `app` setup may not complete
- Explicit dependencies ensure proper initialization order

**Files Affected:**
- All test files - Always list `app` or `db_session` when needed

---

### 12. Session-Scoped Fixture Transaction Isolation

**Problem Pattern:**
```python
# WRONG: Session-scoped fixtures commit data that can't be rolled back
@pytest.fixture(scope="session")
def core_test_data(test_engine):
    Session = sessionmaker(bind=test_engine)
    session = Session()

    # Creates data in committed transaction
    entities = CoreEntityFactory.setup_core_entities(session)
    session.commit()  # Data is now permanent!

    yield entities

    # Can't rollback - other tests may depend on this data
    session.close()
```

**Solution Pattern:**
```python
# CORRECT: Document that session-scoped data is shared and read-only
@pytest.fixture(scope="session")
def core_test_data(test_engine):
    """
    Create core test data once per session (hospitals, lab units, diseases, roles).
    This persists for the entire test session for efficiency.

    IMPORTANT: This data is COMMITTED and cannot be rolled back.
    Tests should treat this as READ-ONLY reference data.
    For test-specific mutable data, use function-scoped fixtures that create
    and rollback their own data.
    """
    Session = sessionmaker(bind=test_engine)
    session = Session()

    try:
        entities = CoreEntityFactory.setup_core_entities(session)
        session.commit()  # Intentional commit for shared reference data
        yield entities
    finally:
        session.close()

# Function-scoped for mutable test data
@pytest.fixture(scope="function")
def test_encounter(db_session, core_test_data):
    # Creates in transactional session, gets rolled back
    encounter = PatientEncounters(
        lab_unit_id=core_test_data['lab_units'][0].id,
        patient_id="TEST_PATIENT"
    )
    db_session.add(encounter)
    db_session.flush()  # Flush, not commit
    yield encounter
    # Automatic rollback by db_session fixture
```

**Why:**
- Session-scoped fixtures are shared across all tests in the session
- Committed data cannot be rolled back - becomes permanent for test run
- Function-scoped fixtures use transaction rollback for isolation
- Test design: session-scoped = read-only reference data, function-scoped = mutable test data

**Files Affected:**
- `tests/conftest.py` - `core_test_data` session-scoped fixture
- `tests/fixtures/seeded_data.py` - Session-scoped fixtures for reference data
- All test files - Use session-scoped for reference, function-scoped for mutations

---

### 13. Flask-Login Session Authentication in Tests

**Problem Pattern:**
```python
# WRONG: Setting user_id as integer breaks Flask-Login
@pytest.fixture
def auth_client(client, user):
    def _auth_client(user):
        with client.session_transaction() as sess:
            sess['_user_id'] = user.id  # INTEGER - WRONG!
            sess['_fresh'] = True
        return client
    return _auth_client
# Flask-Login expects string in session, authentication fails
```

**Solution Pattern:**
```python
# CORRECT: Always use string for _user_id in session
@pytest.fixture
def auth_client(client, user):
    """
    Create an authenticated client for a specific user.

    Uses session-based authentication (sets _user_id directly in session)
    to bypass the actual /login POST request. This avoids transaction
    conflicts with the test database isolation strategy.
    """
    def _auth_client(user, password='Test@2026'):
        with client.session_transaction() as sess:
            # CRITICAL: Must be string, not integer
            # Flask-Login expects string in session
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
        return client
    return _auth_client
```

**Why:**
- Flask-Login stores `user_id` as string in session (due to session serialization)
- Integer IDs work in-memory but fail when session is serialized/deserialized
- During actual HTTP requests, session goes through serialization
- Tests must match production behavior for valid authentication

**Files Affected:**
- `tests/fixtures/auth_client.py` - Fixed to use `str(user.id)` with comment explaining why

---

### 14. Fixture Scoping: When to Use Which Scope

**Problem Pattern:**
```python
# WRONG: Using wrong scope for fixture purpose
@pytest.fixture(scope="session")  # Too broad!
def test_encounter(db_session):
    # Creates mutable data that persists across tests
    return PatientEncounters(patient_id="TEST")

@pytest.fixture  # Function-scoped (correct)
def reference_data(db_session):
    # Creates reference hospitals/labs - wasteful to recreate every test
    return create_hospital()
```

**Solution Pattern:**
```python
# CORRECT: Match scope to fixture purpose

# Session-scoped: Expensive, immutable reference data
@pytest.fixture(scope="session")
def core_test_data(test_engine):
    """
    Hospitals, lab units, diseases, roles - created once per test session.
    Read-only reference data used by many tests.
    """
    return setup_reference_data()

# Module-scoped: Shared state within test module
@pytest.fixture(scope="module")
def shared_cache():
    """
    Expensive object reused within test module.
    Reset between modules but not within module.
    """
    return ExpensiveCache()

# Function-scoped: Mutable test data (default)
@pytest.fixture
def test_encounter(db_session):
    """
    Test-specific encounter, created fresh for each test.
    Gets rolled back after test.
    """
    encounter = PatientEncounters(patient_id="TEST")
    db_session.add(encounter)
    db_session.flush()
    return encounter
```

**Scope Selection Guide:**

| Scope | Use Case | Examples | Commit? | Rollback? |
|-------|----------|----------|----------|-----------|
| `session` | Expensive, immutable reference data | Hospitals, Diseases, Roles | Yes | No |
| `module` | Shared state within module | Cache, configuration | No | No |
| `function` | Mutable test data (default) | Test entities, mock setups | No | Yes |

**Why:**
- **Session-scoped**: Created once, committed, shared across all tests (efficient but permanent)
- **Module-scoped**: Shared within module, reset between modules (balanced)
- **Function-scoped**: Isolated per test, rolled back (safe but recreates data)

**Rules:**
- Use **session-scoped** for: expensive reference data that never changes during tests
- Use **function-scoped** for: anything that mutates database state
- Default to **function-scoped** unless you have a clear performance reason

**Files Affected:**
- `tests/fixtures/security.py` - Session-scoped site admins (reference data)
- `tests/fixtures/seeded_data.py` - Session-scoped reference data queries
- `tests/conftest.py` - Function-scoped `db_session` for transaction isolation

---

## Quick Reference Checklist (Updated)

When writing or fixing tests, check:

### Database & Sessions
- [ ] **Session Management**: Using `get_db_session()` not `Session()`?
- [ ] **Scope Merging**: Merged session-scoped fixtures into function-scoped tests?
- [ ] **Session Wrapping**: Not accidentally committing/closing shared test session?

### Fixtures
- [ ] **Fixture Names**: No conflicting fixture names across modules?
- [ ] **Fixture Dependencies**: All dependencies explicitly declared?
- [ ] **Fixture Scope**: Using appropriate scope (session/module/function)?
- [ ] **Monkeypatching**: All Session imports patched in test setup?

### Mocks
- [ ] **Mock Setup**: Mocks have correct return types and required attributes?
- [ ] **Iterables**: Mock queries return lists, not single objects?
- [ ] **None Handling**: Template mocks return None for missing attributes?

### Code
- [ ] **Imports**: All required imports at module level, especially `session` from Flask
- [ ] **current_user**: Not referencing before conditional import?
- [ ] **Expectations**: Test expectations match actual implementation?

### Flask-Login
- [ ] **Session Auth**: Using `str(user.id)` not integer in session?
- [ ] **Session Key**: Using `_user_id` (with underscore), not `user_id`?

---

## Related Files

- `tests/conftest.py` - Main test configuration and fixtures
- `tests/fixtures/security.py` - Hospital isolation fixtures
- `tests/fixtures/seeded_data.py` - Session-scoped seeded data fixtures
- `utils/hospital_scoping.py` - Hospital scoping utilities
- `db_transaction_manager.py` - Database session management
- `auth/roles.py` - Role-based access control
