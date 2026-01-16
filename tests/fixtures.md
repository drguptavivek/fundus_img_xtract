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

---

## Workflow Fixtures

The `tests/fixtures/workflow.py` module provides comprehensive fixtures for testing the complete grading pipeline:
**Encounters → Images → Tasks → Grades → Consensus → Review**

### Disease Grading Fixtures

| Fixture | Purpose |
|---------|---------|
| `disease_grading_glaucoma_mild` | Mild Glaucoma grading (display_order=1) |
| `disease_grading_glaucoma_moderate` | Moderate Glaucoma grading (display_order=2) |
| `disease_grading_glaucoma_severe` | Severe Glaucoma grading (display_order=3) |
| `disease_grading_dr_no_dr` | No DR grading |
| `disease_grading_dr_mild` | Mild NPDR grading |
| `disease_grading_dr_severe` | Severe NPDR grading |
| `disease_grading_with_features` | Grading with GradingsFeatures (for testing selected features) |

### AI Model Fixtures

| Fixture | Purpose |
|---------|---------|
| `ai_model_glaucoma_v1` | GlaucomaNet v1.0 AI model |
| `ai_model_dr_v2` | DRNet v2.0 AI model |

### Grade Creation Factory Fixtures

These are callable fixtures that return functions to create grades:

| Fixture | Purpose | Usage |
|---------|---------|-------|
| `create_resident_grade` | Creates a resident (role_slot='resident') grade | `grade = create_resident_grade(task, user, grading)` |
| `create_resident2_grade` | Creates a resident2 (role_slot='resident2') grade | `grade = create_resident2_grade(task, user, grading)` |
| `create_arbitrator_grade` | Creates an arbitrator (role_slot='arbitrator') grade | `grade = create_arbitrator_grade(task, user, grading)` |
| `create_ai_grade` | Creates an AI (role_slot='ai') grade | `grade = create_ai_grade(task, ai_model, grading)` |
| `create_review_grade` | Creates a review grade and updates original grade | `grade = create_review_grade(task, user, original_grade, approved=True)` |

**Example Usage:**
```python
def test_grading(db_session, create_resident_grade, disease_grading_glaucoma_mild):
    grade = create_resident_grade(
        task=task,
        user=grader,
        grading=disease_grading_glaucoma_mild,
        comment="Patient shows early signs",
        time_taken=120.0,
    )
    assert grade.role_slot == 'resident'
    assert grade.grade_name == 'Mild'
```

### Consensus Fixture

| Fixture | Purpose | Usage |
|---------|---------|-------|
| `create_consensus` | Creates a Consensus record for a task | `consensus = create_consensus(task, final_grading, method='match')` |

**Consensus Methods:**
- `match`: Auto-consensus when residents agree
- `adjudication`: Arbitrator decides
- `task_review`: Manual review

### Complete Workflow Scenario Fixtures

| Fixture | Purpose | Returns |
|---------|---------|---------|
| `dual_grading_scenario` | Creates resident + resident2 grades, optional consensus | `dict` with task, grades, consensus |
| `arbitration_scenario` | Creates full arbitration workflow (disagreeing grades + arbitrator + consensus) | `dict` with all grades and consensus |
| `ai_grading_scenario` | Creates AI grade + human review | `dict` with ai_grade and review_grade |
| `complete_grading_workflow` | Creates full chain: encounter → files → tasks → grades → consensus | `dict` with encounter, files, tasks, grades |

**Example - Dual Grading Scenario:**
```python
def test_dual_grading(
    db_session,
    TestDataFactory,
    dual_grading_scenario,
    ophthalmologist_hospital_a,
    disease_grading_glaucoma_mild,
):
    # Create task
    task = TestDataFactory.create_grading_task(
        db_session, lab_unit_id=1, disease_id=1
    )

    # Create dual grading scenario
    scenario = dual_grading_scenario(
        task=task,
        resident=ophthalmologist_hospital_a,
        resident2=other_grader,
        resident_grading=disease_grading_glaucoma_mild,
        create_consensus_if_match=True,
    )

    assert scenario['resident_grade'].role_slot == 'resident'
    assert scenario['resident2_grade'].role_slot == 'resident2'
    assert scenario['consensus'] is not None
    assert scenario['consensus'].method == 'match'
```

### Pre-Configured Quick Scenario Fixtures

These provide ready-to-use grading scenarios without setup:

| Fixture | Purpose | Returns |
|---------|---------|---------|
| `sample_grading_task_with_grades` | Ready-to-use task with resident + resident2 grades | `dict` with task, encounter, file, grades |
| `sample_task_with_consensus` | Ready-to-use task with consensus | Same as above + consensus |
| `sample_ai_grading_with_review` | Ready-to-use AI grading + review | `dict` with task, ai_grade, review_grade |

**Example - Using Quick Scenario:**
```python
def test_with_pre_configured_scenario(sample_task_with_consensus):
    task = sample_task_with_consensus['task']
    consensus = sample_task_with_consensus['consensus']

    assert task.state == 'final'
    assert consensus.method == 'match'
```

---

## Workflow Fixture Dependencies

