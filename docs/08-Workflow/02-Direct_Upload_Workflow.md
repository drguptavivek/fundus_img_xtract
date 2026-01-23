---
title: Direct Upload Workflow
description: Manual image upload and editing workflow for non-batch data.
last_updated: 2026-01-23
---
# Direct Upload Workflow

This workflow describes the process for users to manually upload specific images (non-batch) directly via the web interface.

```mermaid
sequenceDiagram
    participant User
    participant WebServer as Web Server (Flask)
    participant DB as Database
    participant FileSystem as File System
    participant ImageProc as Image Processor
    participant PII as PII Service
    participant JobSystem as Job System

    User->>WebServer: Submit Upload Form (POST /direct/upload)
    WebServer->>WebServer: Validate Form (Fields, Quota)
    
    alt Validation Failed
        WebServer-->>User: Error Flash Message
    else Validation Success
        WebServer->>DB: Create Job (Status: Processing)
        
        loop For Each File
            WebServer->>WebServer: Validate Filename & MimeType
            WebServer->>WebServer: Calculate Hash (MD5)
            WebServer->>DB: Check Duplicate
            
            alt Is Duplicate
                WebServer->>FileSystem: Save to Dup Dir
                WebServer->>JobSystem: Add Job Item (Error: Duplicate)
            else Is Unique
                WebServer->>ImageProc: Strip EXIF Data
                WebServer->>FileSystem: Save Original Image
                WebServer->>ImageProc: Generate Thumbnail
                WebServer->>FileSystem: Save Thumbnail
                
                WebServer->>DB: Create DirectImageUpload Record
                WebServer->>DB: Extract & Upsert Metadata (orig)
                WebServer->>PII: Enqueue PII Detection (orig)
                WebServer->>JobSystem: Add Job Item (Completed)
            end
        end
        
        WebServer->>DB: Update Job Status (Completed/Error)
        WebServer->>Worker: Trigger Thumbnail Regen (Background)
        WebServer-->>User: Redirect to Job Status Page
    end
    
    opt Edit Image (Post-Upload)
        User->>WebServer: Save Edited Image (POST /direct/upload/save_image/<id>)
        WebServer->>FileSystem: Save Edited File
        WebServer->>ImageProc: Generate Edited Thumbnail
        WebServer->>DB: Update DirectImageUpload (Edited Filename)
        WebServer->>PII: Enqueue PII Detection (Edited)
    end
```

## Key Components

1.  **Quota Management**: Checks both user-specific and system-wide upload quotas (`DIRECT_UPLOAD_LIFETIME_QUOTA`) before processing.
2.  **Synchronous Processing**: Unlike Zip uploads, direct uploads are processed synchronously within the request.
    -   **Metadata Extraction**: Performed immediately after EXIF stripping using `extract_image_metadata`. Results are stored in the `ImageMetadata` table for the "orig" variant.
    -   **PII Detection**: Enqueued as an asynchronous job using `enqueue_pii_detection`.
3.  **Security**:
    -   **Validation**: Strict filename validation (sanitization) and MIME type checking (magic bytes).
    -   **Hashing**: Uses MD5 to detect duplicates.
    -   **EXIF Stripping**: Removes potentially sensitive metadata from images before storage (`utils.image_processing.strip_exif_data`).
4.  **Editing**: Users can edit images (e.g., crop, mask) after upload.
    -   Saving an edited image triggers a **re-extraction of metadata** and a **new PII detection job** specifically for the "edited" variant.
