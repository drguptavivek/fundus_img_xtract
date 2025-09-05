# Malicious Upload Handling and Logging

## Overview

The system implements multiple layers of security checks to detect and prevent malicious uploads. These checks occur both during the initial upload process and during the ZIP file processing phase.

## Malicious Upload Detection

### 1. Initial Upload Validation (uploads/routes.py)

During the initial upload via the web interface:
- Only ZIP files are accepted (based on file extension)
- File size limits are enforced
- Resource fork files (starting with `._`) are rejected
- Upload metadata is recorded in sidecar JSON files

### 2. ZIP Processing Security Checks (main.py)

During ZIP file processing, the system performs several security checks:

#### Path Traversal Protection
- Blocks absolute paths (starting with `/`)
- Blocks paths containing parent directory references (`..`)
- Logs violations with user and IP information

#### File Type Validation
- Only allows files with extensions `.pdf`, `.jpg`, and `.jpeg`
- Performs content-type sniffing to detect files with mismatched extensions
- Rejects executables, scripts, and other potentially dangerous file types
- Logs violations with detailed information about the disallowed file

#### Content Verification
- Uses magic byte detection to verify that files match their extensions
- Detects when a file claiming to be a PDF is actually an executable, etc.
- Logs content mismatches with details about expected vs. detected types

## Logging System

### Main Processing Log
- Location: `logs/zip_main_process_log.txt` (configurable via `ZIP_INGEST_LOG` environment variable)
- Records processing status for each file (SUCCESS, ERROR, SKIPPED, etc.)
- Includes timestamp and brief status messages

### Malicious Upload Log
- Location: `logs/malicious_uploads.log` (configurable via `MALICIOUS_UPLOAD_LOG` environment variable)
- Records detailed information about rejected malicious uploads
- Log format: `[timestamp] zip=filename user=username ip=ip_address reason=reason entry=affected_entry`
- Includes user and IP information from upload metadata when available

### HTTP Request Logging
- Success requests logged to `logs/http_success.log`
- Error requests logged to `logs/http_error.log`
- Includes client IP, request method, URL, status code, user agent, and processing duration

### Sidecar Metadata
When files are uploaded via the web interface, metadata is stored in JSON files in the `upload_meta` directory:
- Filename
- Upload timestamp
- Uploader username and ID
- Client IP address
- User agent string

This metadata is used to enrich malicious upload logs with user information.

## Response to Malicious Uploads

When a malicious upload is detected:
1. The ZIP file is immediately deleted from the system
2. Related metadata files are also deleted
3. Detailed information is logged to the malicious upload log
4. A `MaliciousZipError` is raised to ensure the job processing system records the error
5. The file is not moved to the processed or error directories (since it's deleted)

## Error Handling

The system distinguishes between different types of errors:
- Malicious uploads are deleted and logged with specific reasons
- Processing errors (corrupted ZIPs, etc.) are moved to the error directory
- Valid uploads are moved to the processed directory after successful extraction

## Configuration

### Environment Variables
- `ZIP_INGEST_LOG`: Path to the main processing log file (default: `logs/zip_main_process_log.txt`)
- `MALICIOUS_UPLOAD_LOG`: Path to the malicious upload log file (default: `logs/malicious_uploads.log`)

### File Locations
- Upload directory: `files/uploaded/`
- Metadata directory: `files/upload_meta/`
- Processed files: `files/processed/`
- Error files: `files/error/`
- Duplicate files: `files/dupmd5_YYYY-MM-DD/`