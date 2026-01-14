# Test Fixtures Documentation

## Overview

This document describes the pytest fixture architecture, conflicts, and dependencies for the Fundus Image Manager test suite.

---

## Fixture Ecosystem

### Session-Scoped Fixtures (Run Once Per Test Session)

| Fixture | Location | Purpose |
|---------|----------|---------|
| `test_engine` | conftest.py | Creates test database engine, drops/recreates tables |
| `seed_test_database` | fixtures/seed_database.py | **AUTOUSE** - Seeds core entities (roles, diseases, hospitals, lab units, users) |
| `core_test_data` | conftest.py | Creates core entities via CoreEntityFactory |
| `test_hospitals` | fixtures/security.py | Creates Hospital A (id=1) and Hospital B (id=2) |
| `test_lab_units` | fixtures/security.py | Creates 6 lab units (3 per hospital) |
| `site_admin_hospital_a` | fixtures/security.py | Site admin for Hospital A |
| `site_admin_hospital_b` | fixtures/security.py | Site admin for Hospital B |

### Function-Scoped Fixtures (Run For Each Test)

| Fixture | Location | Purpose |
|---------|----------|---------|
| `db_session` | conftest.py | Database session with transaction rollback for test isolation |
| `master_admin` | fixtures/security.py | Master admin user (is_master_admin=True) |
| `ophthalmologist_hospital_a` | fixtures/security.py | Ophthalmologist in Hospital A |
| `ophthalmologist_cross_hospital` | fixtures/security.py | Ophthalmologist who can grade in both hospitals |
| `optometrist_hospital_a` | fixtures/security.py | Optometrist for Hospital A |
| `dataset_creator` | fixtures/security.py | Dataset creator role user |

---

## Critical Fixture Conflicts

### Lab Unit ID Collision

**Three different fixture systems create lab units with different IDs:**

#### 1. seed_test_database (autouse, runs FIRST)
```python
# Creates 4 lab units:
Lab A1 (id=1, hospital_id=1)
Lab A2 (id=2, hospital_id=1)
Lab B1 (id=3, hospital_id=2)  ← CONFLICT!
Lab B2 (id=4, hospital_id=2)
```

#### 2. test_lab_units (security.py)
```python
# Creates 6 lab units:
lab_a1 (id=1, hospital_id=1)
lab_a2 (id=2, hospital_id=1)
lab_a3 (id=3, hospital_id=1)  ← CONFLICT! (skipped if exists)
lab_b1 (id=4, hospital_id=2)
lab_b2 (id=5, hospital_id=2)
lab_b3 (id=6, hospital_id=2)
```

#### 3. CoreEntityFactory.setup_core_entities
```python
# Same as security.py - 6 lab units with IDs 1-6
```

### What Actually Gets Created

| ID | seed_database | security.py | Final Result | Hospital |
|----|---------------|------------|--------------|----------|
| 1 | Lab A1 | lab_a1 | ✅ Lab A1 | A |
| 2 | Lab A2 | lab_a2 | ✅ Lab A2 | A |
| 3 | **Lab B1** | **lab_a3** | ❌ **Lab B1 wins** | **B (wrong!)** |
| 4 | Lab B2 | lab_b1 | ✅ Lab B1 | B |
| 5 | - | lab_b2 | ❌ Not created | - |
| 6 | - | lab_b3 | ❌ Not created | - |

**Result:** Only 4 lab units created, not 6. Lab unit ID 3 is Hospital B instead of Hospital A!

---

## Impact Analysis

### Tests Affected

- **76 total test files**
- **41 test files** use lab units (54%)
- **31 unit tests**
- **34 integration tests**
- **7 security tests**

### Currently Failing Tests (4)

| Test | Expected | Actual | Issue |
|------|----------|--------|-------|
| `test_master_admin_gets_all_lab_units_in_hospital` | lab_a3 (id=3, Hosp A) | Lab B1 (id=3, Hosp B) | ID collision |
| `test_master_admin_gets_all_lab_units_without_hospital_filter` | 6 lab units | 4 lab units | IDs 5,6 not created |
| `test_regular_user_gets_only_own_hospital_lab_units` | lab_a1 (id=1) | empty set | User fixture issue |
| `test_apply_scoping_filters_by_hospital_for_upload` | hospital_id=1 | empty set | Data visibility issue |

### Hardcoded References Found

```python
# Tests that assume specific lab unit IDs:
tests/unit/analytics/test_kpi_pii_sanitization.py: lab_unit_id = 1
tests/fixtures/test_security_fixtures.py: lab_unit_id == 1 (Hospital A)
tests/fixtures/test_security_fixtures.py: lab_unit_id == 4 (Hospital B, but gets Lab B1!)

# Mock data uses high IDs:
tests/unit/utils/test_image_search.py: lab_unit_id = 20
```

