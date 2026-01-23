---
title: Pre-graded Upload - Task and Grade Association
description: How tasks are created and grades are imported for pre-graded datasets.
last_updated: 2026-01-23
---
# Pre-graded Upload - Task and Grade Association

This document details how grading tasks are created for pre-graded images and how grades from Excel files are associated with those tasks.

## Overview

Pre-graded uploads follow a two-phase workflow:
1. **Phase 1**: Image upload with automatic task creation
2. **Phase 2**: Grade import from Excel with automatic consensus calculation

## Phase 1: Image Upload and Task Creation

### Automatic Task Creation

When images are uploaded via `/direct/pregraded`:

1. **Image Storage**: Each image is saved with `is_pregraded = True` flag
2. **Auto-Verification**: System automatically creates `DirectImageVerify` record with `verified_status = 'verified'`
3. **Immediate Task Creation**: For each image, system calls `ensure_task(uuid, disease_id, db)`:
   ```python
   # Code: pregraded.py:297
   ensure_task(uuid_value, disease_id, db_session)
   ```
4. **Task State**: Created with `state = 'pending'`
5. **Task Association**: Linked to `DirectImageUpload` via `direct_image_upload_id`

**Key Difference from Regular Uploads**: 
- Regular uploads: Tasks created AFTER manual verification
- Pre-graded uploads: Tasks created IMMEDIATELY during upload

---

## Phase 2: Grade Import from Excel

### Excel File Structure

Excel file must contain columns for:
- **Filename**: Must match uploaded image filename
- **Grade**: Disease-specific grade value (e.g., "Severe NPDR", "Moderate")
- **Hospital**: Must match the hospital selected during image upload
- **Lab Unit**: Must match the lab unit selected during image upload
- **Disease**: Must match the disease selected during image upload

### Grade Import Process

#### Step 1: Image Matching

System matches Excel rows to uploaded images:
```python
# Matching criteria (pregraded_grades.py):
# - filename
# - hospital_id
# - lab_unit_id  
# - disease_id
```

**If no match found**: Row is skipped with error "Image not found"

#### Step 2: Task Lookup

For each matched image, system finds the associated grading task:
```python
# Code: pregraded_grades.py:568-573
task = db_session.execute(
    select(GradingTask).where(
        GradingTask.direct_image_upload_id == upload.id,
        GradingTask.disease_id == pending.disease_id,
    )
).scalar_one_or_none()
```

**If task not found**: Raises error "Associated grading task not found"

#### Step 3: Grade Application

System creates/updates `Grade` record with:
- `task_id`: Links to the grading task
- `grader_user_id`: User ID of the grader (from Excel or selected grader)
- `role_slot`: One of `'resident'`, `'resident2'`, or `'ai'`
- `disease_grading_id`: Resolved from Excel grade text
- `comment`: Optional remarks from Excel

```python
# Code: pregraded_grades.py:586-597
_apply_grade(
    db_session,
    task=task,
    grade_id=grade_id,
    grader_user_id=pending.grader_user_id,
    role=pending.role,  # 'resident', 'resident2', or 'ai'
    remarks=final_comment,
    ...
)
```

#### Step 4: State Update and Consensus

**For Resident or Resident2 grades**:
```python
# Code: pregraded_grades.py:599-602
if pending.role in (ROLE_RESIDENT, ROLE_RESIDENT2):
    update_task_state_based_on_grades(task.id, db=db_session)
    if pending.role == ROLE_RESIDENT2:
        create_or_update_consensus(task.id, db=db_session)
```

**State transitions**:
- **Resident grade only**: Task state → `'resident_done'`
- **Resident + Resident2 (match)**: Task state → `'final'`, Consensus created with `method = 'match'`
- **Resident + Resident2 (differ)**: Task state → `'arbitration'`

**For AI grades**:
- No automatic state update
- No automatic consensus creation
- Grade is stored for reference/comparison

---

## Handling Missing Grades

