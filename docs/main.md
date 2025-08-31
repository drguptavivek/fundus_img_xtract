# Documentation: `main.py`

This document outlines the function and behavior of the `main.py` script, which serves as the primary data ingestion pipeline for ZIP archives from medical imaging devices.

### Purpose

The `main.py` script is responsible for processing uploaded ZIP archives containing patient encounter data. Its main goals are:
1.  **Secure Ingestion**: Validate and process ZIP files from an upload directory.
2.  **Data Extraction**: Extract patient metadata, images, and PDF reports from the archives.
3.  **Persistence**: Store the extracted files and their associated metadata into the database.
4.  **File Organization**: Move processed, duplicate, or erroneous ZIP files to appropriate directories for archival and review.
5.  **Logging**: Record the outcome of each processing attempt.

### Core Function: `process_zip_file(zip_path, session)`

This is the central function that orchestrates the processing of a single ZIP file.

-   **Input**:
    -   `zip_path`: A `pathlib.Path` object pointing to the ZIP file to be processed.
    -   `session`: An active SQLAlchemy database session.
-   **Output**: A list of filenames for any PDFs that were extracted, which can be consumed by a subsequent OCR processing step.
-   **Returns**: A list of PDF filenames extracted from the zip.

#### Key Workflow Steps:

1.  **Duplicate Check**: It first calculates the MD5 hash of the ZIP file.  When a new ZIP file is processed, the system first calculates its MD5 hash, which is a unique digital fingerprint of the file's content. It then queries the database to see if this exact hash has been recorded from a previous upload.  If the hash already exists in the `zip_files` table, the file is considered a duplicate, moved to a dedicated `dupmd5` dated directory, and skipped. This content-based checking is more reliable than just comparing filenames.
2.  **Security Validation**:
    *   **File Type Allowlist**: It strictly enforces that only files with `.pdf`, `.jpg`, and `.jpeg` extensions are present. Any other file type results in the rejection and deletion of the ZIP.
    *   **Path Traversal**: It checks for and rejects any ZIP files containing relative paths (`../`) or absolute paths (`/`) to prevent directory traversal attacks.
    *   **Content Sniffing**: It reads the first few bytes (magic bytes) of each allowed file to ensure its content matches its extension (e.g., a `.pdf` file must start with `%PDF-`).
    *   **Malicious File Handling**: If any security check fails, the script logs the attempt, deletes the malicious ZIP file, and raises a `MaliciousZipError`.
3.  **Metadata Extraction**: It identifies the primary data directory within the ZIP, which is expected to follow a `PatientName_PatientID_CaptureDate` format. This information is parsed to populate the `PatientEncounters` model.
4.  **File Extraction & Renaming**:
    *   Allowed files (images and PDFs) are extracted from the archive.
    *   They are renamed to a standardized format: `{patient_id}_{name}_{capture_date}_{original_filename}`.
    *   Images are saved to `files/images/` and PDFs to `files/pdfs/`.
5.  **Database Persistence**:
    *   A `ZipFile` record is created to log the processed archive and its MD5 hash.
    *   A `PatientEncounters` record is created using the parsed metadata.
    *   An `EncounterFile` record is created for each extracted file, linked to the `PatientEncounters` record. A unique `uuid` is generated for each file. In ```models.py```, the uuid column in the ```EncounterFiles``` table is defined with a  default value that automatically generates a UUID. This means that even though main.py doesn't explicitly create a UUID when it  creates new EncounterFiles records, the database handles it automatically. As a result, every original image and every original report gets it own unique UUID.  [Documentation](docs/main.md). 
6.  **Transaction Management**: All database operations for a single ZIP file are committed as a single transaction. If any error occurs, the transaction is rolled back.
7.  **Archive Management**:
    *   On **success**, the original ZIP file is moved to the `files/processed/` directory.
    *   On **failure** (e.g., bad format, missing metadata directory), it is moved to `files/processing_error/`.
    *   If **malicious**, it is deleted.

### Standalone Execution

When run as a script (`if __name__ == "__main__":`), it initializes the environment and database, then processes all `.zip` files found in the `UPLOAD_DIR`.
