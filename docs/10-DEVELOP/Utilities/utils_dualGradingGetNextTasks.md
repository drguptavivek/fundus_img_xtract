# Dual Grading Get Next Tasks Utilities Documentation

This document provides an overview of the utility functions available in the dual grading get next tasks module. These utilities are designed for getting the next eligible dual grading tasks for users based on their role and eligibility.

## Module Overview

This module provides functions for determining and retrieving the next eligible dual grading tasks for different user roles (resident, resident2, arbitrator).

## Functions

### `_has_user_graded_task_6hr(db, user_id: int, task_id: int) -> bool`

Check if a user has graded a task in the last 6 hours (or configured timeframe). This is used for revision functionality to allow arbitrators to revise grades.

**Parameters:**
- `db`: Database session
- `user_id` (int): The ID of the user
- `task_id` (int): The ID of the task

**Returns:**
- `bool`: True if user has graded the task in the last 6 hours, False otherwise

**Implementation Details:**
- Gets the revision timeframe from environment variable ARBITRATOR_REVISION_HOURS (defaults to 6 hours)
- Compares grade creation time with the cutoff time
- Handles timezone-naive datetimes by assuming they're in UTC

### `_get_filtered_tasks(db, user_id: int, disease_id: int, role_slot: str, eligible_lab_unit_ids: list) -> list`

Get filtered tasks based on role slot and other criteria.

**Parameters:**
- `db`: Database session
- `user_id` (int): The ID of the user
- `disease_id` (int): The disease ID
- `role_slot` (str): The role slot ('resident', 'resident2', or 'arbitrator')
- `eligible_lab_unit_ids` (list): List of lab unit IDs the user is eligible for

**Returns:**
- `list`: List of filtered tasks

**Implementation Details:**
- Filters tasks based on eligible lab units for the user
- Filters tasks by disease ID
- Filters tasks by role-specific states:
  - Arbitrators: only see tasks in "arbitration" state
  - Residents: only see tasks in "pending" state
  - Resident2: only see tasks in "resident_done" state
- Excludes tasks that the user has graded in the past 2 weeks

### `get_next_eligible_resident_task(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None) -> Optional[Union[GradingTask, str]]`

Get the next eligible task for a resident user.

**Parameters:**
- `user_id` (int): The ID of the user (must be a resident or admin)
- `disease_id` (int): The disease ID (required)
- `lab_unit_id` (Optional[int]): Optional lab unit ID to filter by
- `db`: Optional database session (if not provided, a new session will be created)

**Returns:**
- `Optional[Union[GradingTask, str]]`: The next eligible GradingTask, None if no tasks are available, or a helpful message if no suitable tasks are found after 3 tries

**Implementation Details:**
- Gets user's eligible lab unit IDs for resident role and specified disease
- If a specific lab unit is requested, checks if user is eligible for it
- Tries up to 3 times to find a suitable task using _get_filtered_tasks
- Returns a random task from the filtered list if available
- Returns a helpful message if no tasks are found after 3 attempts

### `get_next_eligible_resident2_task(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None) -> Optional[Union[GradingTask, str]]`

Get the next eligible task for a resident2 user.

**Parameters:**
- `user_id` (int): The ID of the user (must be an ophthalmologist or admin)
- `disease_id` (int): The disease ID (required)
- `lab_unit_id` (Optional[int]): Optional lab unit ID to filter by
- `db`: Optional database session (if not provided, a new session will be created)

**Returns:**
- `Optional[Union[GradingTask, str]]`: The next eligible GradingTask, None if no tasks are available, or a helpful message if no suitable tasks are found after 3 tries

**Implementation Details:**
- Gets user's eligible lab unit IDs for resident2 role and specified disease
- If a specific lab unit is requested, checks if user is eligible for it
- Tries up to 3 times to find a suitable task using _get_filtered_tasks
- Returns a random task from the filtered list if available
- Returns a helpful message if no tasks are found after 3 attempts

### `get_next_eligible_arbitrator_task(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None) -> Optional[Union[GradingTask, str]]`

Get the next eligible task for an arbitrator user.

**Parameters:**
- `user_id` (int): The ID of the user (must be an ophthalmologist or admin)
- `disease_id` (int): The disease ID (required)
- `lab_unit_id` (Optional[int]): Optional lab unit ID to filter by
- `db`: Optional database session (if not provided, a new session will be created)

