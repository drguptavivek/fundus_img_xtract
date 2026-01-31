# TDD and Testing Plan: Multi-Image Set Workflow

## 🧪 Testing Strategy
Following the project's **TDD** mandate, tests will be written *before* implementation for each task.

## 🛠️ Unit Tests (`tests/unit/`)

### 1. Schema & Models (Task 1)
- **Model Validation**: Ensure `EncounterSetImage` can be created with valid spatial positions (1-9).
- **Polymorphism Check**: Test `GradingTask` constraints. Verify that trying to save a task with zero links or multiple links (e.g., both `encounter_file_id` and `patient_encounter_id`) raises an `IntegrityError` or validation error.
- **Nullability**: Verify `PatientEncounters.zip_file_id` can be null.

### 2. API Ingestion (Task 2)
- **JWT Validation**: Test with valid, expired, and malformed tokens.
- **Scope Verification**: Ensure a token for Hospital A cannot upload images for Hospital B.
- **Metadata Stripping**: Upload an image with EXIF (GPS/Camera data) and verify it's gone in the stored version.
- **Duplicate Prevention**: Test that uploading the exact same file twice in one set is handled correctly.

## 🔗 Integration Tests (`tests/integration/`)

### 1. Workflow Orchestration (Task 5)
- **Celery Flow**: Mock Celery workers to verify that an API upload correctly triggers `process_encounter_set_image_task`.
- **State Transitions**: Verify that `PatientEncounters` moves to `ready_for_verification` only after *all* images in the set are marked as processed.

### 2. Grading Workflow (Task 4)
- **Task Creation**: Verify that verifying an encounter-set creates exactly one `GradingTask`.
- **Consensus Logic**: Test that submitting grades for an encounter-set task correctly populates the `Consensus` model.

## 🛡️ Security Tests (`tests/security/`)

### 1. PII Leakage
- **OCR Alerting**: Verify that images with obvious text (e.g., "Name: John Doe") are flagged by the `encounter_set_pii_check_task`.
- **Media Access**: Ensure images from `EncounterSetImage` are *only* accessible via signed UUID URLs and not direct paths.

## 🎭 E2E Tests (Playwright)

### 1. Verification UI (Task 3)
- **Grid Reordering**: Simulate dragging position 2 to position 1 and verify the update.
- **Editor Integration**: Open the editor from the grid, apply a mask, save, and verify the thumbnail updates.

### 2. Sync-Grid Grading (Task 4)
- **Synchronized View**: Verify that zooming on one image triggers a zoom event on the others (mocking coordinates).
