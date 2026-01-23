# Image Editing, Preprocessing & Anonymization Workflow

This workflow manages the lifecycle of direct image uploads after initial ingestion, including manual edits, automated PII detection, and final anonymization verification before grading tasks are created.

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
            
            opt Metadata Extraction
                WebServer->>WebServer: Extract Metadata (Dimensions, EXIF)
                WebServer->>DB: Upsert ImageMetadata
            end
            
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
    -   **Trigger**: Enqueued automatically after any image save (Upload, Edit).
    -   **Process**: Uses OCR (`ocr_pii`) to scan for text (names, IDs, etc.) in images.
    -   **Result**: Stores `clear` or `detected` status in `ImagePiiVerification` table for both `orig` and `edited` image variants.

2.  **Direct Image Editing**:
    -   **Route**: `/direct/upload/save_image/<id>`
    -   **Functionality**: Allows users to crop, mask, or modify images post-upload.
    -   **Safety**: Blocks editing if grading tasks are already in progress (unless override flag is set).
    -   **Side Effects**: Saves edited copy, generates new thumbnail, re-runs metadata extraction, and queues PII detection for the edited version.

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
