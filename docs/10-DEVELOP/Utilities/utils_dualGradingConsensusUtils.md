# Dual Grading Consensus Utilities Documentation

This document provides an overview of the utility functions available in the dual grading consensus module. These utilities are designed for handling consensus in the dual grading system.

## Module Overview

This module provides functions for:
- Creating consensus records when grading tasks reach agreement
- Checking consensus status for tasks
- Updating task states based on grading activity

## Functions

### `create_or_update_consensus(task_id: int, db=None) -> Optional[Consensus]`

Create or update consensus for a task based on grades.

**Parameters:**
- `task_id` (int): The ID of the task to create/update consensus for
- `db`: Optional database session (if not provided, a new session will be created)

**Returns:**
- `Optional[Consensus]`: Consensus object if created/updated, None otherwise

**Implementation Details:**
- Fetches the task with all related grades and graders
- Checks for grades by role (resident, resident2, arbitrator)
- If an arbitrator has graded, creates consensus using the "adjudication" method
- If resident and resident2 grades match, creates consensus using the "match" method
- If resident and resident2 grades don't match, no consensus is created yet (needs arbitration)
- Logs consensus creation with task details
- Properly manages database sessions (creates one if not provided, commits if managing its own session)

### `get_task_consensus_status(task_id: int, db=None) -> dict`

Get the consensus status for a task.

**Parameters:**
- `task_id` (int): The ID of the task to check
- `db`: Optional database session (if not provided, a new session will be created)

**Returns:**
- `dict`: Dictionary with consensus status information including task details, grades by role, and consensus information if it exists

**Return Structure:**
- `task_id` (int): The ID of the task
- `task_state` (str): The current state of the task
- `resident_grade` (dict): Details about the resident's grade (if it exists)
- `resident2_grade` (dict): Details about the resident2's grade (if it exists)
- `arbitrator_grade` (dict): Details about the arbitrator's grade (if it exists)
- `consensus` (dict): Details about the consensus (if it exists)
- `can_create_consensus` (bool): Whether consensus can be created based on current grades

### `update_task_state_based_on_grades(task_id: int, db=None) -> Optional[GradingTask]`

Update the task state based on the current grades.

**Parameters:**
- `task_id` (int): The ID of the task to update
- `db`: Optional database session (if not provided, a new session will be created)

**Returns:**
- `Optional[GradingTask]`: Updated GradingTask object or None if task not found

**Implementation Details:**
- Determines the new state based on the grades that have been submitted:
  - If arbitrator has graded: state becomes "final"
  - If both resident and resident2 have graded and they match: state becomes "final"
  - If both resident and resident2 have graded but they don't match: state becomes "arbitration"
  - If only resident has graded: state becomes "resident_done"
  - If only resident2 has graded: state becomes "resident2_done"
  - If no grades have been submitted: state remains "pending"
- Only updates the task if the state actually changed
- Logs state changes for debugging and monitoring
- Properly manages database sessions

### `has_consensus(task_id: int, db=None) -> bool`

Check if a task has reached consensus.

**Parameters:**
- `task_id` (int): The ID of the task to check
- `db`: Optional database session (if not provided, a new session will be created)

**Returns:**
- `bool`: True if the task has consensus, False otherwise

### `get_consensus_method(task_id: int, db=None) -> Optional[str]`

Get the consensus method for a task (match or adjudication).

**Parameters:**
- `task_id` (int): The ID of the task to check
- `db`: Optional database session (if not provided, a new session will be created)

**Returns:**
- `Optional[str]`: Method string ('match' or 'adjudication') or None if no consensus

**Implementation Details:**
- Returns 'match' when consensus was reached because resident and resident2 grades matched
- Returns 'adjudication' when consensus was established by an arbitrator's decision
- Returns None if no consensus has been reached yet

## Module Constants

### `consensus_logger`

A logger instance named "consensus" for logging consensus-related events and operations.