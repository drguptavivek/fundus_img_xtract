# Dual Grading Revision Utilities Documentation

This document provides an overview of the utility functions available in the dual grading revision utilities module. These utilities are designed for checking revision eligibility in the dual grading system.

## Module Overview

This module provides functions for checking if users are eligible to revise their grades for specific tasks and slots in the dual grading system. It includes specific checks for arbitrator revisions and general revision eligibility based on task state.

## Functions

### `is_user_eligible_for_revision(db: Session, user_id: int, task_id: int, slot_type: str, grade: Grade = None) -> dict`

Check if a user is eligible to revise their grade for a specific task and slot.

**Parameters:**
- `db` (Session): Database session
- `user_id` (int): ID of the user requesting revision
- `task_id` (int): ID of the grading task
- `slot_type` (str): The slot type ('resident', 'faculty', 'arbitrator')
- `grade` (Grade): The grade object to check (optional, will be fetched if not provided)

**Returns:**
- `dict`: A dictionary with the following keys:
  - `eligible` (bool): boolean indicating if the user is eligible for revision
  - `message` (str): string explaining why the user is or isn't eligible
  - `is_recent` (bool): boolean indicating if the grade was submitted recently enough for revision

**Implementation Details:**
- Validates the slot type
- Fetches the grade if not provided using fetch_existing_grade_for_user
- Checks if the grade belongs to the current user
- For resident and faculty grades: eligible for revision at any time before finalization
- For arbitrator grades: only eligible if submitted within the last 6 hours
- Handles timezone-naive datetime objects by assuming they're in UTC

### `is_arbitrator_eligible_for_revision(db: Session, user_id: int, task_id: int, task: Optional[GradingTask] = None) -> dict`

Specific check for arbitrator revision eligibility.

**Parameters:**
- `db` (Session): Database session
- `user_id` (int): ID of the user requesting revision
- `task_id` (int): ID of the grading task
- `task` (Optional[GradingTask]): The GradingTask object (optional, will be fetched if not provided)

**Returns:**
- `dict`: A dictionary with eligibility information including:
  - `eligible` (bool): boolean indicating if the user is eligible for revision
  - `message` (str): string explaining why the user is or isn't eligible
  - `grade` (Grade): the arbitrator grade object if found

**Implementation Details:**
- Fetches the task if not provided using fetch_task_with_related_data
- Checks if the user has made an arbitrator grade for this task
- Checks if the grade was made recently (within 6 hours) using is_user_eligible_for_revision
- Adds the grade to the result for further use

### `check_arbitrator_revision_eligibility(db: Session, user_id: int, task: GradingTask) -> tuple[bool, str]`

Check if an arbitrator is eligible to revise a grade based on the task state and other conditions.

**Parameters:**
- `db` (Session): Database session
- `user_id` (int): ID of the user requesting revision
- `task` (GradingTask): The GradingTask object

**Returns:**
- `tuple[bool, str]`: A tuple of (is_eligible: bool, message: str)

**Implementation Details:**
- For final tasks: checks if the user is the arbitrator who made the decision and if it was recent (within 6 hours)
- For non-final tasks: checks if the task state matches the arbitration requirements
- Handles timezone-naive datetime objects by assuming they're in UTC

### `is_arbitrator_revision_allowed(db: Session, user_id: int, task_id: int, slot: str) -> dict`

Check if an arbitrator is allowed to revise their grade.

**Parameters:**
- `db` (Session): Database session
- `user_id` (int): ID of the user requesting revision
- `task_id` (int): ID of the grading task
- `slot` (str): The slot type ('arbitrator')

**Returns:**
- `dict`: A dictionary with the following keys:
  - `allowed` (bool): boolean indicating if revision is allowed
  - `message` (str): string explaining why or why not
  - `is_recent` (bool): boolean indicating if the existing grade was submitted recently enough for revision

**Implementation Details:**
- Only allows checking for arbitrator revisions (returns error for other slots)
- Fetches the existing grade for the arbitrator using fetch_existing_grade_for_user
- Checks if the grade was submitted within the last 6 hours
- Handles timezone-naive datetime objects by assuming they're in UTC

### `check_revision_eligibility_by_task_state(task_state: str, role_slot: str, grade_created_at: Optional[datetime] = None) -> tuple[bool, str]`

Check if a user is eligible to revise a grade based on the task state and other conditions.

**Parameters:**
- `task_state` (str): Current state of the task
- `role_slot` (str): Role slot ('resident', 'faculty', 'arbitrator')
- `grade_created_at` (Optional[datetime]): When the grade was created (needed for arbitrator revisions)

**Returns:**
- `tuple[bool, str]`: A tuple of (is_eligible: bool, message: str)

**Implementation Details:**
- For final tasks: only arbitrators can revise if their grade was submitted within 6 hours
- For non-final tasks:
  - Residents: can revise at any time before finalization
  - Faculty: can revise at any time before finalization
  - Arbitrators: can revise if task is in arbitration state OR if their grade was submitted in the last 6 hours
- Handles timezone-naive datetime objects by assuming they're in UTC