# Test Suite Documentation

## Overview

This directory contains the test suite for the fundus image extraction and grading system. The tests are organized by category and use pytest with PostgreSQL for database testing.

## Directory Structure

```
tests/
├── conftest.py                    # Main pytest configuration and fixtures
├── fixtures/                      # Test fixture modules
│   ├── hospital_grading_pools.py  # Grading pool fixtures for multi-hospital testing
│   ├── hospital_roles.py          # Role-based user fixtures
│   ├── security.py                # Security and hospital isolation fixtures
│   ├── seed_database.py           # Session-scoped database seeding
│   └── seeded_data.py             # Function-scoped access to seeded data
├── helpers/                       # Test utilities and factories
│   ├── db_utils.py                # Database utility functions
│   ├── factories.py               # Legacy test data factories
│   └── test_factories.py          # Modern test data factories (NEW)
├── unit/                          # Unit tests
│   └── security/                  # Security-focused unit tests
│       ├── test_analytics_isolation.py  # Analytics hospital scoping tests
│       └── test_screenings_isolation.py # Screenings hospital scoping tests
├── integration/                   # Integration tests
└── e2e/                          # End-to-end tests (Playwright)
```

## Test Database

### Configuration

- **Database**: PostgreSQL 18 (test-db container)
- **URL**: `postgresql://test_user:test_password_change_in_production@test-db:5432/fundus_test`
- **Isolation**: Transaction-based rollback after each test
- **Seeding**: Session-scoped seeding of core entities (hospitals, diseases, etc.)

### Running Tests

```bash
# All tests
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/

# Specific test file
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/unit/security/test_analytics_isolation.py

# Specific test
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/unit/security/test_analytics_isolation.py::TestEncounterViewIsolation::test_cross_hospital_encounter_view_forbidden -xvs

# With coverage
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/ --cov=. --cov-report=html
```

## Fixtures

### Core Fixtures (`conftest.py`)

#### Database Fixtures

- **`test_engine`** (session-scoped): PostgreSQL engine, creates/drops all tables
- **`db_session`** (function-scoped): Transactional session with automatic rollback
- **`app`** (function-scoped): Flask app configured for testing
- **`client`** (function-scoped): Flask test client

#### Authentication Fixtures

- **`admin_user`**: Admin user for testing
- **`ophthalmologist_user`**: Ophthalmologist with lab unit assignment
- **`resident_user`**: Resident with grading permissions
- **`arbitrator_user`**: Arbitrator with arbitration permissions
- **`authenticated_client`**: Client authenticated as admin
- **`login_user`**: Helper function to perform login via POST
- **`logged_in_client`**: Client with admin logged in via actual login flow
- **`auth_client_factory`**: Factory to create authenticated clients for any user

#### Utility Fixtures

- **`csrf_token`**: Get CSRF token from application
- **`make_request_with_auth`**: Helper to make authenticated requests with CSRF
- **`db_utils`**: Database utility functions (truncate, reset sequences, etc.)

### Security Fixtures (`fixtures/security.py`, `fixtures/hospital_roles.py`)

#### Hospital Fixtures

- **`test_hospitals`** (session-scoped): Dict of seeded hospitals
- **`hospital_data`** (function-scoped): Hospitals with lab units in convenient structure
  ```python
  {
      'hospital_a': {
          'hospital': Hospital object,
          'lab_units': [LabUnit, LabUnit]
      },
      'hospital_b': {...}
  }
  ```

#### User Fixtures

- **`master_admin`**: Global admin (no hospital assignment)
- **`site_admin_hospital_a/b`**: Site admins for each hospital
- **`hosp_a_data_manager`**, **`hosp_b_data_manager`**: Data managers per hospital
- **`hosp_a_file_uploader`**, **`hosp_b_file_uploader`**: File uploaders per hospital
- **`hosp_a_optometrist`**, **`hosp_b_optometrist`**: Optometrists per hospital
- **`hosp_a_res_1/2/3/4`**: Residents for Hospital A grading pool
- **`hosp_b_res_1/2/3/4`**: Residents for Hospital B grading pool
- **`hosp_a_arb_1/2`**: Arbitrators for Hospital A
- **`hosp_b_arb_1/2`**: Arbitrators for Hospital B

#### Metadata Fixtures

