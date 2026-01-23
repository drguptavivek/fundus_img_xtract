---
title: Zip Upload Workflow
description: Batch ingestion of image and PDF clinical data via Zip files.
last_updated: 2026-01-23
---
# Zip Upload Workflow

This workflow describes the process of ingesting large batches of images and PDFs via Zip files.

## List of Steps

1.  **Submission**: User selects a Lab Unit and uploads a Zip file via `POST /remedio_zip_uploads/upload`.
2.  **Initial Validation**: 
    -   Checks file extension (must be `.zip`).
    -   Validates file size against `PER_FILE_MAX_BYTES` setting.
    -   Skips macOS resource forks (files starting with `._`).
3.  **Job Creation**: 
    -   Generates a unique job token (UUID).
    -   Saves the Zip to a date-stamped folder in `UPLOAD_DIR`.
    -   Creates a sidecar `.json` metadata file in `upload_meta/` containing uploader ID, username, client IP, and User-Agent.
    -   Creates a `Job` record in the database with status `queued`.
4.  **Worker Trigger**: Background worker picks up the job and starts processing using `ZipProcessor`.
5.  **Integrity & Security Checks**:
    -   **Deduplication**: Calculates MD5 hash of the entire Zip and checks against the `ZipFile` table to prevent re-processing duplicates.
    -   **Path Traversal Protection**: Checks for "zip slip" vulnerabilities during extraction.
    -   **Extension Whitelisting**: Strictly filters extraction to `.pdf`, `.jpg`, and `.jpeg`.
    -   **Magic-byte Sniffing**: Uses `_sniff_member_type` to read file headers and verify that `.pdf` and `.jpg` contents match their extensions. Detects and rejects renamed binaries (PE/ELF) or scripts.
6.  **Extraction & Anonymization**:
    -   **Images**: EXIF metadata is stripped using a "pixels-only" reconstruction method.
    -   **Storage**: Save stripped images to `IMAGE_DIR`.
    -   **Thumbnails**: Immediately generates thumbnails for each stripped image.
7.  **Data Extraction**:
    -   **Metadata**: Extracts dimensions, format, and luminance synchronously using `utils/image_metadata.py`.
    -   **PII Detection**: Enqueues an asynchronous OCR detection job for each image.
    -   **Encounter Creation**: Automatically creates `PatientEncounters` and linking records using the folder name as the patient identifier (`Name_ID_Date`).
8.  **PDF & OCR Processing**:
    -   Extracts PDFs and creates `EncounterFilePDF` records.
    -   Passes PDF list back to the worker for asynchronous OCR text extraction.
9.  **Completion**: 
    -   Updates `Job` status to `done`.
    -   Moves the source Zip to `PROCESSED_DIR` or `PROCESSING_ERROR_DIR`.

## Mermaid Workflow Diagram

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
