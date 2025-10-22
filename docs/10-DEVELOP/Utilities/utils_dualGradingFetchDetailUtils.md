# Dual Grading Fetch Detail Utilities Documentation

This document provides an overview of the utility functions available in the dual grading fetch detail module. These utilities are designed to work with grades and tasks, allowing for efficient retrieval of related data.

## Module Information

**Note:** All functions in this module expect a database session to be passed as a parameter. The caller is responsible for managing the session lifecycle (opening and closing). This design allows for better transaction management and session reuse.

## Functions

### `fetch_task_with_related_data(db, task_id: int) -> GradingTask`

Fetch a grading task with all related data.

**Parameters:**
- `db`: Database session (caller is responsible for closing)
- `task_id` (int): The ID of the task to fetch

**Returns:**
- `GradingTask` object with all related data loaded, including:
  - Disease information
  - Encounter file
  - Direct image
  - Consensus details (including decided by and final label)
  - All grades with grader information and labels

### `fetch_grade_with_related_data(db, grade_id: int) -> Grade`

Fetch a grade with all related data.

**Parameters:**
- `db`: Database session (caller is responsible for closing)
- `grade_id` (int): The ID of the grade to fetch

**Returns:**
- `Grade` object with all related data loaded, including:
  - Task information with disease, encounter file, and direct image
  - Consensus details (including decided by and final label)
  - All grades with grader information and labels
  - Grade label information

### `fetch_existing_grade_for_user(db, task_id: int, user_id: int, slot_type: str) -> Grade | None`

Fetch existing grade for this user and slot (for review purposes).

**Parameters:**
- `db`: Database session (caller is responsible for closing)
- `task_id` (int): The ID of the task
- `user_id` (int): The ID of the user
- `slot_type` (str): The slot type (resident, resident2, arbitrator)

**Returns:**
- `Grade` object if found, None otherwise

### `get_user_gradings(db, user_id: int, page: int = 1, per_page: int = 20, role_slot: Optional[str] = None) -> Tuple[List[Grade], int]`

Retrieve a paginated list of gradings done by a user.

This function returns Grade model objects. For a version that includes related details like disease name, lab unit name, etc., see `get_user_gradings_with_details()`.

**Parameters:**
- `db`: Database session (caller is responsible for closing)
- `user_id` (int): ID of the user
- `page` (int): Page number (1-indexed), defaults to 1
- `per_page` (int): Number of items per page, defaults to 20
- `role_slot` (Optional[str]): Filter by role slot (resident, resident2, arbitrator)

**Returns:**
- `Tuple[List[Grade], int]`: A tuple containing:
  - List of Grade objects for the current page
  - Total count of gradings by the user

### `get_user_gradings_with_details(db, user_id: int, page: int = 1, per_page: int = 20, role_slot: Optional[str] = None, filter_date: Optional[str] = None) -> Tuple[List[Dict[str, Any]], int]`

Retrieve a paginated list of gradings done by a user with related details.

**Parameters:**
- `db`: Database session (caller is responsible for closing)
- `user_id` (int): ID of the user
- `page` (int): Page number (1-indexed), defaults to 1
- `per_page` (int): Number of items per page, defaults to 20
- `role_slot` (Optional[str]): Filter by role slot (resident, resident2, arbitrator)
- `filter_date` (Optional[str]): Filter by date in YYYY-MM-DD format

**Returns:**
- `Tuple[List[Dict[str, Any]], int]`: A tuple containing:
  - List of dictionaries with grading details for the current page
  - Total count of gradings by the user

**Dictionary fields include:**
- `id`: Grade ID
- `task_id`: Task ID
- `grader_user_id`: User ID of the grader
- `role_slot`: Role slot (resident, resident2, arbitrator)
- `disease_grading_id`: Disease grading ID
- `comment`: Grade comment
- `created_at`: Creation timestamp
- `updated_at`: Update timestamp
- `disease_name`: Name of the disease
- `grade_impression`: Grade impression
- `lab_unit_name`: Name of the lab unit
- `hospital_name`: Name of the hospital
- `image_uuid`: UUID of the image (encounter file or direct image)
- `ai_probability`: AI probability (if applicable)
- `ai_model_name`: Name of the AI model (if applicable)
- `ai_model_version`: Version of the AI model (if applicable)