**Returns:**
- `Optional[Union[GradingTask, str]]`: The next eligible GradingTask, None if no tasks are available, or a helpful message if no suitable tasks are found after 3 tries

**Implementation Details:**
- Gets user's eligible lab unit IDs for arbitrator role and specified disease
- If a specific lab unit is requested, checks if user is eligible for it
- Tries up to 3 times to find a suitable task using _get_filtered_tasks
- Returns a random task from the filtered list if available
- Returns a helpful message if no tasks are found after 3 attempts

### `_atomically_get_and_lock_task(db, user_id: int, disease_id: int, role_slot: str, eligible_lab_unit_ids: list) -> Optional[GradingTask]`

Atomically get and lock a task for a user to prevent race conditions. This function uses SELECT FOR UPDATE to ensure no other user can get the same task.

**Parameters:**
- `db`: Database session
- `user_id` (int): The ID of the user
- `disease_id` (int): The disease ID
- `role_slot` (str): The role slot ('resident', 'resident2', or 'arbitrator')
- `eligible_lab_unit_ids` (list): List of lab unit IDs the user is eligible for

**Returns:**
- `Optional[GradingTask]`: The locked GradingTask or None if no eligible tasks are available

**Implementation Details:**
- Uses SELECT FOR UPDATE to lock the rows in the database
- Orders tasks randomly and limits to 1 to get just one task locked
- Verifies that the user hasn't graded the task recently
- Returns the locked task if eligible, otherwise None

### `get_next_eligible_resident_task_atomic(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None) -> Optional[Union[GradingTask, str]]`

Get the next eligible task for a resident user with atomic locking to prevent race conditions.

**Parameters:**
- `user_id` (int): The ID of the user (must be a resident or admin)
- `disease_id` (int): The disease ID (required)
- `lab_unit_id` (Optional[int]): Optional lab unit ID to filter by
- `db`: Optional database session (if not provided, a new session will be created)

**Returns:**
- `Optional[Union[GradingTask, str]]`: The next eligible GradingTask, None if no tasks are available, or a helpful message if no suitable tasks are found after 3 tries

**Implementation Details:**
- Gets user's eligible lab unit IDs for resident role and specified disease
- If a specific lab unit is requested, checks if user is eligible for it
- Tries up to 3 times to find a suitable task using _atomically_get_and_lock_task
- Returns a locked task from the filtered list if available
- Returns a helpful message if no tasks are found after 3 attempts

### `get_next_eligible_resident2_task_atomic(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None) -> Optional[Union[GradingTask, str]]`

Get the next eligible task for a resident2 user with atomic locking to prevent race conditions.

**Parameters:**
- `user_id` (int): The ID of the user (must be an ophthalmologist or admin)
- `disease_id` (int): The disease ID (required)
- `lab_unit_id` (Optional[int]): Optional lab unit ID to filter by
- `db`: Optional database session (if not provided, a new session will be created)

**Returns:**
- `Optional[Union[GradingTask, str]]`: The next eligible GradingTask, None if no tasks are available, or a helpful message if no suitable tasks are found after 3 tries

**Implementation Details:**
- Gets user's eligible lab unit IDs for resident2 role and specified disease
- If a specific lab unit is requested, checks if user is eligible for it
- Tries up to 3 times to find a suitable task using _atomically_get_and_lock_task
- Returns a locked task from the filtered list if available
- Returns a helpful message if no tasks are found after 3 attempts

### `get_next_eligible_arbitrator_task_atomic(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None) -> Optional[Union[GradingTask, str]]`

Get the next eligible task for an arbitrator user with atomic locking to prevent race conditions.

**Parameters:**
- `user_id` (int): The ID of the user (must be an ophthalmologist or admin)
- `disease_id` (int): The disease ID (required)
- `lab_unit_id` (Optional[int]): Optional lab unit ID to filter by
- `db`: Optional database session (if not provided, a new session will be created)

**Returns:**
- `Optional[Union[GradingTask, str]]`: The next eligible GradingTask, None if no tasks are available, or a helpful message if no suitable tasks are found after 3 attempts

**Implementation Details:**
- Gets user's eligible lab unit IDs for arbitrator role and specified disease
- If a specific lab unit is requested, checks if user is eligible for it
- Tries up to 3 times to find a suitable task using _atomically_get_and_lock_task
- Returns a locked task from the filtered list if available
- Returns a helpful message if no tasks are found after 3 attempts