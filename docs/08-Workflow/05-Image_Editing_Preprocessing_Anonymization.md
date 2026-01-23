---
title: Image Editing, Preprocessing & Anonymization Workflow
description: Post-ingestion lifecycle of direct uploads, including PII detection and edits.
last_updated: 2026-01-23
---
# Image Editing, Preprocessing & Anonymization Workflow

This workflow manages the lifecycle of direct image uploads after initial ingestion, including manual edits, automated PII detection, and final anonymization verification before grading tasks are created.

## List of Steps

### Phase 1: Initial Upload & Automated PII Detection
1.  **Upload**: User uploads an image via the direct upload form.
2.  **Storage**: System saves the original image to the file system.
3.  **PII Detection Enqueue**: System automatically enqueues a background PII detection job for the "orig" variant.
4.  **Background Processing**: 
    -   Worker fetches queued PII job.
    -   Performs OCR analysis to detect text (names, IDs, dates).
    -   Updates `ImagePiiVerification` table with status (`clear` or `detected`).

### Phase 2: Direct Image Editing (Optional)
5.  **Edit Request**: User saves an edited image (crop/mask) via `POST /direct/upload/save_image/<id>`.
6.  **Permission Check**: System verifies user permissions and lab unit access.
7.  **Task Lock Check**: System blocks editing if grading tasks are already in progress (unless override flag is set).
8.  **Save Edited Version**:
    -   Saves edited file to file system with `edited_` prefix.
    -   Generates new thumbnail for edited variant.
    -   Updates `DirectImageUpload` record with `edited_filename`.
9.  **Metadata Re-extraction**: Calls `extract_image_metadata` and `upsert_image_metadata` for the "edited" variant.
10. **PII Detection Re-enqueue**: Enqueues a new PII detection job specifically for the "edited" variant.
11. **Cache Invalidation**: Bumps media cache version to force browser refresh.

### Phase 3: Anonymization Verification (Manual)
12. **Dashboard View**: User views the preprocessing dashboard via `GET /preprocess/dashboard`.
    -   System displays pending images and statistics.
13. **Image Selection**: User selects an image for verification via `GET /preprocess/anonymize_image/<uuid>`.
    -   System fetches image and current verification status.
    -   Checks for grading task locks.
14. **Verification Decision**:
    -   **Mark Verified**: Updates `DirectImageVerify` status to `verified`, creates grading tasks via `ensure_task()`.
    -   **Mark Unverified**: Checks if tasks are in progress, updates status to `unverified`, removes pending grading tasks.
    -   **Restore Original**: Deletes edited file, clears `edited_filename` field.
15. **PII Override** (Optional): Admin can manually override PII status if automated detection is incorrect.

## Mermaid Workflow Diagram

