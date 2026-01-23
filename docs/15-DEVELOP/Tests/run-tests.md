# Test Execution Commands

This document provides commands to run tests in batches (one category at a time).

## Prerequisites

All tests must be run inside the Docker container:

```bash
# Use this prefix for all commands
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest
```

---

## Unit Tests

Run all unit tests:
```bash
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/unit/ -v --tb=short
```

Run specific unit test files:
```bash
# Admin tests
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/unit/admin/ -v

# Auth tests
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/unit/auth/ -v

# Utils tests (includes hospital scoping)
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/unit/utils/ -v

# Other unit tests
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/unit/test_infrastructure_verification.py -v
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/unit/test_user_fixtures.py -v
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/unit/test_password_hashing.py -v
```

---

## Integration Tests

Run all integration tests:
```bash
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/integration/ -v --tb=short
```

Run specific integration test files:
```bash
# Analytics integration
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/integration/analytics/ -v

# Auth integration
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/integration/auth/ -v

# Grading integration
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/integration/grading/ -v
```

---

## Security Tests

Run security tests one by one:
```bash
# Hospital isolation (cross-hospital scoping)
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/security/test_dashboard_isolation.py -v --tb=short

# PII leakage protection
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/security/test_pii_leakage.py -v --tb=short

# Filename anonymization
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/security/test_filename_anonymization.py -v --tb=short

# Query isolation
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/security/test_query_isolation.py -v --tb=short

# Apply scoping for site admin
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/security/test_apply_scoping_site_admin.py -v --tb=short
```

---

## Fixture Tests

Run fixture verification tests:
```bash
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/fixtures/ -v --tb=short
```

---

## Running Individual Tests

Run a specific test class:
```bash
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/unit/utils/test_hospital_scoping.py::TestGetUserLabUnitsInHospital -v
```

Run a specific test method:
```bash
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/unit/utils/test_hospital_scoping.py::TestGetUserLabUnitsInHospital::test_master_admin_gets_all_lab_units_in_hospital -v
```

---

## Test Options

- `-v` : Verbose output
- `--tb=short` : Shorter traceback format
- `-x` : Stop on first failure
- `-k "test_name"` : Run tests matching pattern
- `--maxfail=3` : Stop after N failures
- `-n 4` : Parallel execution (requires pytest-xdist)

---

## Quick Reference

```bash
# Unit tests (277 tests)
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/unit/ -v

# Integration tests
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/integration/ -v

# Security tests (run individually - see above)
docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run pytest tests/security/ -v
```
