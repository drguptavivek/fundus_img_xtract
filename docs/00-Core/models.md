# Summary of `models.py` Database Schema

This document outlines the database schema defined in `models.py`. It is designed to help an AI agent understand the key entities, their relationships, and important data constraints for the Fundus Image Manager application.

## Core Entities & Purpose

The database manages medical imaging data, specifically retinal fundus images, from ingestion to analysis and grading using a three-tier dual grading system.

### 1. User Management & Access Control

- **`User`**: Standard user model with authentication and profile information.
  - **Key Fields**: `id`, `username` (unique), `password_hash`, `is_active`, `is_locked_until`, `full_name`, `email`, `timezone`
  - **Role Methods**: `has_role()`, `has_all_roles()` for permission checking
  - **Quotas**: `file_upload_quota` and `file_upload_count` for upload limits

- **`Role`**: Defines user roles (e.g., 'admin', 'optometrist', 'resident', 'ophthalmologist').
  - **Key Fields**: `id`, `name` (unique)

- **`UserRole`**: Many-to-many association table linking `User` and `Role`.

- **`UserDiseaseUnitRole`**: Granular permissions for users to grade specific diseases in specific lab units.
  - **Key Fields**: `user_id`, `disease_id`, `lab_unit_id`
  - **Permission Flags**: `can_grade_resident`, `can_grade_faculty`, `can_arbitrate`
  - **Purpose**: Enables fine-grained access control for the dual grading system

### 2. Organizational Structure

- **`Hospital`**: Medical facility where images are captured.
  - **Key Fields**: `id`, `name` (unique)

- **`LabUnit`**: Department or unit within a hospital.
  - **Key Fields**: `id`, `name`, `hospital_id`
  - **Purpose**: Used for scoping grading assignments and access control

- **`user_lab_units`**: Association table linking users to their authorized lab units.

### 3. Reference Data

- **`Disease`**: Medical conditions that can be graded (e.g., Glaucoma, Diabetic Retinopathy).
  - **Key Fields**: `id`, `name` (unique)

- **`DiseaseGrading`**: Possible grading outcomes for each disease.
  - **Key Fields**: `id`, `disease_id`, `impression`, `display_order`, `is_active`, `guidelines`
  - **Purpose**: Master list of grading labels used across the system

- **`Camera`**: Types of cameras used for image capture.
  - **Key Fields**: `id`, `name` (unique)

- **`Area`**: Anatomical areas being imaged (e.g., left eye, right eye).
  - **Key Fields**: `id`, `name` (unique)

### 4. Data Ingestion & Clinical Encounters

These models track the raw data as it is uploaded and processed.

- **`ZipFile`**: Represents an uploaded ZIP archive from Remedio FOP cameras.
  - **Key Fields**: `id`, `zip_filename` (unique), `md5_hash` (for duplicate detection), `upload_date`
  - **Purpose**: Entry point for batch data ingestion

- **`PatientEncounters`**: Represents a single clinical visit or data capture session.
  - **Key Fields**: `id`, `zip_file_id` (unique), `name`, `patient_id`, `capture_date`, `capture_date_dt` (proper DATE type)
  - **Verification Fields**: Tracks verification status for Glaucoma, DR, and general encounter
  - **Lab Unit**: `lab_unit_id` links to organizational structure

- **`EncounterFile`**: Individual image files extracted from ZIP archives.
  - **Key Fields**: `id`, `patient_encounter_id`, `filename`, `file_type`, `uuid` (unique), `eye_side`
  - **Constraint**: Only stores image files (not PDFs)
  - **Purpose**: Individual image assets for grading

- **`EncounterFilePDF`**: PDF files extracted from ZIP archives.
  - **Key Fields**: `id`, `patient_encounter_id`, `filename`, `uuid` (unique)
  - **Constraint**: Only stores PDF files
  - **Purpose**: Reports and documents associated with encounters

### 5. Diagnostic Reports

- **`DiabeticRetinopathyReport`**: Structured data from DR reports.
  - **Key Fields**: `id`, `patient_encounter_id`, `uuid` (unique), `result`, `qualitative_result`, `report_file_name`

- **`GlaucomaReport`**: Structured data from Glaucoma reports.
  - **Key Fields**: `id`, `patient_encounter_id`, `uuid` (unique), `vcdr_right`, `vcdr_left`, `result`, `qualitative_result`

- **`GlaucomaResultsCleaned`**: Cleaned, numeric version of glaucoma data.
  - **Key Fields**: `id`, `glaucoma_report_id` (unique), `vcdr_right_num`, `vcdr_left_num`
  - **Purpose**: Easier analysis with parsed numeric values

### 6. Direct Image Upload System