---

## Execution Order

```
1. pytest loads
2. conftest.py loads (pytest_plugins: fixtures.security, fixtures.metadata)
3. test_engine (session) → Creates/drops tables
4. seed_test_database (session, autouse) → Creates 4 lab units ⚠️
5. test_hospitals (session) → Skips if exist
6. test_lab_units (session) → Tries to create 6, skips id=3
7. core_test_data (session) → Same as #6
8. [For EACH test]
   └─ db_session (function) → Transaction with rollback
```

---

## Recommended Solutions

### Option A: Fix seed_database (RECOMMENDED)

**Update `fixtures/seed_database.py` to create 6 lab units:**

```python
# Change from:
lab_units_data = [
    {'id': 1, 'name': 'Lab A1', 'hospital_id': 1},
    {'id': 2, 'name': 'Lab A2', 'hospital_id': 1},
    {'id': 3, 'name': 'Lab B1', 'hospital_id': 2},  # ❌ Wrong ID
    {'id': 4, 'name': 'Lab B2', 'hospital_id': 2}
]

# To:
lab_units_data = [
    {'id': 1, 'name': 'Lab A1', 'hospital_id': 1},
    {'id': 2, 'name': 'Lab A2', 'hospital_id': 1},
    {'id': 3, 'name': 'Lab A3', 'hospital_id': 1},  # ✅ Fixed
    {'id': 4, 'name': 'Lab B1', 'hospital_id': 2},  # ✅ Fixed
    {'id': 5, 'name': 'Lab B2', 'hospital_id': 2},  # ✅ New
    {'id': 6, 'name': 'Lab B3', 'hospital_id': 2}   # ✅ New
]
```

**Impact:** May break tests that assume id=3 is Hospital B. Need to audit all tests.

### Option B: Disable seed_database autouse

**In `fixtures/seed_database.py`:**

```python
@pytest.fixture(scope="session")  # Remove autouse=True
def seed_test_database(test_engine):
    # ...
```

**Then** update tests that need it to explicitly request the fixture.

**Impact:** Requires updating many tests, but more flexible.

### Option C: Consolidate to Single Source of Truth (CLEANEST)

1. Keep `seed_test_database` as the single source for core entities
2. Remove duplicate fixtures from `security.py` (`test_hospitals`, `test_lab_units`)
3. Update `security.py` fixtures to use `seed_test_database` data
4. Update all tests to use consistent fixture names

**Impact:** Most work upfront, but prevents future conflicts.

---

## Fixture Dependencies Graph

```
test_engine (session)
    │
    ├─── seed_test_database (session, autouse)
    │      └── Creates: roles, diseases, hospitals, lab_units, users
    │
    ├─── core_test_data (session)
    │      └── CoreEntityFactory.setup_core_entities()
    │
    └─── [Each test]
           └── db_session (function, transaction rollback)
                ├── Uses session-scoped data
                └── Creates test-specific data
```

---

## Migration Checklist

If implementing **Option A** (fix seed_database):

- [ ] Update `fixtures/seed_database.py` with correct lab unit IDs
- [ ] Run all tests to identify broken assumptions
- [ ] Fix tests that assume id=3 is Hospital B
- [ ] Update documentation with correct ID assignments
- [ ] Run full test suite to verify

If implementing **Option B** (disable autouse):

- [ ] Remove `autouse=True` from `seed_test_database`
- [ ] Identify tests that depend on seeded data
- [ ] Add `seed_test_database` to fixture dependencies
- [ ] Run full test suite

If implementing **Option C** (consolidate):

- [ ] Audit all fixture files for duplicates
- [ ] Remove `test_hospitals`, `test_lab_units` from security.py
- [ ] Update security.py fixtures to reference seed data
- [ ] Update all tests to use consolidated fixtures
- [ ] Document fixture architecture
- [ ] Run full test suite

---

## Quick Reference

### Hospital Assignments (After Fix)

| Lab Unit ID | Name | Hospital |
|-------------|------|----------|
| 1 | Lab A1 | Hospital A (id=1) |
| 2 | Lab A2 | Hospital A (id=1) |
| 3 | Lab A3 | Hospital A (id=1) |
| 4 | Lab B1 | Hospital B (id=2) |
| 5 | Lab B2 | Hospital B (id=2) |
| 6 | Lab B3 | Hospital B (id=2) |

### User Types

| Username | Hospital ID | is_master_admin | Lab Units |
|----------|-------------|-----------------|-----------|
| master_admin | NULL | True | All |
| site_admin_a | 1 | False | Hospital A labs |
| site_admin_b | 2 | False | Hospital B labs |
| ophth_a | 1 | False | lab_a1 |
| ophth_cross | NULL | False | lab_a1 (can grade in both) |
