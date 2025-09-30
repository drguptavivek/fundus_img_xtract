# Dual Grading Flow and Revision Logic

## Overview
This document outlines the logic checks and flows for grading and revision of grades in the dual grading system, which involves three user roles: resident (medical resident), faculty (ophthalmologist), and arbitrator (ophthalmologist with arbitration privileges).

## User Role Eligibility Checks

### Role-Based Permissions
- **Resident**: Must have the 'resident' role, can only grade as 'resident'
- **Faculty**: Must have the 'ophthalmologist' role, can grade as 'faculty'
- **Arbitrator**: Must have the 'ophthalmologist' role, can grade as 'arbitrator'

### Task-Specific Eligibility Check
The function `get_user_eligibility_for_task(db, user_id, task_id, role_slot)` performs the following checks:
1. Validates the user exists and has appropriate role requirements
2. Verifies the user has permissions for the specified disease and lab unit via `UserDiseaseUnitRole` table
3. Confirms the user has the required role (resident vs ophthalmologist) based on the requested role_slot
4. Checks the `UserDiseaseUnitRole` record for appropriate permissions:
   - For 'resident': checks `can_grade_resident == True`
   - For 'faculty': checks `can_grade_faculty == True`
   - For 'arbitrator': checks `can_arbitrate == True`

### Lab Unit Eligibility
The function `_get_user_eligible_lab_unit_ids(db, user_id, disease_id, role_slot)`:
- Returns all lab units for admin users
- Otherwise filters by user's role permissions for the specific disease and role slot
- For non-admins, checks the `UserDiseaseUnitRole` table for active permissions matching the role slot

## Task Assignment Logic

### Getting Next Eligible Tasks
Different functions handle task assignment for different roles:
- `get_next_eligible_resident_task(user_id, disease_id, lab_unit_id)`
- `get_next_eligible_faculty_task(user_id, disease_id, lab_unit_id)`
- `get_next_eligible_arbitrator_task(user_id, disease_id, lab_unit_id)`

These functions:
1. Get eligible lab units for the user's role and disease using `_get_user_eligible_lab_unit_ids()`
2. Filter tasks by:
   - Eligible lab units
   - Disease ID
   - Appropriate state for the role:
     - Residents: `state == "pending"`
     - Faculty: `state == "resident_done"`
     - Arbitrators: `state == "arbitration"`
3. Exclude tasks the user has graded in the last 2 weeks using `_has_user_graded_task_2weeks()`
4. Return a random task from the filtered list (with retry logic - attempts up to 3 times if needed)
5. If no tasks are available after attempts, returns a helpful message

