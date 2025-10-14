# Dual Grading System Documentation

## Overview

The dual grading system implements a three-tier grading process for retinal fundus images:
1. **Resident** performs initial grading
2. **Faculty** (ophthalmologist) provides independent assessment
3. **Arbitrator** (ophthalmologist) resolves discrepancies when resident and faculty grades differ

This system ensures quality control through multiple independent assessments and provides a consensus mechanism for final decisions.

## Workflow

### 1. Task Creation
- When an image is verified, grading tasks are automatically created for each disease
- Tasks are created in `pending` state and assigned to the appropriate lab unit

### 2. Resident Grading
- Residents access tasks in `pending` state
- They provide their assessment of the image
- After submission, task state changes to `resident_done`

### 3. Faculty Grading
- Faculty members access tasks in `resident_done` state
- They provide independent assessment without seeing resident's grade
- After submission:
  - If grades match: task state changes to `final` and consensus is created
  - If grades differ: task state changes to `arbitration`

### 4. Arbitration (when needed)
- Arbitrators access tasks in `arbitration` state
- They can see both resident and faculty grades to make informed decision
- Their decision becomes the final consensus
- Task state changes to `final`

### 5. Finalization
- Task is marked as `final`
- A consensus record is created with the final decision
- No further modifications allowed (except arbitrator revisions within 6 hours)

## Routes

### `/grading/` (GET)
**Dashboard** - Shows grading statistics, pending tasks, and grading history
- **Authentication**: Requires `resident`, `ophthalmologist`, or `admin` role

### `/grading/task/<int:task_id>/<string:slot_type>` (GET)
**Display grading task** - Shows the grading interface for a specific task
- **Parameters**:
  - `task_id`: The ID of the task to display
  - `slot_type`: The role slot (`resident`, `faculty`, or `arbitrator`)
- **Authentication**: Requires `resident`, `ophthalmologist`, or `admin` role
- **Access Control**: Users can only access tasks appropriate for their role and task state

### `/grading/task/submit` (POST)
**Submit grade** - Saves a grade for a task
- **Parameters**:
  - `task_id`: The ID of the task
  - `slot`: The role slot (`resident`, `faculty`, or `arbitrator`)
  - `label_id`: The ID of the disease grading label
  - `comment`: Optional comment
  - `action`: Optional action (`save_next` or `save_close`)
- **Authentication**: Requires `resident`, `ophthalmologist`, or `admin` role

### `/grading/revise/<int:grade_id>` (GET)
**Revise grade** - Allows users to revise their previous grades
- **Parameters**:
  - `grade_id`: The ID of the grade to revise
- **Authentication**: Requires `resident`, `ophthalmologist`, or `admin` role
- **Restrictions**:
  - Residents and faculty can revise until task is finalized
  - Arbitrators can only revise within 6 hours of submission

## Task States

| State | Description | Who Can Access |
|-------|-------------|----------------|
| `pending` | New task waiting for resident grading | Residents |
| `resident_done` | Resident has graded, waiting for faculty | Faculty |
| `faculty_done` | Faculty has graded, waiting for resident (edge case) | Residents |
| `arbitration` | Grades differ, needs arbitrator decision | Arbitrators |
| `final` | Task completed with consensus | No one (except arbitrator revision) |

## Access Controls

### Role-Based Permissions
- **Resident**: Must have 'resident' role, can only grade as 'resident'
- **Faculty**: Must have 'ophthalmologist' role, can grade as 'faculty'
- **Arbitrator**: Must have 'ophthalmologist' role with arbitration permissions, can grade as 'arbitrator'

### Task-Specific Eligibility
The system checks:
1. User has appropriate role for the requested slot
2. User has permissions for the disease and lab unit via `UserDiseaseUnitRole` table
3. Task is in correct state for the requested role
4. User hasn't graded this task in the last 2 weeks (across any role)

### Lab Unit Eligibility
- Users can only grade tasks assigned to their authorized lab units
- Admins can access all lab units
- Permissions are checked via `UserDiseaseUnitRole` table

## Revision Logic