- **`DirectImageUpload`**: Images uploaded directly (not from ZIP files).
  - **Key Fields**: `id`, `uuid` (unique), `original_filename`, `filename`, `edited_filename`, `folder_rel`, `file_hash`, `content_hash`, `uploader_id`
  - **Metadata**: `hospital_id`, `lab_unit_id`, `camera_id`, `disease_id`, `area_id`, `is_mydriatic`
  - **Source Information**: `is_pregraded` (whether uploaded as pre-graded), `created_at` timestamp
  - **Relationships**: May be linked to grading tasks via `GradingTask.direct_image_upload_id`, has multiple `verifications` via DirectImageVerify
  - **Purpose**: Bypasses ZIP workflow for individual image uploads, supports both regular and pre-graded uploads
  - **File Tracking**: `file_hash` for duplicate detection, `content_hash` for content integrity
  - **Constraints**: Filename must not contain slashes, folder_rel must be relative POSIX path
  - **Indexes**: `uuid`, `file_hash`, `uploader_id`, `created_at`, `content_hash` for performance
  - **Relationships**: `uploader`, `hospital`, `lab_unit`, `camera`, `disease`, `area` (all relationships to reference tables)

- **`DirectImageVerify`**: Verification status for direct uploads.
  - **Key Fields**: `id`, `image_upload_id` (unique), `verified_status`, `remarks`, `verified_by_id`, `verified_at`
  - **Status Values**: 'verified', 'unverified', 'pending'
  - **Additional Fields**: `remarks` for verification notes, `verified_at` for timestamp
  - **Special Handling**: For pre-graded uploads, records are automatically created with 'verified' status
  - **Relationships**: `image_upload` (DirectImageUpload reference with cascade delete), `verified_by` (User reference)
  - **Constraints**: Unique per image_upload_id, status must be one of the allowed values
  - **Indexes**: `image_upload_id`, `verified_status`, `verified_by_id` for performance

### 7. Dual Grading System

- **`GradingTask`**: Tasks created for grading specific images for specific diseases.
  - **Key Fields**: `id`, `encounter_file_id` OR `direct_image_upload_id`, `disease_id`, `lab_unit_id`, `state`
  - **State Values**: 'pending', 'resident_done', 'faculty_done', 'arbitration', 'final'
  - **Uniqueness**: One task per image-disease combination globally
  - **Purpose**: Core entity for the three-tier grading workflow

- **`Grade`**: Individual grades submitted by users or AI models for tasks.
  - **Key Fields**: `id`, `task_id`, `grader_user_id`, `role_slot`, `disease_grading_id`, `comment`, `time_taken`
  - **Role Slots**:
    - 'resident': Initial grading by resident ophthalmologists
    - 'faculty': Secondary grading by faculty ophthalmologists
    - 'arbitrator': Final decision when resident and faculty grades disagree
    - 'ai': Grades submitted by AI models
    - 'review': Review grades added by faculty or arbitrators for quality control
  - **AI Model Fields**: `ai_model_id`, `ai_model_name`, `ai_model_version` for AI grades
  - **Denormalized Fields**: `disease_name`, `grade_name`, `grade_description` for historical preservation
  - **Uniqueness**: One grade per user per role per task

- **`Consensus`**: Final consensus decision for tasks.
  - **Key Fields**: `id`, `task_id` (unique), `final_disease_grading_id`, `method`, `decided_by_user_id`
  - **Method Values**: 'match' (resident and faculty agreed), 'adjudication' (arbitrator decision)
  - **Purpose**: Stores the final grading decision

- **`TaskTracker`**: Tracks when users start working on tasks.
  - **Key Fields**: `id`, `task_id`, `user_id`, `role_slot`, `started_at`
  - **Purpose**: Identifies and cleans up stuck tasks

### 8. Legacy Image Grading

- **`ImageGrading`**: Legacy grading model (pre-dual grading system).
  - **Key Fields**: `id`, `encounter_file_id` OR `direct_image_upload_id`, `grader_user_id`, `grader_role`, `graded_for`, `impression`
  - **Purpose**: Maintains backward compatibility with old grading data

### 9. AI Model Integration

- **`AIGrade`**: AI model predictions for images.
  - **Key Fields**: `id`, `encounter_file_id` OR `direct_image_upload_id`, `disease_id`, `model_name`, `model_version`
  - **Prediction Data**: `label_disease_grading_id`, `confidence`, `probabilities_json`, `run_id`
  - **Performance**: `inference_time_ms`
  - **Purpose**: Stores AI model outputs for comparison and analysis

### 10. Job Management

- **`Job`**: Background processing jobs for batch operations.
  - **Key Fields**: `id`, `token` (unique), `status`, `error`, `rejected_summary`, `excel_filename`, `upload_type`, `created_at`, `updated_at`, `uploader_user_id`, `uploader_username`, `uploader_ip`, `lab_unit_id`
  - **Status Values**: 'queued', 'processing', 'completed', 'error'
  - **Purpose**: Manages batch operations like ZIP file processing, pre-graded uploads, and other bulk operations
  - **Additional Fields**: `rejected_summary` stores user-provided labels or descriptions for the job, `excel_filename` for Excel-based imports, `upload_type` for type identification
  - **Relationships**: `items` (many JobItems), `lab_unit` (LabUnit reference)
  - **Indexes**: `uploader_user_id`, `uploader_username`, `lab_unit_id` for performance

