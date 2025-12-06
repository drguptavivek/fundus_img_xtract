# Dual Grading KPIs Utilities Documentation

This document provides an overview of the utility functions available in the dual grading KPIs module. These utilities are designed for tracking key performance indicators in the dual grading system.

## Module Overview

This module provides functions for retrieving KPI data for dual grading operations, specifically tracking pending and completed tasks across different roles and diseases for each user.

## Functions

### `get_user_kpi_pending_task_count_data(db, user_id: int) -> Dict[str, Dict[str, int]]`

Get KPI data for each core disease for pending tasks across all mapped lab units for each slot of a user.

This function provides a comprehensive view of pending tasks by disease for all eligible slots (resident, resident2, arbitration) across all lab units where the user has eligibility.

**Parameters:**
- `db`: Database session (caller is responsible for closing)
- `user_id` (int): The ID of the user

**Returns:**
- `Dict[str, Dict[str, int]]`: A dictionary with disease names as keys and slot counts as values:
```python
{
    'Disease Name': {
        'resident_pending': count,
        'resident2_pending': count,
        'arbitration_pending': count
    },
    ...
}
```

**Implementation Details:**
- Gets the user with their roles
- Retrieves all diseases and maps IDs to names
- Gets user's eligible roles with lab units and permissions
- Groups eligible lab units by disease
- Counts tasks based on state and role:
  - Resident pending: tasks in 'pending' state for which user doesn't have a resident grade
  - Resident2 pending: tasks in 'resident_done' state for which user doesn't have a resident2 grade
  - Arbitration pending: tasks in 'arbitration' state that user hasn't graded recently
- Excludes tasks that the user has already completed in the appropriate role

### `get_user_kpi_completed_task_count_data(db, user_id: int) -> Dict[str, Dict[str, int]]`

Get KPI data for each core disease for completed tasks across all mapped lab units for each slot of a user.

This function provides a comprehensive view of completed tasks by disease for all eligible slots (resident, resident2, arbitration) across all lab units where the user has eligibility.

**Parameters:**
- `db`: Database session (caller is responsible for closing)
- `user_id` (int): The ID of the user

**Returns:**
- `Dict[str, Dict[str, int]]`: A dictionary with disease names as keys and slot counts as values:
```python
{
    'Disease Name': {
        'resident_completed': count,
        'resident2_completed': count,
        'arbitration_completed': count
    },
    ...
}
```

**Implementation Details:**
- Gets the user with their roles
- Retrieves all diseases and maps IDs to names
- Gets diseases where user has actually completed gradings
- Counts completed tasks by role:
  - Resident completed: number of grades with role_slot 'resident' for the user in each disease
  - Resident2 completed: number of grades with role_slot 'resident2' for the user in each disease
  - Arbitration completed: number of grades with role_slot 'arbitrator' for the user in each disease
- Returns empty dictionary if the user hasn't completed any gradings