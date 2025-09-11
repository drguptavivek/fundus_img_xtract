# Task Creation Services Implementation

This document describes the implementation of the Task Creation Services for the dual grading system.

## Overview

The Task Creation Services are responsible for automatically creating `GradingTask` entries when images are officially verified. This is a critical part of the automated workflow that ensures verified images enter the grading flow.

## Implementation Details

### 1. Service Functions

The core functionality is implemented in `/services/taskCreationServices.py`:

- `_resolve_image_by_uuid(db, image_uuid)`: Resolves an image by UUID to determine if it's a direct image or encounter file
- `_is_verified_for_disease(db, kind, image_id, disease_id)`: Checks if an image is verified for a specific disease
- `can_unverify_image(db, *, kind, image_id)`: Checks if an image can be unverified (all tasks are pending)
- `create_or_get_task(db, *, kind, image_id, disease_id, lab_unit_id)`: Creates a grading task or returns an existing one
- `remove_pending_tasks(db, *, kind, image_id)`: Removes all pending grading tasks for an image
- `ensure_task(image_uuid, disease_id)`: Main entry point that resolves, verifies, and creates tasks

### 2. Grading Task States

Grading tasks can be in one of five states:
1. **pending** - Initial state when a task is created
2. **resident_done** - When a resident has submitted their grade
3. **faculty_done** - When a faculty member has submitted their grade
4. **arbitration** - When resident and faculty grades don't match and the task needs arbitration
5. **final** - When a consensus has been reached (either through matching grades or arbitration)

### 3. Auto-Creation Hooks

Hooks have been added to the verification flows to automatically create grading tasks:

1. **Direct Image Verification** (`preprocess/anonymize_image.py`):
   - When a direct image is marked as "verified", a grading task is automatically created for its native disease
   - When a direct image is marked as "unverified", all pending grading tasks are automatically removed (if all tasks are pending)

2. **DR Verification** (`verify_remedio_dr/routes.py`):
   - When an encounter is marked as DR-verified, grading tasks are created for all images in the encounter for DR disease
   - When an encounter is marked as DR-unverified, unverification is prevented if any image has non-pending tasks, otherwise all pending grading tasks are automatically removed

3. **Glaucoma Verification** (`glaucoma/routes.py`):
   - When an encounter is marked as Glaucoma-verified, grading tasks are created for all images in the encounter for Glaucoma disease
   - When an encounter is marked as Glaucoma-unverified, unverification is prevented if any image has non-pending tasks, otherwise all pending grading tasks are automatically removed

### 4. API Endpoints

RESTful API endpoints have been added in `/api/tasks.py`:

- `POST /api/tasks/ensure`: Idempotently create or return a grading task for an image UUID and disease
- `GET /api/tasks/next`: Returns the next eligible task for a user based on their role and eligibility
- `POST /api/tasks/submit`: Submit a grade for a task

## Key Features

1. **Idempotency**: The `create_or_get_task` function ensures that only one task exists per image×disease globally
2. **Verification Gating**: Tasks are only created for verified images
3. **Task Cleanup**: Pending tasks are automatically removed when verification status changes to unverified
4. **Safety Checks**: Images cannot be unverified if any of their tasks are in a non-pending state
5. **Multi-disease Support**: An image can have tasks for multiple diseases, all are handled appropriately
6. **Eligibility Checking**: API endpoints validate user eligibility for specific grading slots
7. **Error Handling**: Graceful handling of various error conditions with appropriate HTTP status codes
8. **Logging**: Comprehensive logging for debugging and audit purposes

## Testing

Unit tests have been added in `/tests/test_task_creation_services.py` to verify the functionality of all service functions including the new task removal and safety check functionality.

## Future Enhancements

1. Add support for additional diseases beyond DR and Glaucoma
2. Implement more sophisticated task selection algorithms for the "next task" endpoint
3. Add bulk task creation and removal utilities for administrative tasks
4. Implement more comprehensive state transition logic for grading tasks