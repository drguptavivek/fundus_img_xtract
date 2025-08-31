# Summary of `models.py` Database Schema

This document outlines the database schema defined in `models.py`. It is designed to help an AI agent understand the key entities, their relationships, and important data constraints for the Fundus Image Manager application.

## Core Entities & Purpose

The database manages medical imaging data, specifically retinal fundus images, from ingestion to analysis and grading.

### 1. Data Ingestion & Clinical Encounters

These models track the raw data as it is uploaded and processed.

-   **`ZipFile`**: Represents an uploaded ZIP archive.
    -   **Key Fields**: `id`, `zip_filename`, `md5_hash` (for duplicate detection).
    -   **Purpose**: Acts as the entry point for data from Remedio FOP cameras.

-   **`PatientEncounters`**: Represents a single clinical visit or data capture session for a patient.
    -   **Key Fields**: `id`, `zip_file_id` (links to `ZipFile`), `patient_id`, `name`, `capture_date`, `capture_date_dt` (a proper `DATE` type for querying).
    -   **Verification Fields**: Includes fields to track manual verification status for Glaucoma and DR (`glaucoma_verified_status`, `dr_verified_by`, etc.).
    -   **Purpose**: Central hub for all data related to one patient visit.

-   **`EncounterFile`**: Represents an individual file (image or PDF) extracted from a ZIP archive.
    -   **Key Fields**: `id`, `patient_encounter_id` (links to `PatientEncounters`), `filename`, `file_type` (`pdf`, `image`), `ocr_processed` (boolean flag).
    -   **Stable Identifier**: `uuid` (a 36-char string) provides a permanent, unique ID for each file, crucial for linking and external references.
    -   **Annotation**: `eye_side` field for laterality ('left', 'right').
    -   **Purpose**: Manages individual assets and their processing state.

### 2. Diagnostic Reports (Extracted from PDFs)

These models store structured data extracted via OCR from PDF reports.

-   **`DiabeticRetinopathyReport`**:
    -   **Key Fields**: `id`, `patient_encounter_id`, `result`, `qualitative_result`.
    -   **Stable Identifier**: `uuid` for linking to the split PDF file.
    -   **File Link**: `report_file_name` stores the filename of the single-page DR PDF.

-   **`GlaucomaReport`**:
    -   **Key Fields**: `id`, `patient_encounter_id`, `vcdr_right`, `vcdr_left`, `result`, `qualitative_result`.
    -   **Stable Identifier**: `uuid` for linking to the split PDF file.
    -   **File Link**: `report_file_name` stores the filename of the single-page Glaucoma PDF.

### 3. Cleaned Data for Analytics

-   **`GlaucomaResultsCleaned`**:
    -   **Purpose**: Stores a cleaned, numeric version of glaucoma data for easier analysis and querying.
    -   **Key Fields**: `glaucoma_report_id` (links 1-to-1 with `GlaucomaReport`), `vcdr_right_num`, `vcdr_left_num` (parsed `FLOAT` values).
    -   **Traceability**: Includes original string values and the report's UUID for reference.

### 4. Image Grading & Annotation

-   **`ImageGrading`**:
    -   **Purpose**: Records a diagnostic impression for a single image, made by a specific user in a specific role. This is the core of the manual grading process.
    -   **Key Fields**: `encounter_file_id` (links to an image), `grader_user_id`, `grader_role`, `graded_for` (the disease, e.g., 'glaucoma'), `impression`.
    -   **Constraint**: A composite index on `(encounter_file_id, grader_user_id, grader_role, graded_for)` suggests a unique grading per user/role/disease for an image.

### 5. User Management & Access Control

-   **`User`**: Standard user model with `id`, `username`, `password_hash`, and profile information.
-   **`Role`**: Defines user roles (e.g., 'admin', 'optometrist').
-   **`UserRole`**: A many-to-many association table linking `User` and `Role`.
    -   **Helper methods**: `user.has_role('admin')` can be used to check permissions.

### 6. Asynchronous Job Tracking

-   **`Job`**: Represents a background job, typically for processing a batch of uploaded files.
    -   **Key Fields**: `token` (publicly-safe unique ID), `status` ('queued', 'processing', 'done', 'error').
-   **`JobItem`**: Represents a single file within a `Job`.
    -   **Key Fields**: `job_id`, `filename`, `state`.

### 7. Security

-   **`LoginAttempt`**: Logs every login attempt to enable rate-limiting and brute-force detection.
-   **`IpLock`**: Stores IP addresses that are temporarily locked out due to excessive failed logins.

## Key Relationships (ERD-like)

```
// 1. Core Ingestion Flow
ZipFile (1) -- (1) PatientEncounters

// 2. Encounter Composition
PatientEncounters (1) -- (many) EncounterFile
PatientEncounters (1) -- (many) DiabeticRetinopathyReport
PatientEncounters (1) -- (many) GlaucomaReport

// 3. Report Cleaning
GlaucomaReport (1) -- (1) GlaucomaResultsCleaned

// 4. Image Grading
EncounterFile (1) -- (many) ImageGrading
User (1) -- (many) ImageGrading

// 5. User Roles
User (many) -- (many) Role  (via UserRole table)

// 6. Job Tracking
Job (1) -- (many) JobItem
```

## Important Constraints & Indexes

-   **Uniqueness**:
    -   `ZipFile.zip_filename` and `ZipFile.md5_hash` are unique.
    -   `EncounterFile.uuid`, `DiabeticRetinopathyReport.uuid`, `GlaucomaReport.uuid` are unique and indexed, making them excellent for stable lookups.
    -   `GlaucomaResultsCleaned.glaucoma_report_id` is unique, enforcing a 1-to-1 relationship.
    -   `User.username` is unique.
    -   `Role.name` is unique.
-   **Indexes**:
    -   Several fields are indexed for performance, including foreign keys, UUIDs, verification statuses (`glaucoma_verified_status`), and date columns (`capture_date_dt`).
    -   The composite index on `ImageGrading` is important for preventing duplicate gradings.
-   **Cascading Deletes**:
    -   Deleting a `ZipFile` will cascade and delete the associated `PatientEncounters` and all its related files and reports.
    -   Deleting a `PatientEncounters` will cascade to its `EncounterFile`s, `DiabeticRetinopathyReport`s, and `GlaucomaReport`s.
-   **Data Types**:
    -   `PatientEncounters.capture_date_dt` is a proper `Date` type, which should be preferred for date-based queries over the string-based `capture_date`.
    -   `GlaucomaResultsCleaned` stores numeric VCDR values, which is better for statistical analysis than the raw strings in `GlaucomaReport`.