---
title: Zip Upload Workflow
description: Batch ingestion of image and PDF clinical data via Zip files.
last_updated: 2026-01-23
---
# Zip Upload Workflow

This workflow describes the process of ingesting large batches of images and PDFs via Zip files.

```mermaid
sequenceDiagram
    participant User
    participant WebServer as Web Server (Flask)
    participant DB as Database
    participant FileSystem as File System
    participant Worker as Background Worker
    participant ZipProcessor as Zip Processor
    participant OCR as OCR Service

    User->>WebServer: Upload Zip File (POST /remedio_zip_uploads/upload)
    WebServer->>WebServer: Validate Request (Size, Ext, LabUnit)
    alt Validation Failed
        WebServer-->>User: Error Flash Message
    else Validation Success
        WebServer->>FileSystem: Save Zip to UPLOAD_DIR
        WebServer->>DB: Create Job (Status: Queued)
        WebServer->>Worker: Queue Job (ThreadPool)
        WebServer-->>User: Redirect to Job Status Page
    end

    loop Background Processing
        Worker->>DB: Update Job Status (Processing)
        Worker->>ZipProcessor: Process Zip File
        
        ZipProcessor->>FileSystem: Read Zip
        ZipProcessor->>DB: Check Duplicate (MD5)
        
        alt Is Duplicate
            ZipProcessor->>FileSystem: Move to Dup Dir
            Worker->>DB: Mark Item Error (Duplicate)
        else Is Unique
            loop For Each File in Zip
                ZipProcessor->>ZipProcessor: Validate File Type & Path
                
                alt Image (JPG/JPEG)
                    ZipProcessor->>FileSystem: Extract & Strip EXIF
                    ZipProcessor->>FileSystem: Generate Thumbnail
                    ZipProcessor->>DB: Create EncounterFile
                    ZipProcessor->>DB: Extract & Upsert Metadata
                    ZipProcessor->>DB: Enqueue PII Detection
                else PDF
                    ZipProcessor->>FileSystem: Extract PDF
                    ZipProcessor->>DB: Create EncounterFilePDF
                end
            end
            
            ZipProcessor->>DB: Create PatientEncounters (from Dir Structure)
            ZipProcessor->>FileSystem: Move Zip to Processed Dir
            ZipProcessor-->>Worker: Return Extracted PDF List
            
            opt Has PDFs
                Worker->>OCR: Process PDFs for OCR
                OCR->>DB: Update OCR Data
            end
            
            Worker->>DB: Update Job Status (Done)
        end
    end
```

## Key Components

1.  **Validation**: strict checks on file extension (`.zip`), size limits, and user permissions (RBAC/ABAC).
2.  **Job System**: Asynchronous processing using `ThreadPoolExecutor`. The user receives immediate feedback via a Job Token.
3.  **Zip Processor**:
    -   **Structure Requirement**: Folders inside Zip must follow `Name_ID_Date` format to auto-create Patient Encounters.
    -   **Security**: Checks for "zip slip" vulnerabilities (path traversal) and strictly allows only specific extensions.
    -   **Deduplication**: Uses MD5 hashing to prevent re-processing identical files.
    -   **Image Processing**: 
        -   Strips EXIF data and generates thumbnails.
        -   **Metadata Extraction**: Performs synchronous extraction (dimensions, format, average luminance, etc.) using `utils/image_metadata.py`.
        -   **PII Detection**: Enqueues an asynchronous detection job for each extracted image via `utils/pii_detection_queue.py`.
4.  **OCR Integration**: If PDFs are found, they are passed to the OCR service for text extraction.
