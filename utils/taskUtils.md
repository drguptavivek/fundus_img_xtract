# Task Utilities Documentation

Calling functions should  use db_context_manager correctly.

This module provides centralized functions for retrieving and managing task information with proper scoping based on user's lab units and role-based access controls.

## Functions

### `get_task_summary`

Retrieves a paginated list of tasks with key information for display purposes.

#### Parameters:
- `db_session`: Database session to use for queries
- `page` (int): Page number for pagination (1-indexed), default is 1
- `per_page` (int): Number of items per page, default is 50
- `lab_unit_ids` (Optional[List[int]]): List of lab unit IDs to scope the query to
- `status_filter` (Optional[str]): Optional status to filter tasks (e.g., 'pending', 'resident_done', 'faculty_done', 'arbitration', 'final')
- `disease_filter` (Optional[int]): Optional disease ID to filter tasks
- `search_query` (Optional[str]): Optional search term to match against image UUID

#### Returns:
Tuple of (list of task dictionaries, total count)

Each task dictionary contains:
- `id` (int): Task ID
- `uuid` (str): Task identifier (using ID since GradingTask doesn't have UUID)
- `status` (str): Task state (e.g., 'pending', 'resident_done', etc.)
- `disease` (str): Name of the disease being graded
- `lab_unit` (str): Name of the lab unit
- `image_uuid` (str): UUID of the associated image
- `created_at` (datetime): When the task was created
- `updated_at` (datetime): When the task was last updated

#### Access Control:
- Non-admin users can only see tasks in their assigned lab units
- Admin users can see all tasks regardless of lab unit

---

### `get_task_detail`

Retrieves detailed information about a specific task including grades and consensus.

#### Parameters:
- `db_session`: Database session to use for queries
- `task_id` (int): ID of the task to retrieve details for

#### Returns:
Dictionary with comprehensive task details or None if task not found

The dictionary includes:
- Basic task information (ID, status, disease, lab unit, etc.)
- Patient information (if available)
- Grading information with all grades assigned to the task
- Consensus information if a consensus has been reached
- Image information depending on whether it's from an encounter file or direct upload

#### Access Control:
- Non-admin users can only access tasks in their assigned lab units
- Admin users can access any task

---

### `get_tasks_by_status`

Retrieves tasks filtered by a specific status with pagination support.

#### Parameters:
- `db_session`: Database session to use for queries
- `status` (str): Status to filter by (e.g., 'pending', 'resident_done', 'faculty_done', 'arbitration', 'final')
- `lab_unit_ids` (Optional[List[int]]): List of lab unit IDs to scope the query to
- `page` (int): Page number for pagination (1-indexed), default is 1
- `per_page` (int): Number of items per page, default is 50

#### Returns:
Tuple of (list of task dictionaries, total count)

Each task dictionary contains:
- `id` (int): Task ID
- `uuid` (str): Task identifier (using ID since GradingTask doesn't have UUID)
- `status` (str): Task state
- `disease` (str): Name of the disease being graded
- `lab_unit` (str): Name of the lab unit
- `image_uuid` (str): UUID of the associated image
- `created_at` (datetime): When the task was created
- `due_date` (datetime): Due date if applicable (None for GradingTask)

#### Access Control:
- Non-admin users can only see tasks in their assigned lab units
- Admin users can see all tasks regardless of lab unit

---

### `get_task_stats`

Retrieves task statistics for specified lab units.

#### Parameters:
- `db_session`: Database session to use for queries
- `lab_unit_ids` (Optional[List[int]]): List of lab unit IDs to get stats for

#### Returns:
Dictionary with task statistics:
- `total_tasks` (int): Total number of tasks
- `pending_tasks` (int): Number of pending tasks
- `in_progress_tasks` (int): Number of tasks in progress (resident_done or faculty_done)
- `completed_tasks` (int): Number of final tasks
- `overdue_tasks` (int): Number of overdue tasks (0 for GradingTask since it doesn't have due dates)

#### Access Control:
- Non-admin users can only get stats for their assigned lab units
- Admin users can get stats for all lab units

---

### `get_tasks_for_user`

Retrieves tasks eligible for a specific user based on their LabUnit-Disease-slot eligibility mapping.

In this system, tasks are not assigned but users get tasks based on their LabUnit-Disease-slot eligibility mapping.

#### Parameters:
- `db_session`: Database session to use for queries
- `user_id` (int): ID of the user to get eligible tasks for
- `page` (int): Page number for pagination (1-indexed), default is 1
- `per_page` (int): Number of items per page, default is 50
- `status_filter` (Optional[str]): Optional status to filter tasks

#### Returns:
Tuple of (list of task dictionaries, total count)

Each task dictionary contains:
- `id` (int): Task ID
- `uuid` (str): Task identifier (using ID since GradingTask doesn't have UUID)
- `status` (str): Task state
- `disease` (str): Name of the disease being graded
- `lab_unit` (str): Name of the lab unit
- `image_uuid` (str): UUID of the associated image
- `created_at` (datetime): When the task was created
- `updated_at` (datetime): When the task was last updated

#### Access Control:
- Uses the UserDiseaseUnitRole model to find all lab unit-disease combinations where the user has grading permissions
- Non-admin users viewing the data can only see tasks in their assigned lab units
- Admin users can see all eligible tasks regardless of lab unit