The filtering is performed by the `_get_filtered_tasks(db, user_id, disease_id, role_slot, eligible_lab_unit_ids)` function which:
- Gets all tasks matching the criteria (lab units, disease, state)
- Filters out tasks that the user has graded in the past 2 weeks
- The 2-week restriction applies across all role slots (if you graded as resident, you can't grade as faculty/arbitrator for the same task within 2 weeks)

## Grading Task Flow

### Accessing a Task
The `dual_grading_task(task_id, slot_type)` function:
1. Validates the slot type ('resident', 'faculty', 'arbitrator')
2. Checks user eligibility for the specified slot via `get_user_eligibility_for_task()`
3. Checks if the slot is available based on the current task state using `check_revision_eligibility_by_task_state(task_state, role_slot, grade_created_at)`
4. Special handling for arbitrators on final tasks:
   - Uses `is_arbitrator_eligible_for_revision()` to check if arbitrator is eligible to revise their own grade within 6 hours
5. For arbitrators on arbitration tasks, fetches resident and faculty grades to display for reference

### Task States and Their Meanings
- `pending`: Task is waiting for resident grading (no grades submitted yet)
- `resident_done`: Resident has graded, faculty needs to grade (task moves to faculty queue)
- `faculty_done`: Faculty has graded, but resident hasn't graded yet (task is in faculty queue until resident grades)
- `arbitration`: Resident and faculty grades differ, needs arbitrator to decide
- `final`: Task finalized (consensus reached either by matching grades or arbitrator's decision)

### Edge Cases for Task Access
- If a resident tries to access a task that is `faculty_done`, they will not be able to proceed (only faculty and arbitrators can grade this task)
- If a faculty tries to access a task that is `resident_done`, they can grade it
- If a faculty tries to access a task that is `pending`, they will not be able to proceed (only residents can do initial grading)
- For arbitrators on final tasks, they can only revise their own grade if it was submitted within the 6-hour window

## Stuck Task Handling

### Task Tracker Model
A new `TaskTracker` model has been implemented to track when users start working on tasks:
- Records include: `task_id`, `user_id`, `role_slot` (resident|faculty|arbitrator), and `started_at` timestamp
- When a user accesses a task for grading, a tracker record is created or updated with the current timestamp
- This mechanism allows the system to identify tasks that have been started but not completed

### Stuck Task Cleanup Mechanism
- A background thread runs every 30 minutes to identify and reset tasks that have been in progress for more than 60 minutes without submission
- The cleanup mechanism identifies tasks in the `TaskTracker` table where `started_at` is older than the time threshold
- These stuck tasks are reset by deleting their tracker records, making them available for other users
- The `reset_stuck_tasks()` function handles the cleanup process, logging the tasks that were reset

## Revision Logic

### Time-Based Restrictions
- **Residents and Faculty**: Can revise their grades as long as the task is not finalized
- **Arbitrators**: Can only revise their grades within 6 hours of submission (configurable via `ARBITRATOR_REVISION_HOURS` environment variable, defaults to 6)
- **General exclusion**: Users cannot be assigned tasks they've graded in the last 2 weeks across any role slot

### Revision Functions

#### `is_user_eligible_for_revision(db, user_id, task_id, slot_type, grade)`
This function checks:
1. Validates the slot type ('resident', 'faculty', 'arbitrator')
2. Verifies the grade exists and belongs to the user
3. For residents and faculty: allows revision if task is not finalized
4. For arbitrators: allows revision only if grade was submitted within 6 hours (configurable via `ARBITRATOR_REVISION_HOURS`)

The function returns:
- `eligible`: boolean indicating if user is eligible for revision
- `message`: string explaining why eligible/not eligible
- `is_recent`: boolean indicating if grade was submitted recently enough for revision (specifically for arbitrators)

#### `is_arbitrator_eligible_for_revision(db, user_id, task_id, task)`
This function checks:
1. Verifies the user has made an arbitrator grade for the task
2. Uses `is_user_eligible_for_revision()` to check if the arbitrator can revise based on time constraint
3. Returns eligibility information including the arbitrator grade for further use

#### `is_arbitrator_revision_allowed(db, user_id, task_id, slot)`
Used in `dual_grading_submit()` to determine if an arbitrator can modify a finalized task:
1. Only applies to arbitrator submissions
2. Verifies the arbitrator has an existing grade for the task
3. Checks if the grade was submitted within 6 hours (configurable via `ARBITRATOR_REVISION_HOURS`)

The function returns:
- `allowed`: boolean indicating if revision is allowed
- `message`: string explaining why or why not
- `is_recent`: boolean indicating if the existing grade was submitted recently enough for revision

### Revision Endpoints

#### `revise_grading(grade_id)` - Direct Grade Revision
1. Validates the grade exists and belongs to the current user
2. Checks revision eligibility via `is_user_eligible_for_revision()`
3. Ensures the user still has the required role for the slot
4. Allows the user to revise their grade
5. This endpoint is for direct access to edit a specific grade by its ID

#### `dual_grading_task()` - Task-Based Revision
When accessing a task with an existing grade, the function:
1. Checks if the user has an existing grade for the slot
2. Allows continuing to work on the existing grade
3. For arbitrators on final tasks, allows revision if within 6 hours

## Submission Logic

### `dual_grading_submit()` - Grade Submission Handling
1. Validates inputs (task_id, label_id, slot type)
2. Checks if task is finalized and if arbitrator revision is allowed
3. Verifies user eligibility for the task and slot via `get_user_eligibility_for_task()`
4. For arbitrators, checks additional eligibility requirements:
   - User must have 'ophthalmologist' role
   - User must be eligible for arbitration via `check_arbitration_eligibility()`
   - Arbitrator cannot have graded the same task as resident or faculty within 2 weeks (unless revising their own arbitrator grade)
5. Creates new grade or updates existing grade
6. Updates task state via `update_task_state_based_on_grades()`
7. Creates consensus if applicable via `create_or_update_consensus()`
8. Calculates time taken for grading and logs the submission

### Arbitrator Exclusion Logic During Submission
When submitting as an arbitrator:
- If this is a revision of an existing arbitrator grade by the same user, the 2-week exclusion check is skipped
- If this is a new arbitrator grade, the system checks if the user has graded this task as resident or faculty within the last 2 weeks
- If the exclusion applies, the submission is blocked

### Logging
- All grade submissions are logged with IP address, user ID, task ID, slot type, disease ID, and grade information
- For revisions, previous grade and comment information is also logged
- Time taken for grading is calculated and stored

## Task State Management

### `update_task_state_based_on_grades(task_id)`
This function updates the task state based on submitted grades:
- If arbitrator has graded → `state = "final"`
- If both resident and faculty have graded:
  - If their grades match → `state = "final"`
  - If their grades differ → `state = "arbitration"`
- If only resident graded → `state = "resident_done"`
- If only faculty graded → `state = "faculty_done"`
- If no grades submitted → `state = "pending"`

Note: When a task transitions to "final" state, it becomes eligible for consensus creation.

### Consensus Creation
The `create_or_update_consensus()` function:
- Creates consensus when an arbitrator grades (method: "adjudication")
- Creates consensus when resident and faculty grades match (method: "match")
- Only creates consensus if no consensus already exists for the task
- The consensus creation is triggered after task state updates during grade submission

## Special Cases and Restrictions

### Arbitrator Exclusion Rule
Arbitrators cannot arbitrate a task they previously graded as resident or faculty within the last 2 weeks, unless they're revising their own arbitrator grade.
- This restriction is checked during submission (not task assignment)
- It applies to the same user grading the same task in different roles

### Time-Based Constraints
- General exclusion: Users cannot be assigned tasks they've graded in the last 2 weeks across any role slot
- Arbitrator revision: Arbitrators can only revise their grades within 6 hours of submission (configurable via `ARBITRATOR_REVISION_HOURS` environment variable)
- These time windows can be customized through environment variables

### Edge Cases and Error Handling
- **Invalid slot types**: If an invalid slot type is provided, access is denied with an appropriate message
- **Task not found**: If the specified task doesn't exist, access is denied with an appropriate message
- **Insufficient permissions**: If the user doesn't have appropriate permissions for the requested role slot, access is denied
- **Task in incorrect state**: If a user tries to access a task that's not in the appropriate state for their role, access is denied
- **Revision not allowed**: If a user tries to revise a grade that doesn't meet revision criteria, access is denied

## Revision Endpoints Overview

1. **`/grading/task/<task_id>/<slot_type>`**: Access a task for grading or revising existing grade
2. **`/grading/revise/<grade_id>`**: Direct access to revise a specific grade
3. Both endpoints use the same eligibility and revision logic checks

This comprehensive system ensures proper role-based access, prevents conflicts of interest, and maintains quality through the dual-grading and arbitration process with appropriate revision controls.