```mermaid
sequenceDiagram
    participant User
    participant WebServer as Web Server (Flask)
    participant DB as Database
    participant FileSys as File System
    participant Worker as Background Worker
    participant OCR as OCR/PII Service

    note right of User: Phase 1: Initial Upload (Auto PII Detect)
    User->>WebServer: Upload Image
    WebServer->>FileSys: Save Original Image
    WebServer->>Worker: Enqueue PII Detection (Orig)
    
    loop PII Detection (Async)
        Worker->>DB: Fetch Queued PII Job
        Worker->>Worker: Mark Job Running
        Worker->>OCR: Detect PII (OCR Analysis)
        OCR-->>Worker: Return Detection Result
        Worker->>DB: Update ImagePiiVerification (Clear/Detected)
        Worker->>DB: Mark Job Completed
    end

    note right of User: Phase 2: Direct Image Editing (Optional)
    opt User edits image (Crop/Mask)
        User->>WebServer: Save Edited Image (POST /direct/upload/save_image/<id>)
        WebServer->>WebServer: Check Permissions (User ID, LabUnit)
        
        alt Grading Tasks In Progress
            WebServer-->>User: Error: Cannot Edit (Tasks In Progress)
        else Permissions OK
            WebServer->>FileSys: Save Edited Version (edited_<name>)
            WebServer->>FileSys: Generate Thumbnail (Edited)
            WebServer->>DB: Update DirectImageUpload (edited_filename)
            
            WebServer->>WebServer: Extract & Upsert Metadata (edited)
            WebServer->>Worker: Enqueue PII Detection (Edited)
            WebServer->>DB: Bump Media Cache Version
            WebServer-->>User: Success: Image Saved
        end
    end
    
    loop PII Detection for Edited Image (Async)
        Worker->>DB: Fetch Queued PII Job (Edited)
        Worker->>OCR: Detect PII
        OCR-->>Worker: Return Result
        Worker->>DB: Update ImagePiiVerification (Edited Variant)
        Worker->>DB: Mark Job Completed
    end

    note right of User: Phase 3: Anonymization Verification (Manual)
    User->>WebServer: View Dashboard (GET /preprocess/dashboard)
    WebServer->>DB: Fetch Pending Images & Stats
    WebServer-->>User: Render Dashboard List
    
    User->>WebServer: Select Image for Verification (GET /preprocess/anonymize_image/<uuid>)
    WebServer->>DB: Fetch Image & Verification Status
    WebServer->>DB: Check Grading Tasks (Locking)
    WebServer-->>User: Render Verification Page
    
    alt User Marks Verified
        User->>WebServer: Mark Verified (POST)
        WebServer->>DB: Update DirectImageVerify (Status: Verified)
        
        alt Image Verified Successfully
            WebServer->>DB: Create Grading Tasks (ensure_task)
            WebServer-->>User: Redirect to Next Unverified Image
        else Verification Failed
            WebServer->>DB: Rollback
            WebServer-->>User: Error: Verification Failed
        end
    else User Marks Unverified (or Restores Original)
        User->>WebServer: Mark Unverified / Restore (POST)
        WebServer->>DB: Check Can Unverify (Tasks Pending?)
        
        alt Tasks In Progress
            WebServer-->>User: Error: Cannot Unverify
        else OK to Unverify
            WebServer->>DB: Update DirectImageVerify (Status: Unverified)
            WebServer->>DB: Remove Pending Grading Tasks
            alt Restore Original Requested
                WebServer->>FileSys: Delete Edited File
                WebServer->>DB: Clear edited_filename (Restore Original)
            end
            WebServer-->>User: Success: Unverified / Restored
        end
    end
    
    opt PII Override (Manual Admin Action)
        User->>WebServer: Override PII Status (POST .../pii_override)
        WebServer->>DB: Update ImagePiiVerification (Source: Manual)
        WebServer-->>User: Success: PII Status Overridden
    end
```

## Key Components

1.  **Background PII Detection**:
    -   **Trigger**: Enqueued automatically after any image save (Upload via `upload.py`, Edit via `save_image.py`).
    -   **Process**: Uses OCR (`ocr_pii`) to scan for text (names, IDs, etc.) in images.
    -   **Result**: Stores `clear` or `detected` status in `ImagePiiVerification` table for both `orig` and `edited` image variants.

2.  **Direct Image Editing**:
    -   **Route**: `/direct/upload/save_image/<id>`
    -   **Functionality**: Allows users to crop, mask, or modify images post-upload.
    -   **Safety**: Blocks editing if grading tasks are already in progress (unless override flag is set).
    -   **Side Effects**: 
        -   Saves edited copy.
        -   Generates new thumbnail.
        -   **Metadata Re-extraction**: Calls `extract_image_metadata` and `upsert_image_metadata` for the "edited" variant.
        -   **PII Detection**: Enqueues a new detection job specifically for the "edited" variant.

3.  **Anonymization Verification**:
    -   **Purpose**: Manual confirmation that an image is safe (PII-free) for clinical use/dataset curation.
    -   **Route**: `/preprocess/anonymize_image/<uuid>`
    -   **Integration**:
        -   **Verify**: Creates `DirectImageVerify` record. If `verified`, triggers `ensure_task()` to create grading tasks.
        -   **Unverify**: Removes `DirectImageVerify` record and calls `remove_pending_tasks()` to delete any grading tasks.
    -   **Override**: Admins can manually override PII status (e.g., if PII detection is a false positive).

4.  **Locking Mechanisms**:
    -   **Task-Based Lock**: Editing/Unverification is blocked if grading tasks are in `assigned`, `completed`, etc. states (only allows `pending` or no tasks).
    -   **Override Flag**: Users can set a session flag (`allow_graded_edit`) to override locks, logging the action for audit.
