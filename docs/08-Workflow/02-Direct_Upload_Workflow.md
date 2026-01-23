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
            WebServer->>WebServer: Calculate Hash (SHA-256)
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
                WebServer->>DB: Upsert Image Metadata
                WebServer->>PII: Enqueue PII Detection
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
2.  **Synchronous Processing**: Unlike Zip uploads, direct uploads are processed synchronously within the request (though PII detection is enqueued). The "Job" record is used for consistency in status tracking.
3.  **Security**:
    -   **Validation**: Strict filename validation (sanitization) and MIME type checking (magic bytes).
    -   **Hashing**: Uses SHA-256 (truncated) to detect duplicates.
    -   **EXIF Stripping**: Removes potentially sensitive metadata from images before storage.
4.  **Editing**: Users can edit images (e.g., crop, mask) after upload. This creates a separate "edited" variant while preserving the original.