### Scenario 1: Only Resident Grade Imported

**Result**:
- Task state: `'resident_done'`
- Awaits Resident2 grade (can be added via Excel or manual grading)
- No consensus created yet

**Next Steps**:
- User can import another Excel with Resident2 grades
- OR Resident2 can manually grade via grading interface

### Scenario 2: Only Resident2 Grade Imported

**Result**:
- Task state: `'resident2_done'`
- Missing Resident grade
- **Incomplete workflow** - both grades needed for consensus

**Issue**: System expects Resident grade first in normal workflow

### Scenario 3: Only AI Grade Imported

**Result**:
- Task state: Remains `'pending'`
- AI grade stored but doesn't trigger state changes
- Task still available for Resident grading

**Purpose**: AI grades are for comparison/reference, not workflow progression

### Scenario 4: Resident + Resident2 Grades (Different)

**Result**:
- Task state: `'arbitration'`
- Awaits Arbitrator grade
- No consensus created yet

**Next Steps**:
- Arbitrator must grade manually via grading interface
- OR import Excel with Arbitrator grade (if supported)

### Scenario 5: Missing Arbitrator Grade

**When**: Resident and Resident2 grades differ, task in `'arbitration'` state

**Result**:
- Task remains in `'arbitration'` state
- Task appears in Arbitrator's dashboard
- No consensus until Arbitrator grades

**Resolution**:
- Arbitrator must grade manually via grading interface
- System does NOT auto-resolve disagreements

---

## Grade Upsert Behavior

### Creating New Grade

If no grade exists for the role slot:
```python
new_grade = Grade(
    task_id=task.id,
    grader_user_id=grader_user_id,
    role_slot=role,  # 'resident', 'resident2', 'arbitrator', 'ai'
    disease_grading_id=grade_id,
    comment=remarks,
    ...
)
```

### Updating Existing Grade

If grade already exists for the role slot:
```python
existing_grade.disease_grading_id = grade_id
existing_grade.comment = remarks
existing_grade.updated_at = utcnow()
```

**Important**: Each role slot can have only ONE grade per task. Importing again for the same role overwrites the previous grade.

---

## Consensus Logic for Pre-graded Imports

### Automatic Consensus Creation

**Triggered when**: Resident2 grade is imported (line 602)

**Consensus conditions**:

1. **Match** (`method = 'match'`):
   - Resident grade exists
   - Resident2 grade exists
   - `resident.disease_grading_id == resident2.disease_grading_id`
   - Task state → `'final'`
   - `decided_by_user_id = None` (system decision)

2. **No Match** (requires arbitration):
   - Resident grade exists
   - Resident2 grade exists
   - Grades differ
   - Task state → `'arbitration'`
   - No consensus created yet

3. **Arbitrator Decision** (`method = 'adjudication'`):
   - Arbitrator grade exists
   - Task state → `'final'`
   - `decided_by_user_id = arbitrator_user_id`

---

## State Machine for Pre-graded Tasks

```
Initial: pending (task created during image upload)
    ↓
Resident grade imported → resident_done
    ↓
Resident2 grade imported → Check consensus
    ↓
    ├─→ Grades match → final (consensus: match)
    └─→ Grades differ → arbitration
        ↓
        Arbitrator grades → final (consensus: adjudication)
```

---

## Error Handling

### Common Errors

| Error | Cause | Resolution |
|-------|-------|------------|
| "Image not found" | Filename/hospital/lab/disease mismatch | Verify Excel data matches upload parameters |
| "Associated grading task not found" | Task creation failed during upload | Re-upload image or manually create task |
| "Grade text not recognized" | Excel grade doesn't match database | Use grade mapping UI to map values |
| "ensure_task failed" | Verification or permission issue | Check image verification status |

### Partial Import Handling

If Excel contains 100 rows:
- 80 successful → Creates 80 grades
- 20 failed → Logged as errors in `JobItem` table
- Job status: `'error'` with message "20 of 100 files encountered issues"

