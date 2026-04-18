# Wadhwani Glaucoma Integration

## Stages

### Stage 1: Camera Foundations and ZIP Upload Support

- Add `Camera.is_zip_upload_enabled`
- Add `EncounterFile.camera_id`
- Extend Camera Master CRUD with `Enable ZIP uploads`
- Add `Remedio Pristine` camera to master data
- ZIP upload must require a ZIP-enabled camera
- ZIP batch metadata must persist `camera_id`
- ZIP processor must write `camera_id` to created `EncounterFile` rows

### Stage 2: Shared Wadhwani Inference Service

- Add a shared single-task runner:
  - `run_task_inference(task_id, requested_by_user_id, force=False)`
- Add an internal batch-ready orchestrator:
  - `run_task_batch(task_ids, requested_by_user_id, force=False, stop_on_error=False)`
- Support only glaucoma tasks tied to one concrete image:
  - `encounter_file_id`
  - `direct_image_upload_id`
- Reject encounter-set tasks:
  - `patient_encounter_id`
- Use linked `AIModelIntegration(provider='wadhwani_glaucoma')`
- Persist real attempts in `AIInferenceRun`
- Persist successful output in `Grade`
- Save AI grades under `ai_system`
- Reuse successful existing inference by default instead of replaying remote steps

### Stage 3: Internal Trigger API

- Add:
  - `POST /api/ai-models/wadhwani-glaucoma/tasks/<task_id>/infer`
- Roles:
  - `admin`
  - `local_admin`
  - `data_manager`
- Request:
  - `force`
- Responses:
  - success
  - skipped/reused existing
  - failed with `error_code`

## Clarification: Encounter-Set Tasks

`patient_encounter_id` means the task is tied to an encounter set, not one concrete image.

These tasks may have multiple related images that need to be interpreted together. The current Wadhwani integration is image-based, so Phase 1 rejects encounter-set tasks until set-aware inference logic is designed.

## Key Defaults

- `ai_system` is the canonical writer for AI grades
- successful prior inference is reused by default
- no rerun should replay initialize/upload/execute if reusable success data already exists
- Wadhwani result maps to:
  - `Normal`
  - `Glaucoma`
