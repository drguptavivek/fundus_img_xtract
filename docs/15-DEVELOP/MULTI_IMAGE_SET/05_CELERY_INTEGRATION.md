# Task 5: Celery Background Processing

## ⚙️ Rationale
Multi-image sets (up to 9 high-res images) can significantly slow down the API response if processed synchronously. Backgrounding these tasks ensures the mobile app gets immediate confirmation while the server works on heavy lifting.

## 🏗️ New Background Tasks
Create `celery_tasks/tasks/encounter_set_tasks.py`.

### 1. `process_encounter_set_image_task`
**Queue**: `thumbnails` | `metadata`
- **Input**: `encounter_set_image_id`.
- **Actions**:
  - Strip EXIF/IPTC metadata.
  - Generate 200px thumbnails for grid.
  - Calculate MD5 file hash for duplicate detection.
  - Update `EncounterSetImage` record.

### 2. `encounter_set_pii_check_task`
**Queue**: `pii_detection`
- **Input**: `encounter_set_image_id`.
- **Actions**:
  - Run Tesseract OCR on the image.
  - Flag images containing text patterns (Dates, Names, IDs).
  - Update a `pii_flag` on the record to alert the Optometrist.

### 3. `encounter_set_coordinator_task`
**Queue**: `default`
- **Input**: `patient_encounter_id`.
- **Actions**:
  - Monitor the state of all images in the set.
  - Once all images are "Processed", update `PatientEncounters.processing_state = 'ready_for_verification'`.
  - Send a notification to assigned Optometrists.

## 🔗 Trigger Points
- **API Upload**: Immediately after saving the files, the API will trigger the `process` and `pii` tasks for each image.
- **Verification UI**: Re-trigger tasks if an image is replaced or re-ordered significantly.

## 🛠️ Celery Routes
Update `celery_app.py` to route these tasks to efficient queues:
```python
"celery_tasks.tasks.encounter_set_tasks.process_encounter_set_image_task": {"queue": "thumbnails"},
"celery_tasks.tasks.encounter_set_tasks.encounter_set_pii_check_task": {"queue": "pii_detection"},
"celery_tasks.tasks.encounter_set_tasks.encounter_set_coordinator_task": {"queue": "default"},
```