**Important**: Successful rows are committed even if some rows fail

---

## Key Differences from Manual Grading

| Aspect | Manual Grading | Pre-graded Import |
|--------|---------------|-------------------|
| Task Creation | After verification | During image upload |
| Verification | Manual review required | Automatic |
| Grade Entry | One at a time via UI | Bulk via Excel |
| Consensus | Calculated after each grade | Calculated after Resident2 import |
| State Updates | Immediate after submission | Batch after Excel processing |
| Revision | Via revision interface | Re-import Excel (overwrites) |

---

## Best Practices

1. **Import Order**: Import Resident grades first, then Resident2 grades
2. **Batch Size**: Process Excel files in manageable batches (recommended: <1000 rows)
3. **Grade Mapping**: Pre-map grade text values before bulk import
4. **Verification**: Review import summary for errors before proceeding
5. **Consensus Check**: Verify consensus was created for matching grades
6. **Arbitration**: Manually grade tasks that went to arbitration

---

---

## Admin Tools for Task State Fixes

### Problem: Tasks Stuck Without Resident Grade

**Scenario**: Tasks in `'resident2_done'` state but missing Resident grade

**Cause**: 
- Pre-graded Excel import with only Resident2 grades
- Data migration or import errors
- Manual database manipulation

**Impact**:
- Task cannot progress to consensus
- Workflow stuck - cannot reach `'final'` or `'arbitration'` state
- Task invisible to Resident graders (they only see `'pending'` tasks)

### Solution 1: Grading State Inconsistencies Tool

**Route**: `/admin/grading_state_inconsistencies`  
**File**: `admin/grading_state_inconsistencies.py`  
**Access**: Requires `admin` role

#### Detection Logic

Finds tasks where:
1. Task state = `'resident2_done'`
2. Resident2 grade exists (`role_slot = 'resident2'`)
3. Resident grade missing (`role_slot = 'resident'` not found)

```python
# Code: grading_state_inconsistencies.py:44-67
resident2_exists = (
    db.query(Grade.task_id)
    .filter(and_(Grade.task_id == GradingTask.id, Grade.role_slot == "resident2"))
)
resident_missing = ~exists().where(
    and_(Grade.task_id == GradingTask.id, Grade.role_slot == "resident")
)
```

#### Remediation Process

**Admin Action**: Select tasks and click "Reset to Pending"

**What Happens**:
```python
# Code: grading_state_inconsistencies.py:30-38
db.query(GradingTask)
    .filter(
        GradingTask.id.in_(selected_task_ids),
        GradingTask.state == "resident2_done",
    )
    .update({GradingTask.state: "pending"}, synchronize_session=False)
```

**Result**:
- Task state changed from `'resident2_done'` → `'pending'`
- Task now visible to Resident graders
- Resident2 grade preserved (not deleted)

**After Resident Grades**:
- System runs `update_task_state_based_on_grades()`
- If Resident + Resident2 match → state becomes `'final'`, consensus created
- If Resident + Resident2 differ → state becomes `'arbitration'`

---

### Solution 2: Task Backfill Tool

**Route**: `/admin/task_backfill`  
**File**: `admin/task_backfill.py`  
**Access**: Requires `admin` or `local_admin` role

#### Purpose

Creates missing grading tasks for verified images that should have tasks but don't.

**Common Causes**:
- `ensure_task()` failed during verification
- Database transaction rollback
- System errors during task creation
- Manual image verification without task creation

#### Detection Logic

**File**: `utils/task_backfill.py`

Finds images where:
1. Image is verified (`DirectImageVerify.verified_status = 'verified'` OR `PatientEncounters.dr_verified_status = 'verified'`)
2. No corresponding `GradingTask` exists for the image×disease combination