- **`JobItem`**: Individual files within a job.
  - **Key Fields**: `id`, `job_id`, `filename`, `state`, `detail`, `started_at`, `finished_at`, `uploader_user_id`, `uploader_username`, `uploader_ip`
  - **State Values**: 'queued', 'pending', 'completed', 'error'
  - **Purpose**: Tracks processing status of each file in a batch with detailed information
  - **Additional Fields**: `detail` provides specific information about processing result
  - **Relationships**: `job` (Job reference)
  - **Indexes**: `job_id`, `uploader_user_id`, `uploader_username` for performance

### 11. Security & Audit

- **`LoginAttempt`**: Logs all login attempts for security monitoring.
  - **Key Fields**: `id`, `username_input`, `ip_address`, `success`, `created_at`

- **`IpLock`**: IP addresses temporarily locked due to failed login attempts.
  - **Key Fields**: `id`, `ip_address` (unique), `locked_until`

- **`PasswordResetAttempt`**: Password reset requests for rate limiting.
  - **Key Fields**: `id`, `email`, `ip_address`, `attempted_at`

### 12. Notifications

- **`Notification`**: System notifications for users.
  - **Key Fields**: `id`, `title`, `message`, `notification_type`, `recipient_user_id`, `sender_user_id`
  - **Type Values**: 'info', 'warning', 'error', 'system'
  - **Status**: `is_read`, `is_active`

- **`NotificationRead`**: Tracks when users read notifications.
  - **Key Fields**: `id`, `notification_id`, `user_id`, `read_at`
  - **Purpose**: Per-user read tracking

### 13. Session Management

- **`FlaskSession`**: Server-side session storage.
  - **Key Fields**: `session_id` (primary key), `data`, `expiry`, `user_id`, `started_at`, `ended_at`
  - **Purpose**: Secure session management with user tracking

## Key Relationships

### Core Ingestion Flow
```
ZipFile (1) -- (1) PatientEncounters
PatientEncounters (1) -- (many) EncounterFile
PatientEncounters (1) -- (many) EncounterFilePDF
PatientEncounters (1) -- (many) DiabeticRetinopathyReport
PatientEncounters (1) -- (many) GlaucomaReport
```

### Dual Grading Flow
```
GradingTask (1) -- (many) Grade
GradingTask (1) -- (1) Consensus
GradingTask (1) -- (many) TaskTracker
Grade (many) -- (1) User
Grade (many) -- (1) DiseaseGrading
```

### Direct Upload Flow
```
DirectImageUpload (1) -- (many) DirectImageVerify
DirectImageUpload (1) -- (many) GradingTask
DirectImageUpload (1) -- (many) ImageGrading
```

### Organizational Structure
```
Hospital (1) -- (many) LabUnit
LabUnit (many) -- (many) User (via user_lab_units)
User (many) -- (many) Role (via UserRole)
User (many) -- (many) Disease (via UserDiseaseUnitRole)
```

## Important Constraints & Indexes

### Uniqueness Constraints
- `User.username`, `ZipFile.zip_filename`, `ZipFile.md5_hash`
- All UUID fields (`EncounterFile.uuid`, `DirectImageUpload.uuid`, etc.)
- `GradingTask`: Unique per image-disease combination
- `Grade`: Unique per user-role-task combination
- `Consensus`: One per task
- `DirectImageVerify`: One per image upload

### Check Constraints
- Image references: Either `encounter_file_id` OR `direct_image_upload_id` must be set, never both
- Task states limited to: 'pending', 'resident_done', 'faculty_done', 'arbitration', 'final'
- Role slots limited to: 'resident', 'faculty', 'arbitrator', 'ai', 'review'
- Consensus methods limited to: 'match', 'adjudication'

### Performance Indexes
- Foreign keys on all relationships
- UUID columns for fast lookups
- Composite indexes for common query patterns:
  - User permissions: `(user_id, disease_id, lab_unit_id)`
  - Task assignments: `(disease_id, lab_unit_id, state)`
  - Grading history: `(task_id, role_slot)`, `(grader_user_id, role_slot)`

### Cascade Deletes
- Deleting `ZipFile` cascades to all related encounter data
- Deleting `GradingTask` cascades to grades and consensus
- Deleting `User` cascades to sessions, notifications, and permission records

## Data Integrity Features

### Denormalization for Historical Preservation
- `Grade` table stores copies of disease and grading information at time of grading
- `Consensus` table stores copies of final decision details
- Ensures data integrity even if master tables change

### Audit Trails
- All grading activities tracked with user, timestamp, and IP address
- Login attempts and security events logged
- Job processing history maintained

### Security
- Password hashing with secure algorithms
- Session management with server-side storage
- IP-based rate limiting and lockout mechanisms
- Role-based access control with granular permissions