### Time-Based Restrictions
- **Residents and Faculty**: Can revise grades until task is finalized
- **Arbitrators**: Can only revise within 6 hours of submission (configurable via `ARBITRATOR_REVISION_HOURS`)
- **General exclusion**: Users cannot be assigned tasks they've graded in the last 2 weeks

### Revision Process
1. Users access their previous grade via `/grading/revise/<grade_id>` or by accessing the task again
2. System checks revision eligibility based on role and time constraints
3. Users can update their grade and comment
4. Task state and consensus are updated accordingly

### Arbitrator Special Cases
- Arbitrators can revise their decision on finalized tasks within 6 hours
- This allows correction of errors while maintaining decision integrity
- After 6 hours, decisions become permanent

## Stuck Task Handling

### Task Tracker
- System tracks when users start working on tasks via `TaskTracker` model
- Records include: `task_id`, `user_id`, `role_slot`, and `started_at` timestamp
- Prevents multiple users from working on the same task simultaneously

### Cleanup Mechanism
- Background thread runs every 30 minutes
- Identifies tasks in progress for more than 60 minutes
- Resets stuck tasks by deleting tracker records
- Makes tasks available for other users

## Consensus Creation

### Match Consensus
- Created automatically when resident and faculty grades match
- Method: "match"
- No arbitrator involvement needed

### Arbitration Consensus
- Created when arbitrator provides decision
- Method: "adjudication"
- Arbitrator's grade becomes final decision

## Database Models

### GradingTask
Represents a grading task for an image and disease combination.
- **Fields**:
  - `id`: Primary key
  - `encounter_file_id`: Foreign key to EncounterFile (nullable)
  - `direct_image_upload_id`: Foreign key to DirectImageUpload (nullable)
  - `disease_id`: Foreign key to Disease
  - `lab_unit_id`: Foreign key to LabUnit
  - `state`: Task state (`pending`, `resident_done`, `faculty_done`, `arbitration`, `final`)
  - `created_at`, `updated_at`: Timestamps
- **Relationships**:
  - `disease`: The disease for this task
  - `lab_unit`: The lab unit for this task
  - `encounter_file`: The encounter file (if from ZIP upload)
  - `direct_image`: The direct image upload (if from direct upload)
  - `grades`: List of grades for this task
  - `consensus`: The consensus for this task (if finalized)

### Grade
Represents a grade given by a user for a task.
- **Fields**:
  - `id`: Primary key
  - `task_id`: Foreign key to GradingTask
  - `grader_user_id`: Foreign key to User
  - `role_slot`: The role slot (`resident`, `faculty`, or `arbitrator`)
  - `disease_grading_id`: Foreign key to DiseaseGrading
  - `comment`: Optional comment
  - `time_taken`: Time taken to grade (in seconds)
  - `created_at`, `updated_at`: Timestamps
- **Relationships**:
  - `task`: The task for this grade
  - `grader`: The user who gave this grade
  - `disease_grading`: The disease grading label

### Consensus
Represents the final consensus for a task.
- **Fields**:
  - `id`: Primary key
  - `task_id`: Foreign key to GradingTask (unique)
  - `final_disease_grading_id`: Foreign key to DiseaseGrading
  - `method`: The method used to reach consensus (`match` or `adjudication`)
  - `decided_by_user_id`: Foreign key to User (nullable, for arbitration)
  - `decided_at`: Timestamp
- **Relationships**:
  - `task`: The task for this consensus
  - `final_disease_grading`: The final disease grading label
  - `decided_by`: The arbitrator who decided (if arbitration)

## Security Features

### Audit Trail
- All grade submissions are logged with:
  - IP address
  - User ID
  - Task ID
  - Role slot
  - Disease ID
  - Grade information
  - Previous grade (for revisions)
  - Time taken

### Access Controls
- CSRF protection on all forms
- Role-based access control
- Task state validation
- Lab unit eligibility checks

### Data Integrity
- Database constraints prevent duplicate gradings
- Transaction management ensures data consistency
- Input validation on all submissions

## Error Handling

Common error scenarios:
- Invalid task IDs or slot types
- Insufficient permissions
- Tasks in incorrect state
- Missing disease gradings
- Network timeouts during submission

All errors are logged with appropriate detail for debugging, and user-friendly messages are displayed.