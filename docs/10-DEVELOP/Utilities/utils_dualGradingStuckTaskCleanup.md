# Dual Grading Stuck Task Cleanup Utilities Documentation

This document provides an overview of the utility functions available in the dual grading stuck task cleanup module. These utilities are designed for detecting and cleaning up stuck tasks in the dual grading system.

## Module Overview

This module provides functions for detecting and cleaning up tasks that have been started but not completed within the specified time limit. A stuck task is one where a user has accessed the task but not submitted a grade within the specified time limit (default 60 minutes).

## Functions

### `cleanup_stuck_tasks(time_limit_minutes: int = 60, db=None) -> int`

Identifies and cleans up tasks that have been started but not completed within the specified time limit.
This helps to reclaim tasks from users who may have disconnected or left tasks incomplete.

**Parameters:**
- `time_limit_minutes` (int): The time limit in minutes after which a task is considered stuck (default 60)
- `db`: Optional database session (if not provided, a new session will be created)

**Returns:**
- `int`: The number of stuck tasks that were cleaned up

**Implementation Details:**
- Calculates the time threshold based on the current time and time limit
- Finds TaskTracker entries where the task was started but not completed and the start time is older than the threshold
- Currently only logs the stuck tasks (implementation may involve deleting the tracker records)
- Returns the count of stuck tasks found
- Properly manages database sessions (creates one if not provided, commits/rollbacks as needed)

### `mark_task_started(task_id: int, user_id: int, role_slot: str, db=None) -> bool`

Marks that a user has started working on a task by creating a TaskTracker record.
This function should be called when a user accesses a task for grading.

**Parameters:**
- `task_id` (int): The ID of the task being worked on
- `user_id` (int): The ID of the user starting the task
- `role_slot` (str): The role slot ('resident', 'resident2', or 'arbitrator')
- `db`: Optional database session (if not provided, a new session will be created)

**Returns:**
- `bool`: True if successfully marked, False otherwise

**Implementation Details:**
- Checks if a tracker record already exists for this user and task
- If existing, updates the start time; if not, creates a new tracker record
- Handles potential race conditions where two requests try to create the same tracker
- Uses timezone-aware datetime for the start time (UTC)
- Properly manages database sessions

### `cleanup_task_tracker(task_id: int, user_id: int, role_slot: str, db=None) -> bool`

Immediately cleanup the TaskTracker record when a task for a specific slot is completed.

**Parameters:**
- `task_id` (int): The ID of the task being completed
- `user_id` (int): The ID of the user completing the task
- `role_slot` (str): The role slot ('resident', 'resident2', or 'arbitrator') being completed
- `db`: Optional database session (if not provided, a new session will be created)

**Returns:**
- `bool`: True if successfully cleaned up, False otherwise

**Implementation Details:**
- Finds the specific task tracker record for the given task, user, and role slot
- Removes the tracker record from the database
- Logs the cleanup action for auditing
- Properly manages database sessions
- Returns True if no record exists (considered successful since there's nothing to cleanup)

### `reset_stuck_tasks(time_limit_minutes: int = 60, db=None) -> int`

Identifies and resets tasks that have been started but not completed within the time limit.
This deletes the tracker records so the tasks become available for other users.

**Parameters:**
- `time_limit_minutes` (int): The time limit in minutes after which a task is considered stuck (default 60)
- `db`: Optional database session (if not provided, a new session will be created)

**Returns:**
- `int`: The number of stuck tasks that were reset

**Implementation Details:**
- Calculates the time threshold based on the current time and time limit
- Finds task tracker entries where grading was started but not completed within the time limit
- Deletes the tracker records to allow the tasks to become available for other users
- Logs each reset action for auditing
- Returns the count of reset tasks
- Properly manages database sessions (creates one if not provided, commits/rollbacks as needed)