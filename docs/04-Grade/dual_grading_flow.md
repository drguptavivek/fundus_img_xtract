# Dual Grading Implementation Details

## Overview
This document provides detailed implementation logic for the dual grading system. For a high-level overview, see [Dual Grading System Documentation](../04-Grade/dual_grading.md).

## Core Implementation Files

### Main Routes
- **`dual_grading.py`**: Main route handlers for grading workflow
- **`dashboard.py`**: Dashboard with statistics and task assignment
- **`start_grading.py`**: Entry point for initiating grading sessions

### Utility Modules
- **`dualGradingEligibility.py`**: User eligibility checks
- **`dualGradingGetNextTasks.py`**: Task assignment logic
- **`dualGradingFetchDetailUtils.py`**: Data fetching utilities
- **`dualGradingConsensusUtils.py`**: Consensus creation and management
- **`dualGradingRevisionUtils.py`**: Revision logic and restrictions
- **`dualGradingStuckTaskCleanup.py`**: Task tracking and cleanup

## Detailed Logic Implementation

### User Eligibility Checks

#### `get_user_eligibility_for_task(db, user_id, task_id, role_slot)`
Performs comprehensive eligibility verification:
1. Validates user exists and has appropriate role requirements
2. Verifies permissions for disease and lab unit via `UserDiseaseUnitRole` table
3. Checks role-specific requirements:
   - For 'resident': requires `can_grade_resident == True`
   - For 'resident2': requires `can_grade_resident2 == True`
   - For 'arbitrator': requires `can_arbitrate == True`
4. Returns boolean eligibility with detailed message

#### `_get_user_eligible_lab_unit_ids(db, user_id, disease_id, role_slot)`
Returns lab units user can grade for:
- Admin users: All lab units
- Non-admin users: Filtered by `UserDiseaseUnitRole` permissions
- Checks active permissions matching the role slot

### Task Assignment Logic

#### Task Filtering (`_get_filtered_tasks`)
Filters tasks based on:
1. Eligible lab units for user's role and disease
2. Disease ID matching
3. Appropriate task state for role:
   - Residents: `state == "pending"`
   - Resident2: `state == "resident_done"`
   - Arbitrators: `state == "arbitration"`
4. Excludes tasks graded by user in last 4 weeks

#### Random Task Selection
- Uses `random.choice()` for unbiased task distribution
- Implements retry logic (up to 3 attempts) if no tasks available
- Returns helpful message when no eligible tasks found

### Grade Submission Flow

#### State Validation at Submission
Prevents race conditions by revalidating task state:
- Residents: Can grade `pending` or `resident_done` (for revisions)
- Resident2: Can grade `resident_done`, `resident2_done`, or `arbitration` (for revisions)
- Arbitrators: Can grade `arbitration` or `final` (for eligible revisions)

#### Grade Upsert Logic
```python
if existing_grade:
    # Update existing grade
    existing_grade.disease_grading_id = label_id
    existing_grade.comment = comment
    existing_grade.time_taken = time_taken
    # Update denormalized fields
else:
    # Create new grade
    new_grade = Grade(
        task_id=task.id,
        grader_user_id=current_user.id,
        role_slot=slot,
        disease_grading_id=label_id,
        comment=comment,
        time_taken=time_taken
    )
```

#### Task State Updates
Called after grade submission:
```python
update_task_state_based_on_grades(task.id, db)
create_or_update_consensus(task.id, db)
```

### Revision Implementation Details

#### Time-Based Restrictions
- **Revision window**: 12 hours for Resident, Resident2, and Arbitrator grades
- The same boundary is used by dashboard actions and revision submission checks
- Time windows stored in UTC for consistency

#### Revision Eligibility Functions

##### `is_user_eligible_for_revision(db, user_id, task_id, slot_type, grade)`
Returns dict with:
- `eligible`: Boolean eligibility status
- `message`: Detailed explanation
- `is_recent`: For arbitrators (within revision window)

