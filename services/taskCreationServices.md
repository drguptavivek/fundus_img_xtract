# Task Creation Services Documentation

## Overview

The `taskCreationServices.py` module provides core functionality for managing grading tasks in the fundus image management system. It handles the creation, verification, and management of grading tasks for retinal images, ensuring proper workflow control and data integrity.

## Module Dependencies

```python
from sqlalchemy import select, exists, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from typing import Optional, Tuple

from models import (
    Session, GradingTask, Grade, Consensus, DirectImageUpload, DirectImageVerify,
    EncounterFile, PatientEncounters, Disease, DiseaseGrading, LabUnit
)
```

## Core Functions

### `_resolve_image_by_uuid(db, image_uuid: str) -> Tuple[str, int, int]`

**Purpose**: Resolves an image by its UUID to determine its type and retrieve essential identifiers.

**Parameters**:
- `db`: Database session
- `image_uuid`: UUID of the image to resolve

**Returns**: Tuple of `(kind, image_id, lab_unit_id)` where:
- `kind`: String indicating image type ('direct' or 'encounter')
- `image_id`: Integer ID of the image
- `lab_unit_id`: Integer ID of the associated lab unit

**Raises**: `ValueError` if the image is not found

**Implementation Details**:
- First checks if the image is a `DirectImageUpload`
- If not found, checks if the image is an `EncounterFile`
- Raises `ValueError` if neither type matches

### `_is_verified_for_disease(db, kind: str, image_id: int, disease_id: int) -> bool`

**Purpose**: Checks if an image is verified for a specific disease based on verification policies.

**Parameters**:
- `db`: Database session
- `kind`: Image type ('direct' or 'encounter')
- `image_id`: ID of the image
- `disease_id`: ID of the disease

**Returns**: Boolean indicating verification status

**Implementation Details**:
- For 'direct' images: Checks `DirectImageVerify.verified_status == 'verified'`
- For 'encounter' images:
  - DR (Diabetic Retinopathy): Checks `PatientEncounters.dr_verified_status == 'verified'`
  - Glaucoma: Checks `PatientEncounters.glaucoma_verified_status == 'verified'`
  - Other diseases: Returns `False` (policy not yet implemented)

### `can_unverify_image(db, *, kind: str, image_id: int) -> bool`

**Purpose**: Determines if an image can be unverified by checking if all associated tasks are pending.

**Parameters**:
- `db`: Database session
- `kind`: Image type ('direct' or 'encounter')
- `image_id`: ID of the image

**Returns**: Boolean indicating if the image can be unverified

**Implementation Details**:
- Retrieves all grading tasks associated with the image
- Returns `True` only if all tasks are in 'pending' state or if no tasks exist
- Raises `ValueError` for invalid image kind

### `create_or_get_task(db, *, kind: str, image_id: int, disease_id: int, lab_unit_id: int) -> GradingTask`

**Purpose**: Idempotently creates or retrieves a grading task for an image-disease combination.

**Parameters**:
- `db`: Database session
- `kind`: Image type ('direct' or 'encounter')
- `image_id`: ID of the image
- `disease_id`: ID of the disease
- `lab_unit_id`: ID of the lab unit

**Returns**: `GradingTask` object

**Key Features**:
- **Idempotency**: Ensures only one task exists per image×disease globally
- **Immutability**: Never mutates `lab_unit_id` of existing tasks
- **Final State Protection**: Does not allow reassignment of tasks in 'final' state

**Preconditions** (caller must validate):
- Image exists and is not locked
- Image is verified for the disease

### `remove_pending_tasks(db, *, kind: str, image_id: int) -> int`

**Purpose**: Removes all pending grading tasks associated with an image.

**Parameters**:
- `db`: Database session
- `kind`: Image type ('direct' or 'encounter')
- `image_id`: ID of the image

**Returns**: Integer count of removed tasks

**Implementation Details**:
- Only removes tasks in 'pending' state
- Commits changes only if at least one task was removed
- Raises `ValueError` for invalid image kind

### `ensure_task(image_uuid: str, disease_id: int) -> GradingTask`

**Purpose**: Main entry point that resolves an image, verifies it, and creates/retrieves a grading task.

**Parameters**:
- `image_uuid`: UUID of the image
- `disease_id`: ID of the disease

**Returns**: `GradingTask` object

**Implementation Details**:
- Resolves image by UUID using `_resolve_image_by_uuid`
- Checks if image is locked (raises `PermissionError` if locked)
- Verifies image is verified for the disease using `_is_verified_for_disease`
- Creates or retrieves task using `create_or_get_task`
- **Cross-Lab Protection**: Raises `PermissionError` if trying to access a finalized task from a different lab

## Key Design Patterns

### 1. Idempotency
The service ensures that operations can be safely repeated without causing unintended effects. This is particularly important for task creation, where duplicate tasks could cause confusion in the grading workflow.

### 2. Verification Gating
Tasks are only created for images that have been properly verified for the specific disease. This ensures that only qualified images enter the grading pipeline.

### 3. State Protection
Once a task reaches the 'final' state, it becomes immutable and cannot be reassigned to different lab units, preserving the integrity of the consensus grading.

### 4. Safety Checks
The service includes multiple safety checks to prevent data loss and maintain workflow integrity, such as preventing unverification of images with active grading tasks.

## Error Handling

The service uses specific exceptions to indicate different error conditions:
- `ValueError`: Invalid parameters or missing data
- `PermissionError`: Access denied due to locks, verification status, or cross-lab restrictions

## Usage Examples

### Creating a Task for a Verified Image
```python
# Ensure a task exists for a verified image
try:
    task = ensure_task(image_uuid="123e4567-e89b-12d3-a456-426614174000", disease_id=1)
    print(f"Task {task.id} is ready for grading")
except PermissionError as e:
    print(f"Cannot create task: {e}")
```

### Checking if an Image Can Be Unverified
```python
with Session() as db:
    kind, image_id, _ = _resolve_image_by_uuid(db, "123e4567-e89b-12d3-a456-426614174000")
    if can_unverify_image(db, kind=kind, image_id=image_id):
        print("Image can be safely unverified")
    else:
        print("Image has active grading tasks and cannot be unverified")
```

## Integration Points

This service integrates with:
1. **Verification Flows**: Automatically creates tasks when images are verified
2. **API Endpoints**: Used by `/api/tasks/ensure` and related endpoints
3. **Grading Workflows**: Provides tasks for the dual grading system
4. **Administrative Functions**: Supports task management and cleanup operations

## Relationship to Other Documentation

This module is documented at a higher level in `docs/task_creation_services.md`, which describes:
- The overall implementation in the context of the dual grading system
- Auto-creation hooks in verification flows
- API endpoints that use these services
- Testing strategies

This file provides detailed API documentation for developers working directly with the service functions.

## Future Enhancements

1. **Additional Disease Support**: Extend verification policies for more diseases
2. **Bulk Operations**: Add support for bulk task creation and removal
3. **Advanced Task Selection**: Implement more sophisticated task allocation algorithms
4. **Audit Logging**: Add comprehensive audit trail for task operations