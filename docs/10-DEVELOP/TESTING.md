# Testing Framework Documentation

## Overview

The Fundus Image Manager application uses pytest as its primary testing framework. This document provides comprehensive guidance on writing, running, and maintaining tests for the application.

## Test User Management

### Creating Test Users

For local development and testing, you can create test users using the provided scripts:

1. **Create Admin User**:
   ```bash
   uv run python scripts/create_test_admin.py
   ```
   This creates an admin user with username `admin` and password `Vivek@2026`.

2. **Create All Test Users**:
   ```bash
   uv run python scripts/add_test_users.py
   ```
   This creates a comprehensive set of test users with different roles and permissions.

### Automatic Test User Creation

The testing framework automatically creates test users with different roles for testing purposes. These users are created in the test database and are isolated from the production database.

#### Test User Roles Created

1. **Admin Users**: Full system access for testing admin functionality
   - `admin`: Default admin user created by `create_test_admin.py`
   - `testadmin`: Development administrator created by `add_test_users.py`
2. **Ophthalmologist Users**: Medical professional access for grading and review
   - `test2ComophArbit`: Arbitrator for Glaucoma and DR
   - `test2ComophFac`: Resident2 for Glaucoma and DR
   - `test2ComophResident`: Resident for Glaucoma and DR
3. **File Uploader User**: Access to upload and manage images
   - `testUploader`: File upload permissions
4. **Optometrist User**: Access to upload and review images
   - `testOptometrist`: Optometrist permissions
5. **Data Manager User**: Data management permissions
   - `testManager`: Data management permissions

#### Test Account Credentials

| Role | Username | Password | Full Name | Lab Units | Special Permissions |
|------|----------|----------|-----------|-----------|-------------------|
| Admin | admin | Vivek@2026 | Default Admin | - | Full system access |
| Admin | testadmin | Vivek@2026 | Development Administrator | Community Ophthalmology | Full system access |
| Ophthalmologist | test2ComophArbit | Vivek@2026 | Test Comoph Arbitrator | Community Ophthalmology | Arbitrator for Glaucoma & DR |
| Ophthalmologist | test2ComophFac | Vivek@2026 | Test Comoph Resident2 | Community Ophthalmology | Resident2 for Glaucoma & DR |
| Ophthalmologist | test2ComophResident | Vivek@2026 | Test Comoph Resident | Community Ophthalmology | Resident for Glaucoma & DR |
| File Uploader | testUploader | Vivek@2026 | Test Community Ophthalmology Uploader | Community Ophthalmology | File upload permissions |
| Optometrist | testOptometrist | Vivek@2026 | Test Community Ophthalmology Optometrist | Community Ophthalmology | Optometrist permissions |
| Data Manager | testManager | Vivek@2026 | Test Community Ophthalmology Manager | Community Ophthalmology | Data management permissions |

**Note**:
- All test accounts use `Vivek@2026` as the password
- Test users use core entities from the application (hospitals, lab units, diseases)
- Hospital: RPC AIIMS
- Lab Unit: Community Ophthalmology
- Diseases: Glaucoma, DR (Diabetic Retinopathy)

#### User Lifecycle and Persistence

- **Creation**: Test users are created automatically when the `test_users` fixture is used
- **Isolation**: Each test function gets a fresh database state with clean test users
- **Cleanup**: Test users are automatically removed when the test session ends
- **No Persistence in Production**: Test users never persist in the production database
- **Test Database Retention**: Test users are retained in the test database for the duration of the test session
- **Session Scope**: Test users exist for the entire test session (not just individual tests) to improve performance
- **Automatic Rollback**: All database changes are rolled back after each test, ensuring clean state

#### Database Configuration

The testing framework uses two different SQLite databases:

1. **Primary Test Database** (`test_db` fixture):
   - Type: Temporary file-based SQLite database
   - Location: Created using `tempfile.mkstemp()` in the system's temp directory
   - Scope: Session-scoped (created once per test session)
   - Purpose: Used for creating and managing test data including users, roles, and permissions
   - Lifecycle: Created at the beginning of the test session and destroyed when the session ends

2. **Flask App Database** (`app` fixture):
   - Type: In-memory SQLite database
   - Location: `sqlite:///:memory:`
   - Scope: Function-scoped (created fresh for each test)
   - Purpose: Used by the Flask application for HTTP request testing
   - Lifecycle: Created fresh for each test function and destroyed when the test completes

#### Database Isolation