##### `is_arbitrator_revision_allowed(db, user_id, task_id, slot)`
Used in `dual_grading_submit()` to check if finalized task can be modified:
- Only applies to arbitrator submissions
- Verifies existing arbitrator grade
- Checks time constraint

### Task Tracker Implementation

#### Tracker Model
```python
class TaskTracker(Base):
    __tablename__ = "task_tracker"
    task_id: Mapped[int] = mapped_column(ForeignKey('grading_tasks.id'), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    role_slot: Mapped[str] = mapped_column(String(20), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

#### Lifecycle Management
1. **Creation**: When user accesses new task (not revision)
2. **Cleanup**: Immediately after successful grade submission
3. **Background cleanup**: Every 30 minutes for stuck tasks (>60 minutes)

#### Cleanup Function
```python
def cleanup_task_tracker(task_id, user_id, role_slot, db=None):
    """Remove tracker record after successful submission"""
    with transaction_scope(db) as session:
        tracker = session.query(TaskTracker).filter(
            TaskTracker.task_id == task_id,
            TaskTracker.user_id == user_id,
            TaskTracker.role_slot == role_slot
        ).first()
        if tracker:
            session.delete(tracker)
```

### Consensus Creation Logic

#### `create_or_update_consensus(task_id, db)`
1. Checks if consensus already exists
2. Determines consensus method:
   - **Match**: Resident and resident2 grades identical
   - **Adjudication**: Arbitrator decision
3. Creates consensus record with final grade
4. Updates task state to `final`

#### Consensus Validation
- Only creates consensus for tasks in appropriate states
- Validates required grades are present
- Ensures single consensus per task

### Error Handling Patterns

#### Transaction Management
All operations use `transaction_scope()` context manager:
```python
with transaction_scope() as db:
    # Database operations
    # Automatic commit on success, rollback on exception
```

#### Notification System
Sends notifications to admins for:
- Missing disease gradings
- Missing task images
- Invalid access attempts

#### Logging Strategy
- Dedicated `grades_logger` for all grading activities
- Structured logging with IP, user ID, task details
- Exception logging with full stack traces

### Performance Considerations

#### Query Optimization
- Uses `selectinload` and `joinedload` for efficient data fetching
- Fetches related data in single queries
- Implements proper indexing on foreign keys

#### Session Management
- Proper session cleanup after operations
- Session passed to utility functions for transaction consistency
- Avoids session leaks with context managers

### Security Implementation

#### Input Validation
```python
if not task_id or not isinstance(task_id, int) or task_id <= 0:
    flash("Invalid task ID.", "danger")
    return redirect(url_for("grading.index"))
```

#### Access Control Checks
- Role verification at route level
- Task-specific eligibility checks
- Lab unit permission validation

#### CSRF Protection
- All forms use `_forms.html` template with CSRF token
- Token validation on all POST requests

## Known Issues and Fixes

### Task Tracker Cleanup Bug (FIXED)
- **Issue**: Tracker records weren't cleaned up after successful submissions
- **Impact**: Tasks remained marked "in progress" preventing reassignment
- **Fix**: Added proper cleanup call in `dual_grading_submit()` after grade submission

### Variable Naming Collision (FIXED)
- **Issue**: `is_arbitrator_revision_allowed` function overwritten by boolean variable
- **Impact**: "'bool' object is not callable" error
- **Fix**: Renamed boolean variable to `arbitrator_revision_allowed`

## Testing Recommendations

### Unit Tests
1. Test eligibility check functions with various scenarios
2. Test task state transitions
3. Test consensus creation logic
4. Test revision time restrictions

### Integration Tests
1. Test complete grading workflow
2. Test concurrent user access
3. Test task tracker cleanup
4. Test error handling scenarios

### Edge Cases to Test
1. Arbitrator revising finalized task
2. User attempting to grade ineligible task
3. Task state changes during grading
4. Network timeouts during submission
