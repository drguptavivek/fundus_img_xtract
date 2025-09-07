# Fundus Image Manager Test Suite

This directory contains the test suite for the Fundus Image Manager application.

## Test Organization

The tests are organized into the following files:

1. `test_master_data_creation.py` - Tests for master data (Hospitals, LabUnits, Diseases, Camera, Area)
2. `test_user_roles_and_assignments.py` - Tests for users in each role and lab unit
3. `test_auth_admin_routes.py` - Tests for authentication and admin routes
4. `test_file_uploading.py` - Tests for file uploading (ZIP and direct)
5. `test_verification_workflows.py` - Tests for verification workflows
6. `test_grading_functionality.py` - Tests for grading functionality
7. `test_dual_grading.py` - Tests for dual grading
8. `test_arbitration.py` - Tests for arbitration
9. `test_setup.py` - Master data and user setup for tests
10. `conftest.py` - Pytest configuration and fixtures

## Running Tests

To run the tests, use the following commands from the project root directory:

```bash
# Run all tests
uv run pytest tests/

# Run a specific test file
uv run pytest tests/test_master_data_creation.py

# Run tests with verbose output
uv run pytest tests/ -v

# Run tests and see coverage
uv run pytest tests/ --cov=.

# Run tests with coverage report
uv run pytest tests/ --cov=. --cov-report=html
```

## Test Environment

The tests use an in-memory SQLite database for isolation. Each test runs in a clean environment with:
- A fresh database
- All required tables created
- Master data populated
- Test users created

## Test Data

The tests create the following master data:
- 3 Hospitals
- 6 Lab Units
- 5 Cameras
- 5 Diseases
- 4 Areas

The tests create users with the following roles:
- Admin
- Ophthalmologist (Consultant)
- Resident
- Optometrist
- Data Manager
- File Uploader
- Contributor

Each user is assigned to appropriate lab units and hospitals as needed for testing.

## Test Coverage

The tests cover:
1. Master data creation and validation
2. User creation with role assignments
3. Authentication and authorization
4. File uploading functionality
5. Verification workflows
6. Grading functionality
7. Dual grading mechanisms
8. Arbitration functionality