Both test databases are completely isolated from the production database:
- **No Production Impact**: Test data never affects the production database
- **Temporary Storage**: File-based database is stored in a temporary file that's automatically deleted
- **Memory-based Testing**: Flask tests use a pure in-memory database for maximum speed
- **Clean State**: Each test starts with a clean database state
- **Automatic Cleanup**: All databases are automatically cleaned up when tests complete

### Using Test Users in Tests

```python
def test_with_admin_user(admin_user):
    """Test using the admin user fixture"""
    # admin_user fixture provides a pre-created admin user
    assert admin_user.username == "testadmin"
    assert admin_user.has_role("admin")

def test_with_multiple_roles(test_users):
    """Test using multiple test users"""
    # test_users fixture provides a dictionary of users by role
    admin = test_users['admin']
    ophthalmologist = test_users['ophthalmologist']
    resident = test_users['resident']
    
    # Test interactions between different user roles
    assert admin.has_role("admin")
    assert ophthalmologist.has_role("ophthalmologist")
    assert resident.has_role("resident")
```

### Security Considerations

- All test users use the same password: `Vivek@2026`
- Test users have predictable usernames for reliable testing
- Test users are created with the same entity IDs as defined in the core setup
- Test users are associated with the Community Ophthalmology lab unit under RPC AIIMS hospital

## Test Structure

### Directory Organization

```
tests/
├── conftest.py                 # Shared fixtures and test configuration
├── test_context_manager.py     # Database context manager tests
├── test_imageSearchUtil.py     # Image search utility tests
├── test_rate_limiting.py       # Rate limiting functionality tests
├── test_route_integration.py   # Route integration tests
├── test_route_verification.py  # Route verification tests
├── test_runner_pytest.py       # Image search functionality tests (pytest version)
├── test_server_side_session.py # Server-side session tests
└── test_style_guide_rate_limit.py # Style guide rate limit tests
```

### Test Categories

1. **Unit Tests**: Test individual functions and methods in isolation
2. **Integration Tests**: Test interaction between components
3. **Functional Tests**: Test complete workflows and user scenarios
4. **E2E Tests**: End-to-end testing using Playwright (in `/e2e` directory)

## Test Configuration

### Fixtures (conftest.py)

The `conftest.py` file provides shared fixtures for all tests:

```python
import pytest
from app import create_app
from models import db, User, Role, UserRole, Hospital, LabUnit, Disease
from db_transaction_manager import get_db_session

@pytest.fixture(scope="session")
def test_db():
    """Create a test database session"""
    # Creates an in-memory SQLite database for testing
    # Returns the database session
    pass

@pytest.fixture(scope="function")
def db_session(test_db):
    """Provide a database session for each test function"""
    # Ensures each test has a clean database state
    # Handles rollback after each test
    pass

@pytest.fixture(scope="function")
def app(test_db):
    """Create a Flask app for testing"""
    # Configures Flask app for testing
    # Sets up test client
    pass

@pytest.fixture(scope="function")
def admin_user(db_session):
    """Create an admin user for testing"""
    # Creates a user with admin role
    # Returns the user object
    pass

@pytest.fixture(scope="function")
def test_users(db_session):
    """Create multiple test users with different roles"""
    # Creates users with various roles (admin, ophthalmologist, resident, etc.)
    # Returns a dictionary of users by role
    pass
```

### Environment Setup

Tests use a separate test database configuration:

```python
# In conftest.py
@pytest.fixture(scope="session")
def test_db():
    # Create in-memory SQLite database
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    
    # Create all tables
    Base.metadata.create_all(engine)
    
    # Create session
    session = Session()
    
    yield session
    
    # Cleanup
    session.close()
```

## Writing Tests

### Basic Test Structure

```python
import pytest
from utils.imageSearchUtil import search_images_strict

def test_basic_search(admin_user, db_session):
    """Test basic search functionality"""
    # Arrange - Set up test data
    user_id = admin_user.id
    
    # Act - Perform the operation
    results, total = search_images_strict(
        db_session=db_session,
        page=1,
        per_page=10,
        user_id=user_id
    )
    
    # Assert - Verify the results
    assert isinstance(results, list)
    assert isinstance(total, int)
```

### Test Patterns

#### 1. Testing with Mocks

```python
from unittest.mock import patch, MagicMock

def test_with_mock():
    """Test function with mocked dependencies"""
    with patch('utils.some_util.function') as mock_function:
        mock_function.return_value = "mocked_value"
        
        result = function_being_tested()
        
        assert result == "expected_result"
        mock_function.assert_called_once()
```