- **`test_metadata`** (function-scoped): Cameras, diseases, and areas
  ```python
  {
      'cameras': {'test_camera': Camera},
      'diseases': {'dr': Disease, 'glaucoma': Disease, 'amd': Disease},
      'areas': {'test_area': Area}
  }
  ```

### Seeded Data (`fixtures/seed_database.py`)

The `seed_test_database` fixture (session-scoped, autouse=True) populates the database with:

- **Roles**: master_admin, local_admin, ophthalmologist, resident, arbitrator, optometrist, fileUploader, data_manager, researcher, dataset_creator, analytics_viewer
- **Diseases**: DR, Glaucoma, AMD, Test Disease
- **Cameras**: Test Camera, Fundus Camera, Topcon TRC-50DX, Canon CR-2
- **Areas**: Test Area, Macula, Optic Disc, Peripheral Retina
- **Hospitals**: Hospital A (id=1), Hospital B (id=2)
- **Lab Units**: Lab A1, Lab A2 (Hospital A), Lab B1, Lab B2 (Hospital B)
- **Users**: master_admin, site_admin_a, site_admin_b, ophthalmologist_a/b, ophthalmologist_cross

## Test Data Factories (`helpers/test_factories.py`)

The `TestDataFactory` class provides factory methods for creating valid model instances with all required fields and relationships.

### Usage

```python
from tests.helpers.test_factories import TestDataFactory

def test_something(db_session, hospital_data, test_metadata):
    # Create a patient encounter with required ZipFile
    encounter = TestDataFactory.create_patient_encounter(
        db_session,
        lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
        patient_id="TEST_PATIENT_001",
    )
    
    # Create an encounter file
    file = TestDataFactory.create_encounter_file(
        db_session,
        patient_encounter_id=encounter.id,
        lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
        filename="test_image.jpg",
    )
    
    # Create a grading task
    task = TestDataFactory.create_grading_task(
        db_session,
        lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
        disease_id=test_metadata['diseases']['dr'].id,
        encounter_file_id=file.id,
    )
    
    # Create a direct image upload
    direct = TestDataFactory.create_direct_image_upload(
        db_session,
        lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
        uploader_id=user.id,
        hospital_id=hospital_data['hospital_a']['hospital'].id,
        camera_id=test_metadata['cameras']['test_camera'].id,
        disease_id=test_metadata['diseases']['dr'].id,
        area_id=test_metadata['areas']['test_area'].id,
    )
```

### Factory Methods

#### `create_zip_file(db_session, zip_filename=None, md5_hash=None)`
Creates a ZipFile with unique filename and MD5 hash.

#### `create_patient_encounter(db_session, lab_unit_id, patient_id=None, ...)`
Creates a PatientEncounters instance with required ZipFile relationship.
- Auto-creates ZipFile if not provided
- Auto-generates patient_id, name, capture_date if not provided

#### `create_encounter_file(db_session, patient_encounter_id, lab_unit_id, filename=None, file_type="image")`
Creates an EncounterFile linked to a patient encounter.

#### `create_direct_image_upload(db_session, lab_unit_id, uploader_id, hospital_id, camera_id, disease_id, area_id, ...)`
Creates a DirectImageUpload with all required fields.
- Auto-generates filename, folder_rel, file_hash if not provided

#### `create_grading_task(db_session, lab_unit_id, disease_id, encounter_file_id=None, direct_image_upload_id=None, state="pending")`
Creates a GradingTask for either an encounter file or direct upload.

## Test Categories

### Unit Tests (`tests/unit/`)

Fast, isolated tests for individual components.

#### Security Tests (`tests/unit/security/`)

**`test_analytics_isolation.py`**: Verifies analytics routes enforce hospital scoping
- Tests that data managers only see their hospital's data
- Tests that global admins can access all data
- Tests 404 responses for cross-hospital access attempts
- Covers: encounters, images, tasks, direct uploads

**`test_screenings_isolation.py`**: Verifies screenings routes enforce hospital scoping
- Tests list and detail views
- Tests reprocess_pdf and delete_reports operations
- Ensures cross-hospital access is denied

### Integration Tests (`tests/integration/`)

Tests that verify interactions between multiple components.

### E2E Tests (`tests/e2e/`)

Browser-based tests using Playwright (currently stale, needs update).

## Writing New Tests

### Basic Test Structure

