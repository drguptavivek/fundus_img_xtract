# Dual Grading Eligibility Utilities Documentation

This document provides an overview of the utility functions available in the dual grading eligibility module. These utilities are designed to check and retrieve user eligibility for grading tasks in different roles and contexts.

## Module Information

**Note:** All functions in this module expect a database session to be passed as a parameter. The caller is responsible for managing the session lifecycle (opening and closing). This design allows for better transaction management and session reuse.

## Functions

### `get_user_grading_eligibility_details(db, user_id: int) -> Dict[str, Any]`

Get detailed grading eligibility information for a user with lab unit and disease names.

**Parameters:**
- `db`: Database session (caller is responsible for closing)
- `user_id` (int): ID of the user

**Returns:**
- `Dict` containing user eligibility details grouped by hospital, then lab unit, then disease. The structure is:
  - Hospital names as keys
    - Lab unit names as keys
      - Disease names as keys
        - Lists of roles (Resident, Resident2, Arbitrator) the user has for that combination

### `_get_user_eligible_lab_unit_ids(db, user_id: int, disease_id: int, role_slot: str) -> Optional[list]`

Get the list of lab unit IDs that a user is eligible for a specific role and disease.

**Parameters:**
- `db`: Database session
- `user_id` (int): The ID of the user
- `disease_id` (int): The disease ID
- `role_slot` (str): The role slot ('resident', 'resident2', or 'arbitrator')

**Returns:**
- List of eligible lab unit IDs or None if user has no eligibility

### `check_arbitration_eligibility(db, user_id: int, disease_id: int, lab_unit_id: int) -> UserDiseaseUnitRole | None`

Check if a user is eligible to arbitrate for a specific disease and lab unit.

**Parameters:**
- `db`: Database session (caller is responsible for closing)
- `user_id` (int): The ID of the user
- `disease_id` (int): The ID of the disease
- `lab_unit_id` (int): The ID of the lab unit

**Returns:**
- `UserDiseaseUnitRole` object if eligible, None otherwise

### `get_user_eligibility_for_task(db, user_id: int, task_id: int, role_slot: str) -> bool`

Check if a user is eligible for a specific role slot for a task.

**Parameters:**
- `db`: Database session (caller is responsible for closing)
- `user_id` (int): The ID of the user
- `task_id` (int): The ID of the task
- `role_slot` (str): The role slot ('resident', 'resident2', or 'arbitrator')

**Returns:**
- True if user is eligible, False otherwise

### `_has_user_graded_task_2weeks(db, user_id: int, task_id: int) -> bool`

Check if a user has graded a task in the past 2 weeks.

**Parameters:**
- `db`: Database session
- `user_id` (int): The ID of the user
- `task_id` (int): The ID of the task

**Returns:**
- True if user has graded the task in the past 2 weeks, False otherwise