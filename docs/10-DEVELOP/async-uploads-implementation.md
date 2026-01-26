# Async Upload Workflows - Implementation Plan

**Date:** 2026-01-26
**Status:** Planning (Refined)
**Scope:** Make ZIP, direct, and pregraded uploads async with local-first S3 sync architecture.

---

## Overview

Transform upload workflows from **synchronous blocking** to **fully async** with **local-first S3 sync**.
**Key Design Principles:**
- **All-or-Nothing Safety:** ZIPs are validated entirely before partial processing.
- **Immediate Visuals:** Priority on Thumbnails and OCR to unblock the UI.
- **Chained Processing:** Heavy metadata tasks happen *after* visual assets are ready.
- **Local-First:** Data stays local until scheduled S3 sync (8-hour delay).
- **Burst Protection:** Atomic DB writes followed by distributed task execution.

---

## Architecture: ZIP Upload Workflow

The ZIP upload workflow implements the **Coordinator & Chain** and **Job Store** patterns defined in [Celery Integration Guide](celery-integration.md).

### 1. The ZIP Coordinator
**Action:** `process_zip_coordinator_task` (Celery Worker)
1.  **Unzip & Validate (In-Memory/Temp):**
    *   Iterate *every* file.
    *   Check: Magic bytes (PDF/JPG), Extensions, Path Traversal.
    *   **Decision:** If **ANY** file is invalid/malicious $\rightarrow$ Reject **ENTIRE** ZIP. (0 DB writes).
2.  **Atomic Persistence:**
    *   Move files to local `files/` directory.
    *   Create `PatientEncounter`, `EncounterFiles`, `Job` in **one single DB transaction**.
3.  **Dynamic Job Tracking:**
    *   Calls `db_add_job_items` to register extracted files in the Job UI.
    *   Marks the original ZIP item as `ok` ("Extracted X files").
4.  **Fan-Out (Chained):**
    *   For each image, triggers a **Chain**: `process_image_thumbnail_task` $\rightarrow$ `process_file_metadata_strip_task`.
    *   For each PDF, triggers `process_pdf_ocr_task`.

### 2. Task Details

**Visual Task (Priority)**
*   **Images:** `process_image_thumbnail_task`
    *   Resize & Save Thumbnail.
    *   Update DB: `thumbnail_filename`.
    *   Update Item State: "Thumbnail generated".
*   **PDFs:** `process_pdf_ocr_task` (Terminal Task)
    *   Extract text via OCR.
    *   Update DB: clinical data.
    *   **Completion:** Calls `check_and_complete_job(job_token)`.

**Data Task (Background / Terminal)**
*   **Triggered by:** Completion of `process_image_thumbnail_task`.
*   **Action:** `process_file_metadata_strip_task`
    *   Read original file.
    *   Extract EXIF/IPTC $\rightarrow$ Save to `ImageMetadata` table (with explicit `commit()`).
    *   **Strip EXIF/IPTC** from the file on disk (Anonymize).
    *   **Completion:** Calls `check_and_complete_job(job_token)` to finalize the job status.

---

## Detailed Implementation Phases

### Phase 1: ZIP Upload Async (Refined)
**Status:** Completed

**Modifications:**
*   `zip_processor.py`: Refactor `process_zip_file` to split "Validation" from "DB Creation" (`ingest_zip_atomic`).
*   `celery_job_store.py`: New job management logic for tracking extracted files.
*   `celery_tasks/tasks/zip_upload_tasks.py`: Implementation of Coordinator and Chained tasks.
*   `worker.py`: Updated to call the coordinator task.

### Phase 2: Direct Upload Async
**Status:** Pending (In Progress)

**Adjustments for Direct Uploads:**
*   **Validation:** Happens synchronously in the Flask Route (since it's one file).
*   **Flow:**
    1.  Route: Validate $\rightarrow$ Save to Disk $\rightarrow$ Create DB Record $\rightarrow$ Return "OK".
    2.  Route: Enqueue `chain(visual_task.s(), metadata_task.s(), pii_task.s())`.
    *   *Note:* Direct uploads **DO** require PII detection (unlike ZIPs).

### Phase 3: Pregraded Upload Async
**Status:** Pending

**Logic:**
- Refactor `direct_uploads/pregraded.py` to use the coordinator/chain pattern.
- Ensure large pregraded ZIPs are handled asynchronously to prevent timeout.

### Phase 4: S3 Batch Sync
**Status:** Independent Implementation (In Progress)

**Logic:**
*   **Job:** `sync_unsync_files_to_s3_batch_task`
*   **Target:** `DirectImageUpload` and `EncounterFile` where `s3_object_key` is NULL.
*   **Safety:** Do not delete local file immediately. Mark `s3_verified_at`.
*   **Cleanup:** Separate task deletes local files where `s3_verified_at < (Now - 24h)`.


---

## Database Impact Analysis

| Operation | Previous Plan (Naive) | Current Plan (Atomic) |
| :--- | :--- | :--- |
| **ZIP Ingestion (100 files)** | 100 DB Inserts (Spread out) | **1 Bulk Insert Transaction** |
| **Thumbnailing** | 100 Updates | 100 Updates (Distributed) |
| **Metadata** | 100 Inserts | 100 Inserts (Distributed) |
| **Risk** | Partial state if worker dies | Consistent state (Files exist or don't) |

## Updated File Structure

```text
celery_tasks/
├── tasks/
│   ├── zip_upload_tasks.py      # Coordinator & Visual Tasks
│   ├── metadata_tasks.py        # Extract & Strip Logic
│   ├── s3_sync_tasks.py         # Batch Sync
│   └── ...
utils/
├── upload_coordinator.py        # Shared validation logic
└── ...
```

## Performance Targets
*   **ZIP Acceptance:** < 5s (Validation only).
*   **Thumbnail Visibility:** ~1s per image (Parallel workers).
*   **Full Metadata:** Background processing (Does not block UI).