```python
import pytest
from tests.helpers.test_factories import TestDataFactory

class TestMyFeature:
    """Test my feature functionality."""
    
    def test_something(self, db_session, hospital_data, test_metadata):
        """Test description."""
        # Arrange: Create test data
        encounter = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
        )
        
        # Act: Perform the action
        result = my_function(encounter.id)
        
        # Assert: Verify the outcome
        assert result.status == "success"
```

### Testing with Authentication

#### Option 1: Using `auth_client` Fixture (Recommended)

The `auth_client` fixture performs real login via POST request and maintains session cookies:

```python
def test_authenticated_route(auth_client, hosp_a_data_manager):
    """Test route requires authentication."""
    # Get authenticated client for this user
    client = auth_client(hosp_a_data_manager)
    
    # Make authenticated requests
    response = client.get('/protected/route')
    assert response.status_code == 200
```

**Benefits**:
- Tests actual login flow
- Maintains session cookies automatically
- More realistic than session manipulation

#### Option 2: Using `multi_auth_clients` for Multiple Users

When testing with multiple users simultaneously:

```python
def test_multi_user_isolation(multi_auth_clients, hosp_a_data_manager, hosp_b_data_manager):
    """Test isolation between different users."""
    # Create authenticated clients for both users
    clients = multi_auth_clients([hosp_a_data_manager, hosp_b_data_manager])
    
    # Each client maintains its own session
    response_a = clients[hosp_a_data_manager.username].get('/data')
    response_b = clients[hosp_b_data_manager.username].get('/data')
    
    # Verify isolation
    assert response_a.data != response_b.data
```

#### Option 3: Session Manipulation (For Unit Tests)

For pure unit tests where you don't need full login flow:

```python
def test_with_session(client, hosp_a_data_manager):
    """Test using session manipulation."""
    with client.session_transaction() as sess:
        sess['user_id'] = hosp_a_data_manager.id
        sess['_fresh'] = True
    
    response = client.get('/protected/route')
    assert response.status_code == 200
```

**Note**: Session manipulation may not work for all routes due to Flask-Login configuration. Use `auth_client` for integration tests.

### Testing Hospital Isolation

```python
def test_cross_hospital_access_denied(self, client, hospital_data, hosp_a_data_manager, db_session):
    """Test users cannot access other hospitals' data."""
    # Create data for hospital B
    encounter_b = TestDataFactory.create_patient_encounter(
        db_session,
        lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
    )
    
    # Login as hospital A user
    with client.session_transaction() as sess:
        sess['user_id'] = hosp_a_data_manager.id
        sess['_fresh'] = True
    
    # Try to access hospital B's data
    response = client.get(f'/encounter/{encounter_b.id}')
    
    # Should be denied
    assert response.status_code == 404
```

## Testing Conventions

### Naming Conventions

1. **Test Files**: `test_<feature>.py` (e.g., `test_analytics_isolation.py`)
2. **Test Classes**: `Test<Feature><Aspect>` (e.g., `TestEncounterViewIsolation`)
3. **Test Methods**: `test_<what>_<expected>` (e.g., `test_cross_hospital_encounter_view_forbidden`)

### Test Organization

- **Unit Tests**: `tests/unit/<blueprint>/` - Fast, isolated component tests
- **Integration Tests**: `tests/integration/` - Multi-component interaction tests
- **E2E Tests**: `tests/e2e/` - Full browser-based user flow tests
- **Security Tests**: `tests/unit/security/` - Hospital isolation and access control tests

### Fixture Usage Patterns

#### Always Use These Fixtures

- **`db_session`**: For database operations (function-scoped, auto-rollback)
- **`hospital_data`**: For hospital and lab unit data (function-scoped)
- **`test_metadata`**: For cameras, diseases, areas (function-scoped)
- **`TestDataFactory`**: For creating test data with all required fields

#### Authentication Fixtures

- **`auth_client`**: For single-user authenticated tests
- **`multi_auth_clients`**: For multi-user isolation tests
- **Session manipulation**: Only for unit tests where login flow isn't needed

### Data Creation Pattern

**Always use TestDataFactory** instead of creating models directly:

```python
# ✅ GOOD - Uses factory
encounter = TestDataFactory.create_patient_encounter(
    db_session,
    lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
)

# ❌ BAD - Creates model directly (will fail due to missing required fields)
encounter = PatientEncounters(
    patient_id="TEST",
    lab_unit_id=lab_unit.id,
)
```

