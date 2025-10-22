# Dual Grading Utility Functions - Updated API

This document describes the updated API for dual grading utility functions.

## Functions for Cross-Lab Unit Operations

These functions calculate totals across all lab units where a user has eligibility for a specific disease:

- `get_all_pending_resident_for_disease(user_id: int, disease_id: int) -> Dict[str, int]`
  - Get total pending resident tasks for a user and disease across all eligible lab units
  - For admin users, returns totals across ALL lab units

- `get_all_pending_resident2_for_disease(user_id: int, disease_id: int) -> Dict[str, int]`
  - Get total pending resident2 tasks for a user and disease across all eligible lab units
  - For admin users, returns totals across ALL lab units

- `get_all_pending_arbitration_for_disease(user_id: int, disease_id: int) -> Dict[str, int]`
  - Get total pending arbitration tasks for a user and disease across all eligible lab units
  - For admin users, returns totals across ALL lab units

## Functions for Specific Lab Unit Operations

These functions work with specific lab unit and disease combinations:

- `get_all_pending_resident_for_labUnit_disease(user_id: int, lab_unit_id: int, disease_id: int) -> Dict[str, Optional[int]]`
  - Get all pending resident tasks for a user, lab unit, and disease

- `get_all_pending_resident2_for_labUnit_disease(user_id: int, lab_unit_id: int, disease_id: int) -> Dict[str, Optional[int]]`
  - Get all pending resident2 tasks for a user, lab unit, and disease

- `get_all_pending_arbitration_for_labUnit_disease(user_id: int, lab_unit_id: int, disease_id: int) -> Dict[str, Optional[int]]`
  - Get all pending arbitration tasks for a user, lab unit, and disease

## Other Utility Functions

- `get_user_eligibility_for_task(user_id: int, task_id: int, role_slot: str) -> bool`
  - Check if a user is eligible for a specific role slot for a task

- `get_next_eligible_task(user_id: int, role_slot: str, lab_unit_id: Optional[int] = None, disease_id: Optional[int] = None) -> Optional[GradingTask]`
  - Get the next eligible task for a user and role slot

- `get_user_pending_tasks_summary(user_id: int) -> Dict[str, Dict[str, int]]`
  - Get a summary of all pending tasks for a user across all diseases