#### 2. Testing Database Operations

```python
def test_database_operation(db_session):
    """Test database operations"""
    # Create test data
    test_record = Model(name="Test", value=123)
    db_session.add(test_record)
    db_session.commit()
    
    # Test the operation
    result = get_record_by_id(db_session, test_record.id)
    
    # Verify
    assert result is not None
    assert result.name == "Test"
```

#### 3. Testing Flask Routes

```python
def test_route_with_client(app):
    """Test Flask routes with test client"""
    with app.test_client() as client:
        # Login if needed
        client.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Vivek@2026'
        })
        
        # Test the route
        response = client.get('/protected-route')
        
        assert response.status_code == 200
        assert b'expected content' in response.data
```

#### 4. Testing Error Conditions

```python
def test_error_handling(db_session):
    """Test error handling"""
    with pytest.raises(ValueError) as exc_info:
        function_that_raises_error(db_session, invalid_param)
    
    assert "expected error message" in str(exc_info.value)
```

## Test Data Management

### Using Fixtures for Test Data

```python
@pytest.fixture
def sample_image_data(db_session):
    """Create sample image data for testing"""
    image = DirectImageUpload(
        uuid="test-uuid-123",
        filename="test.jpg",
        uploader_id=1,
        lab_unit_id=1,
        camera_id=1
    )
    db_session.add(image)
    db_session.commit()
    return image

def test_with_sample_data(sample_image_data):
    """Test using sample data"""
    assert sample_image_data.uuid == "test-uuid-123"
```

### Cleaning Up Test Data

```python
@pytest.fixture(autouse=True)
def cleanup_db(db_session):
    """Automatically cleanup database after each test"""
    yield
    # Rollback transaction to ensure clean state
    db_session.rollback()
```

## Running Tests

### Basic Commands

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_imageSearchUtil.py

# Run specific test function
uv run pytest tests/test_imageSearchUtil.py::test_function_name

# Run with verbose output
uv run pytest -v

# Run with coverage
uv run pytest --cov=utils --cov-report=html
```

### Test Options

```bash
# Stop on first failure
uv run pytest -x

# Run failed tests only
uv run pytest --lf

# Run tests with specific pattern
uv run pytest -k "test_search"

# Show local variables in tracebacks
uv run pytest -l

# Run with debugging
uv run pytest --pdb
```

## Test Best Practices

### 1. Test Organization

- **Descriptive Names**: Use clear, descriptive test names that explain what is being tested
- **Arrange-Act-Assert**: Structure tests with clear setup, execution, and verification phases
- **One Assertion Per Test**: Focus on testing one behavior per test when possible
- **Test Independence**: Ensure tests don't depend on each other

### 2. Test Data

- **Minimal Data**: Use only the test data needed for each test
- **Fixtures**: Use fixtures for reusable test data
- **Cleanup**: Always clean up test data after tests
- **Isolation**: Keep test data isolated between tests

### 3. Mocking and Patching

- **Patch Interfaces**: Mock interfaces rather than implementations
- **Specific Mocks**: Use specific mocks for different test scenarios
- **Verify Interactions**: Use `assert_called_with` to verify correct parameters
- **Avoid Over-Mocking**: Only mock what's necessary for the test

### 4. Database Testing

- **Transactions**: Use database transactions for test isolation
- **Rollback**: Rollback changes after each test
- **Seed Data**: Use consistent seed data for tests
- **Performance**: Keep database operations minimal in tests

## Common Test Scenarios

### 1. Authentication Tests

```python
def test_login_success(client):
    """Test successful login"""
    response = client.post('/auth/login', data={
        'username': 'testadmin',
        'password': 'Vivek@2026'
    })
    assert response.status_code == 302  # Redirect after login
    
def test_login_failure(client):
    """Test login with wrong password"""
    response = client.post('/auth/login', data={
        'username': 'testadmin',
        'password': 'wrong_password'
    })
    assert response.status_code == 200
    assert b'Invalid credentials' in response.data
```

### 2. Permission Tests

```python
def test_admin_route_access(client, admin_user):
    """Test admin-only route access"""
    login_client(client, admin_user)
    response = client.get('/admin/dashboard')
    assert response.status_code == 200

def test_unauthorized_access(client, regular_user):
    """Test unauthorized access to admin route"""
    login_client(client, regular_user)
    response = client.get('/admin/dashboard')
    assert response.status_code == 403