### Test Structure Pattern

Follow the **Arrange-Act-Assert** pattern:

```python
def test_something(db_session, hospital_data, test_metadata):
    """Test description explaining what and why."""
    # ARRANGE: Set up test data
    encounter = TestDataFactory.create_patient_encounter(
        db_session,
        lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
    )
    
    # ACT: Perform the action being tested
    result = my_function(encounter.id)
    
    # ASSERT: Verify the outcome
    assert result.status == "success"
    assert result.data is not None
```

### Isolation Testing Pattern

For hospital isolation tests, always test both **positive** (own hospital) and **negative** (cross-hospital) cases:

```python
class TestFeatureIsolation:
    """Test feature enforces hospital isolation."""
    
    def test_own_hospital_access_allowed(self, auth_client, hospital_data, hosp_a_data_manager, db_session):
        """Users can access their own hospital's data."""
        # Create data for hospital A
        data_a = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
        )
        
        # Login as hospital A user
        client = auth_client(hosp_a_data_manager)
        
        # Should succeed
        response = client.get(f'/data/{data_a.id}')
        assert response.status_code == 200
    
    def test_cross_hospital_access_forbidden(self, auth_client, hospital_data, hosp_a_data_manager, db_session):
        """Users cannot access other hospitals' data."""
        # Create data for hospital B
        data_b = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
        )
        
        # Login as hospital A user
        client = auth_client(hosp_a_data_manager)
        
        # Should be denied
        response = client.get(f'/data/{data_b.id}')
        assert response.status_code == 404
    
    def test_global_admin_bypass(self, auth_client, hospital_data, master_admin, db_session):
        """Global admins can access all hospitals' data."""
        # Create data for hospital B
        data_b = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
        )
        
        # Login as global admin
        client = auth_client(master_admin)
        
        # Should succeed
        response = client.get(f'/data/{data_b.id}')
        assert response.status_code == 200
```

## Best Practices

1. **Use Factories**: Always use `TestDataFactory` to create test data - it handles all required fields and relationships
2. **Function-Scoped Fixtures**: Use function-scoped fixtures (`hospital_data`, `test_metadata`) to avoid detached instance errors
3. **Transaction Isolation**: Each test runs in its own transaction that's rolled back - no cleanup needed
4. **Descriptive Names**: Use clear, descriptive test names that explain what's being tested
5. **Arrange-Act-Assert**: Structure tests with clear setup, action, and verification sections
6. **Test One Thing**: Each test should verify one specific behavior
7. **Use Fixtures**: Leverage pytest fixtures for common setup instead of duplicating code

## Troubleshooting

### Detached Instance Errors

**Problem**: `DetachedInstanceError: Instance <Model> is not bound to a Session`

**Solution**: Use function-scoped fixtures instead of session-scoped ones. The `hospital_data` and `test_metadata` fixtures are already function-scoped.

### NOT NULL Constraint Violations

**Problem**: `null value in column "field_name" violates not-null constraint`

**Solution**: Use `TestDataFactory` methods which handle all required fields automatically.

### Session Authentication Issues

**Problem**: Tests getting 301 redirects instead of accessing protected routes

**Solution**: Use session manipulation with `client.session_transaction()`:
```python
with client.session_transaction() as sess:
    sess['user_id'] = user.id
    sess['_fresh'] = True
```

### Unique Constraint Violations

**Problem**: `duplicate key value violates unique constraint`

**Solution**: The factory auto-generates unique values. If you need specific values, pass them explicitly:
```python
encounter = TestDataFactory.create_patient_encounter(
    db_session,
    lab_unit_id=lab_unit.id,
    patient_id="UNIQUE_ID_123",  # Explicit unique ID
)
```

## Future Improvements

1. **Fix Session Authentication**: Resolve 301 redirect issues in analytics isolation tests
2. **Update E2E Tests**: Refresh Playwright tests to match current application state
3. **Add Performance Tests**: Create tests for query performance and N+1 detection
4. **Expand Coverage**: Add tests for remaining blueprints and edge cases
5. **API Tests**: Create comprehensive API endpoint tests
6. **Load Tests**: Add load testing for concurrent user scenarios