```
db_session (function)
    │
    ├─── DiseaseGrading fixtures (function-scoped)
    │      ├── disease_grading_glaucoma_mild
    │      ├── disease_grading_glaucoma_moderate
    │      ├── disease_grading_dr_mild
    │      └── ... (all grading fixtures)
    │
    ├─── AIModel fixtures (function-scoped)
    │      ├── ai_model_glaucoma_v1
    │      └── ai_model_dr_v2
    │
    ├─── Grade creation factories (function-scoped)
    │      ├── create_resident_grade
    │      ├── create_resident2_grade
    │      ├── create_arbitrator_grade
    │      ├── create_ai_grade
    │      └── create_review_grade
    │
    ├─── Consensus factory (function-scoped)
    │      └── create_consensus
    │
    └─── Scenario fixtures (function-scoped)
           ├── dual_grading_scenario
           ├── arbitration_scenario
           ├── ai_grading_scenario
           ├── complete_grading_workflow
           └── ... (pre-configured scenarios)
```

---

## Complete Workflow Example

```python
def test_complete_grading_pipeline(
    db_session,
    complete_grading_workflow,
    ophthalmologist_hospital_a,
    disease_grading_glaucoma_moderate,
):
    # Create complete workflow from encounter to consensus
    workflow = complete_grading_workflow(
        lab_unit_id=1,
        disease_id=1,  # Glaucoma
        resident=ophthalmologist_hospital_a,
        resident2=other_grader,
        grading=disease_grading_glaucoma_moderate,
        num_images=3,
    )

    # Verify encounter
    encounter = workflow['encounter']
    assert encounter.patient_id.startswith('TEST_PATIENT_')

    # Verify files were created
    files = workflow['files']
    assert len(files) == 3

    # Verify tasks and grades
    for grade_data in workflow['grades']:
        task = grade_data['task']
        assert task.state == 'final'

        resident_grade = grade_data['resident_grade']
        assert resident_grade.role_slot == 'resident'

        consensus = grade_data['consensus']
        assert consensus.method == 'match'
```

---

## Grade Model Fields Reference

When creating grades, the following fields are automatically populated:

| Field | Source | Description |
|-------|--------|-------------|
| `task_id` | Parameter | GradingTask ID |
| `grader_user_id` | Parameter | User ID of grader |
| `role_slot` | Fixture | 'resident', 'resident2', 'arbitrator', 'ai', or 'review' |
| `disease_grading_id` | Parameter | DiseaseGrading ID |
| `comment` | Optional parameter | Grader's comment |
| `selected_features_json` | Optional parameter | JSON string of selected features |
| `time_taken` | Optional parameter (default varies) | Time in seconds |
| `start_time` | Auto-generated | When grading started |
| `disease_name` | Auto-populated | Denormalized from Disease |
| `grade_name` | Auto-populated | Denormalized from DiseaseGrading.impression |
| `grade_description` | Auto-populated | Denormalized from DiseaseGrading.guidelines |
| `ai_model_id` | AI grades only | AIModel ID |
| `ai_model_name` | AI grades only | Denormalized from AIModel |
| `ai_model_version` | AI grades only | Denormalized from AIModel |

---

## Consensus Model Fields Reference

| Field | Source | Description |
|-------|--------|-------------|
| `task_id` | Parameter | GradingTask ID (unique) |
| `final_disease_grading_id` | Parameter | Final agreed DiseaseGrading ID |
| `method` | Parameter | 'match', 'adjudication', or 'task_review' |
| `decided_by_user_id` | Optional parameter | User ID of decider (arbitrator) |
| `decided_at` | Auto-generated | When consensus was reached |
| `final_disease_name` | Auto-populated | Denormalized from Disease |
| `final_grade_name` | Auto-populated | Denormalized from DiseaseGrading.impression |
| `final_grade_description` | Auto-populated | Denormalized from DiseaseGrading.guidelines |

---

## Test Factory Helpers

The workflow fixtures work with existing test factories:

### TestDataFactory (tests/helpers/test_factories.py)
- `create_zip_file()` - Creates ZipFile instance
- `create_patient_encounter()` - Creates PatientEncounters with ZipFile
- `create_encounter_file()` - Creates EncounterFile
- `create_direct_image_upload()` - Creates DirectImageUpload
- `create_grading_task()` - Creates GradingTask (enforces encounter_file_id XOR direct_image_upload_id)

### UserFactory (tests/helpers/factories.py)
- `create_admin()` - Creates admin user
- `create_ophthalmologist()` - Creates ophthalmologist with lab units
- `create_by_role()` - Generic user creation by role
- `create_grader_with_slots()` - Creates grader with specific disease slots
- `create_grader_pool()` - Creates 4 residents + 2 arbitrators

### CoreEntityFactory (tests/helpers/factories.py)
- `setup_core_entities()` - Queries seeded entities (hospitals, lab units, diseases, cameras, areas)

### ImageFactory (tests/helpers/factories.py)
- `create_direct_upload()` - Creates DirectImageUpload with all required fields

---

## Best Practices

1. **Use factory fixtures for flexibility**: Instead of pre-configured scenarios, use `create_*` factory fixtures when you need custom parameters
2. **Use pre-configured scenarios for speed**: When testing doesn't require specific values, use `sample_*` fixtures
3. **Always merge session-scoped fixtures**: When using `seed_test_database` users, merge into function-scoped session
4. **Commit before route requests**: When making HTTP requests, commit test data first so route handlers can see it
5. **Use complete_workflow for integration tests**: Tests full pipeline from ingestion to consensus
6. **Use individual fixtures for unit tests**: Tests specific components in isolation