```python
# Pseudo-code from task_backfill.py
missing_tasks = (
    SELECT images WHERE verified = true
    AND NOT EXISTS (
        SELECT 1 FROM grading_tasks 
        WHERE grading_tasks.image_id = images.id
        AND grading_tasks.disease_id = target_disease_id
    )
)
```

#### Backfill Process

**Admin Action**: 
1. View missing task counts by disease and lab unit
2. Set limit (number of tasks to create)
3. Click "Run Backfill"

**What Happens**:
```python
# Code: task_backfill.py:83-95
job = TaskBackfillJob(
    status="queued",
    requested_limit=limit,
    created_by_id=current_user.id,
    hospital_id=current_user.hospital_id,
    allowed_lab_unit_ids=json.dumps(sorted(allowed_lab_unit_ids)),
)
db.add(job)
db.commit()

enqueue_task_backfill(current_app, job_id)
```

**Background Processing**:
1. Job status: `'queued'` → `'running'`
2. For each missing task (up to limit):
   - Call `ensure_task(image_uuid, disease_id, db)`
   - Create `GradingTask` with `state = 'pending'`
3. Job status: `'running'` → `'completed'`
4. Job records: `created_count`, `error_count`, `processed_count`

**Safety Features**:
- Only one backfill job can run at a time
- Lab unit scoping (admins only see their hospital's tasks)
- Limit parameter prevents overwhelming the system
- Job history tracked in `TaskBackfillJob` table

---

## Comparison: State Inconsistencies vs Task Backfill

| Aspect | State Inconsistencies | Task Backfill |
|--------|----------------------|---------------|
| **Problem** | Tasks exist but in wrong state | Tasks don't exist at all |
| **Detection** | Resident2 grade without Resident grade | Verified images without tasks |
| **Solution** | Reset task state to `'pending'` | Create missing tasks |
| **Preserves** | All existing grades | N/A (no grades exist yet) |
| **Access** | `admin` only | `admin` or `local_admin` |
| **Processing** | Synchronous (immediate) | Asynchronous (background job) |
| **Scope** | Specific inconsistent tasks | All missing tasks (up to limit) |

---

## Best Practices

### When to Use State Inconsistencies Tool

1. **After pre-graded import** with only Resident2 grades
2. **After data migration** that created incomplete grade sets
3. **When tasks are stuck** in `'resident2_done'` state
4. **Before running reports** to ensure accurate task state counts

### When to Use Task Backfill Tool

1. **After system errors** during verification workflow
2. **After manual database operations** that bypassed `ensure_task()`
3. **When KPIs show** verified images > grading tasks
4. **During system recovery** after database issues

### Verification After Fixes

**For State Inconsistencies**:
```sql
-- Verify no tasks stuck in resident2_done without Resident grade
SELECT COUNT(*) FROM grading_tasks gt
WHERE gt.state = 'resident2_done'
AND EXISTS (SELECT 1 FROM grades WHERE task_id = gt.id AND role_slot = 'resident2')
AND NOT EXISTS (SELECT 1 FROM grades WHERE task_id = gt.id AND role_slot = 'resident');
-- Should return 0
```

**For Task Backfill**:
```sql
-- Verify all verified images have tasks
SELECT COUNT(*) FROM direct_image_uploads diu
JOIN direct_image_verify div ON div.image_upload_id = diu.id
WHERE div.verified_status = 'verified'
AND NOT EXISTS (
    SELECT 1 FROM grading_tasks 
    WHERE direct_image_upload_id = diu.id
);
-- Should return 0 (or low number if backfill limit was set)
```

---

## Code References

- **Task Creation**: `direct_uploads/pregraded.py:297`
- **Grade Import**: `direct_uploads/pregraded_grades.py:530-643`
- **Grade Application**: `direct_uploads/pregraded_grades.py:586-597`
- **State Update**: `direct_uploads/pregraded_grades.py:600`
- **Consensus Creation**: `direct_uploads/pregraded_grades.py:602`
- **Consensus Logic**: `utils/dualGradingConsensusUtils.py:97-116`
