# Dual Grading Functionality

## Overview

The dual grading functionality allows for a two-step grading process where images are graded by both a resident and a faculty member. If their grades don't match, an arbitrator can make the final decision.

## Workflow

1. **Task Creation**: When an image is verified, a grading task is automatically created.
2. **Resident Grading**: A resident grades the image.
3. **Faculty Grading**: A faculty member grades the image.
4. **Consensus Check**: If both grades match, the task is finalized with a "match" consensus.
5. **Arbitration**: If the grades don't match, an arbitrator is needed to make the final decision.
6. **Finalization**: The task is marked as final and a consensus record is created.

## Routes

### `/grading/task/<int:task_id>` (GET)

Display a dual grading task.

**Parameters**:
- `task_id`: The ID of the task to display

**Authentication**: Requires `resident`, `ophthalmologist`, or `admin` role

### `/grading/task/submit` (POST)

Submit a grade for a task.

**Parameters**:
- `task_id`: The ID of the task
- `slot`: The role slot (`resident`, `faculty`, or `arbitrator`)
- `label_id`: The ID of the disease grading label
- `comment`: Optional comment
- `action`: Optional action (`save_next` or `save_close`)

**Authentication**: Requires `resident`, `ophthalmologist`, or `admin` role

## Models

### GradingTask

Represents a grading task for an image.

**Fields**:
- `id`: Primary key
- `encounter_file_id`: Foreign key to EncounterFile (nullable)
- `direct_image_upload_id`: Foreign key to DirectImageUpload (nullable)
- `disease_id`: Foreign key to Disease
- `lab_unit_id`: Foreign key to LabUnit
- `state`: Task state (`pending`, `resident_done`, `faculty_done`, `arbitration`, `final`)
- `created_at`: Timestamp
- `updated_at`: Timestamp

**Relationships**:
- `disease`: The disease for this task
- `lab_unit`: The lab unit for this task
- `encounter_file`: The encounter file (if any)
- `direct_image`: The direct image upload (if any)
- `grades`: List of grades for this task
- `consensus`: The consensus for this task (if finalized)

### Grade

Represents a grade given by a user for a task.

**Fields**:
- `id`: Primary key
- `task_id`: Foreign key to GradingTask
- `grader_user_id`: Foreign key to User
- `role_slot`: The role slot (`resident`, `faculty`, or `arbitrator`)
- `disease_grading_id`: Foreign key to DiseaseGrading
- `comment`: Optional comment
- `created_at`: Timestamp
- `updated_at`: Timestamp

**Relationships**:
- `task`: The task for this grade
- `grader`: The user who gave this grade
- `label`: The disease grading label

### Consensus

Represents the final consensus for a task.

**Fields**:
- `id`: Primary key
- `task_id`: Foreign key to GradingTask (unique)
- `final_disease_grading_id`: Foreign key to DiseaseGrading
- `method`: The method used to reach consensus (`match` or `arbitration`)
- `decided_by_user_id`: Foreign key to User (nullable)
- `decided_at`: Timestamp

**Relationships**:
- `task`: The task for this consensus
- `final_label`: The final disease grading label
- `decided_by`: The user who decided (if arbitration)

## Services

### `is_user_eligible_for_slot(user, task, slot)`

Check if a user is eligible to grade a task for a specific slot.

**Parameters**:
- `user`: The user to check
- `task`: The task to check
- `slot`: The slot to check (`resident`, `faculty`, or `arbitrator`)

**Returns**: `True` if eligible, `False` otherwise

### `create_consensus_for_task(task_id)`

Create consensus for a task based on the grades.

**Parameters**:
- `task_id`: The ID of the task

**Returns**: The consensus object or `None` if consensus cannot be created

### `get_consensus_for_task(task_id)`

Get the consensus for a task.

**Parameters**:
- `task_id`: The ID of the task

**Returns**: The consensus object or `None` if no consensus exists