# Task Utilities Documentation

This document provides an overview of the utility functions available in the task utilities module. These utilities are designed for managing tasks and related information with proper scoping based on user's lab units and role-based access controls.

## Module Overview

This module provides centralized functions for retrieving and managing task information, with proper scoping based on user's lab units and role-based access controls.

## Functions

### `get_task_summary(db_session, page: int = 1, per_page: int = 50, lab_unit_ids: Optional[List[int]] = None, status_filter: Optional[str] = None, disease_filter: Optional[int] = None, search_query: Optional[str] = None, hospital_filter: Optional[int] = None, lab_unit_name_filter: Optional[str] = None, lab_unit_filter: Optional[int] = None) -> Tuple[List[Dict[str, Any]], int]`

Get paginated list of tasks with key information.

**Parameters:**
- `db_session`: Database session to use for queries
- `page` (int): Page number for pagination (1-indexed), default is 1
- `per_page` (int): Number of items per page, default is 50
- `lab_unit_ids` (Optional[List[int]]): List of lab unit IDs to scope the query to
- `status_filter` (Optional[str]): Optional status to filter tasks (e.g., 'pending', 'completed', 'in_progress', 'final')
- `disease_filter` (Optional[int]): Optional disease ID to filter tasks
- `search_query` (Optional[str]): Optional search term to match against image UUID or patient info
- `hospital_filter` (Optional[int]): Optional hospital ID to filter tasks
- `lab_unit_name_filter` (Optional[str]): Optional lab unit name to filter tasks (deprecated - using lab_unit_filter instead)
- `lab_unit_filter` (Optional[int]): Optional lab unit ID to filter tasks

**Returns:**
- `Tuple[List[Dict[str, Any]], int]`: Tuple of (list of task dictionaries, total count)

**Task Dictionary Fields:**
- `id` (int): Task ID
- `uuid` (str): Task UUID (using ID as GradingTask doesn't have a UUID field)
- `status` (str): Task status/state
- `disease` (str): Disease name
- `lab_unit` (str): Lab unit name
- `hospital` (str): Hospital name
- `image_uuid` (str): Image UUID
- `image_type` (str): Image type ('direct', 'zip', or 'Unknown')
- `created_at` (datetime): Task creation datetime
- `updated_at` (datetime): Task update datetime

### `get_task_detail(db_session, task_id: int) -> Optional[Dict[str, Any]]`

Get detailed information about a specific task including grades and consensus.

**Parameters:**
- `db_session`: Database session to use for queries
- `task_id` (int): ID of the task to retrieve details for

**Returns:**
- `Optional[Dict[str, Any]]`: Dictionary with task details or None if task not found

**Task Detail Dictionary Fields:**
- `id` (int): Task ID
- `uuid` (str): Task UUID (using ID as GradingTask doesn't have a UUID field)
- `status` (str): Task status/state
- `disease` (str): Disease name
- `lab_unit` (str): Lab unit name
- `hospital` (str): Hospital name
- `image_uuid` (str): Image UUID
- `image_path` (str): Path to the image file
- `patient_id` (str): Patient ID
- `patient_name` (str): Patient name
- `patient_age` (str): Patient age (currently 'Unknown')
- `patient_sex` (str): Patient sex (currently 'Unknown')
- `created_at` (datetime): Task creation datetime
- `updated_at` (datetime): Task update datetime
- `assigned_to` (str): Who the task is assigned to (currently None)
- `created_by` (str): Who created the task (currently None)
- `due_date` (str): Task due date (currently None)
- `priority` (str): Task priority (currently None)
- `notes` (str): Task notes (currently None)
- `grades` (List[Dict]): List of grade information
- `consensus_info` (Dict): Information about consensus
- `camera_type` (str): Type of camera used for the image

### `get_tasks_by_status(db_session, status: str, lab_unit_ids: Optional[List[int]] = None, page: int = 1, per_page: int = 50) -> Tuple[List[Dict[str, Any]], int]`

Get tasks filtered by status.

**Parameters:**
- `db_session`: Database session to use for queries
- `status` (str): Status to filter by (e.g., 'pending', 'completed', 'in_progress', 'final')
- `lab_unit_ids` (Optional[List[int]]): List of lab unit IDs to scope the query to
- `page` (int): Page number for pagination (1-indexed), default is 1
- `per_page` (int): Number of items per page (default 50)

**Returns:**
- `Tuple[List[Dict[str, Any]], int]`: Tuple of (list of task dictionaries, total count)

**Task Dictionary Fields:**
- `id` (int): Task ID
- `uuid` (str): Task UUID (using ID as GradingTask doesn't have a UUID field)
- `status` (str): Task status/state
- `disease` (str): Disease name
- `lab_unit` (str): Lab unit name
- `image_uuid` (str): Image UUID
- `assigned_to` (str): Who the task is assigned to (currently None)
- `created_at` (datetime): Task creation datetime
- `due_date` (str): Task due date (currently None)

### `get_task_stats(db_session, lab_unit_ids: Optional[List[int]] = None) -> Dict[str, int]`

Get task statistics for specified lab units.

**Parameters:**
- `db_session`: Database session to use for queries
- `lab_unit_ids` (Optional[List[int]]): List of lab unit IDs to get stats for

**Returns:**
- `Dict[str, int]`: Dictionary with task statistics with keys:
  - `total_tasks` (int): Total number of tasks
  - `pending_tasks` (int): Number of pending tasks
  - `in_progress_tasks` (int): Number of in-progress tasks
  - `completed_tasks` (int): Number of completed tasks
  - `overdue_tasks` (int): Number of overdue tasks (currently always 0)

### `get_tasks_for_user(db_session, user_id: int, page: int = 1, per_page: int = 50, status_filter: Optional[str] = None) -> Tuple[List[Dict[str, Any]], int]`

Get tasks eligible for a specific user based on their permissions.

In this system, tasks are not assigned but users get tasks based on their LabUnit-Disease-slot eligibility mapping.

**Parameters:**
- `db_session`: Database session to use for queries
- `user_id` (int): ID of the user to get eligible tasks for
- `page` (int): Page number for pagination (1-indexed), default is 1
- `per_page` (int): Number of items per page (default 50)
- `status_filter` (Optional[str]): Optional status to filter tasks

**Returns:**
- `Tuple[List[Dict[str, Any]], int]`: Tuple of (list of task dictionaries, total count)

**Task Dictionary Fields:**
- `id` (int): Task ID
- `uuid` (str): Task UUID (using ID as GradingTask doesn't have a UUID field)
- `status` (str): Task status/state
- `disease` (str): Disease name
- `lab_unit` (str): Lab unit name
- `image_uuid` (str): Image UUID
- `created_at` (datetime): Task creation datetime
- `updated_at` (datetime): Task update datetime
- `due_date` (str): Task due date (currently None)
- `priority` (str): Task priority (currently None)