```

### 3. API Endpoint Tests

```python
def test_api_endpoint(client, admin_user):
    """Test API endpoint with authentication"""
    login_client(client, admin_user)
    response = client.get('/api/hospitals')
    assert response.status_code == 200
    data = response.get_json()
    assert 'hospitals' in data
```

### 4. Form Submission Tests

```python
def test_form_submission(client):
    """Test form submission with CSRF"""
    # Get form page to get CSRF token
    response = client.get('/form')
    csrf_token = extract_csrf_token(response.data)
    
    # Submit form
    response = client.post('/form', data={
        'csrf_token': csrf_token,
        'field1': 'value1',
        'field2': 'value2'
    })
    assert response.status_code == 302
```

## Debugging Tests

### 1. Using Print Statements

```python
def test_debug_example(db_session):
    """Test with debug output"""
    # Add debug prints
    print(f"Debug: db_session = {db_session}")
    print(f"Debug: user count = {db_session.query(User).count()}")
    
    # Test logic
    result = some_function(db_session)
    print(f"Debug: result = {result}")
    
    assert result is not None
```

### 2. Using pytest Debugger

```bash
# Run with debugger
uv run pytest --pdb

# Run specific test with debugger
uv run pytest tests/test_file.py::test_function --pdb
```

### 3. Using Breakpoints

```python
def test_with_breakpoint(db_session):
    """Test with breakpoint"""
    import pdb; pdb.set_trace()
    
    # Test logic here
    result = some_function(db_session)
    
    assert result is not None
```

## Test Coverage

### Measuring Coverage

```bash
# Generate coverage report
uv run pytest --cov=utils --cov-report=html

# Generate coverage for specific module
uv run pytest --cov=utils.imageSearchUtil --cov-report=term-missing

# Coverage with minimum threshold
uv run pytest --cov=utils --cov-fail-under=80
```

### Coverage Best Practices

- **Aim for High Coverage**: Target 80%+ coverage for critical modules
- **Focus on Logic**: Don't just test for coverage percentage
- **Test Edge Cases**: Ensure error conditions are tested
- **Regular Checks**: Run coverage regularly in CI/CD

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: uv run pytest --cov=utils --cov-report=xml
      - uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
```

## Troubleshooting

### Common Issues

1. **Import Errors**
   ```bash
   # Ensure PYTHONPATH includes project root
   export PYTHONPATH=$PYTHONPATH:$(pwd)
   uv run pytest
   ```

2. **Database Connection Issues**
   ```python
   # Ensure test database is properly configured
   @pytest.fixture(scope="session")
   def test_db():
       engine = create_engine("sqlite:///:memory:")
       # ... rest of setup
   ```

3. **Fixture Not Found**
   ```python
   # Ensure fixtures are defined in conftest.py or imported
   from tests.conftest import admin_user
   ```

4. **Test Isolation Issues**
   ```python
   # Use function-scoped fixtures for test isolation
   @pytest.fixture(scope="function")
   def db_session(test_db):
       # ... setup with rollback
   ```

## Performance Testing

### Timing Tests

```python
import time

def test_performance(db_session):
    """Test performance of function"""
    start_time = time.time()
    
    result = expensive_function(db_session)
    
    end_time = time.time()
    execution_time = end_time - start_time
    
    assert execution_time < 1.0  # Should complete in under 1 second
    assert result is not None
```

### Benchmarking

```python
import pytest

@pytest.mark.parametrize("input_size", [10, 100, 1000])
def test_scalability(db_session, input_size):
    """Test scalability with different input sizes"""
    # Create test data of specified size
    test_data = create_test_data(db_session, input_size)
    
    # Measure performance
    start_time = time.time()
    result = function_under_test(test_data)
    end_time = time.time()
    
    # Assert performance scales appropriately
    execution_time = end_time - start_time
    assert execution_time < input_size * 0.001  # Linear scaling
```

## Conclusion

This testing framework provides a solid foundation for ensuring the reliability and correctness of the Fundus Image Manager application. By following these guidelines and best practices, developers can create comprehensive tests that catch bugs early and facilitate maintainable code.

Remember that good tests are:
- **Readable**: Easy to understand what is being tested
- **Maintainable**: Easy to update when code changes
- **Reliable**: Consistent results across runs
- **Fast**: Quick execution to encourage frequent testing
- **Isolated**: Independent of other tests and external dependencies