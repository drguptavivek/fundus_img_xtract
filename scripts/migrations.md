# Database Migrations



```bash
python -m scripts.create_user

python -m scripts.assign_roles admin --roles admin


python -m scripts.assign_roles alice --roles admin data_manager
python -m scripts.assign_roles bob   --roles fileUploader
```




```bash
  # Create tables + backfill UUIDs (EncounterFile + Reports)
  python scripts/setup_db.py --migrate-uuids

  # Check-only UUID migration (no changes, just counts/indexes)
  python scripts/setup_db.py --migrate-uuids --check-only
```





Added a proper Date column to PatientEncounters

patient_encounters: capture_date_dt: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
File: models.py
New backfill script: scripts/migrate_capture_date_dt.py

Adds the column if missing (SQLite ALTER TABLE).
Parses existing capture_date strings into ISO dates and writes to capture_date_dt.
Accepts common formats: YYYY-MM-DD, YYYY/MM/DD, DD-MM-YYYY, DD/MM/YYYY, MM/DD/YYYY, MM-DD-YYYY.
Flags:
--dry-run: parse and report counts without writing.
File: scripts/migrate_capture_date_dt.py
How to run

```bash
# Create column (if not present) and backfill:
python scripts/migrate_capture_date_dt.py
# Dry run (no writes):
python scripts/migrate_capture_date_dt.py --dry-run
```

Implemented capture_date_dt population during ZIP processing





Add `eye_side` column to encounter_files and create an index.

Usage:
```bash
  # Normal run (adds column if missing, ensures index)
  python scripts/migrate_eye_side.py

  # Dry run (show what would change)
  python scripts/migrate_eye_side.py --dry-run
```




"""
Add verification columns to patient_encounters: verified_status, verified_by, verified_at.

```bash
  python scripts/migrate_verification.py           # apply changes
  python scripts/migrate_verification.py --dry-run # report only
```





Add graded_for column to image_gradings and create a unique index over
  (encounter_file_id, grader_user_id, grader_role, graded_for).
Backfill existing rows to 'glaucoma'.

Usage:
```bash
  python scripts/migrate_image_grading_graded_for.py
  python scripts/migrate_image_grading_graded_for.py --dry-run

```

Drop unique index/constraint for image_gradings to allow multiple gradings
by the same grader for intra-rater agreement. Create a non-unique composite
index to keep lookups efficient.

Usage:
```bash
  python scripts/migrate_drop_image_grading_unique.py
  python scripts/migrate_drop_image_grading_unique.py --dry-run
```



Add uploader metadata columns to jobs and job_items tables:
 - jobs: uploader_user_id (INT), uploader_username (TEXT), uploader_ip (TEXT)
 - job_items: uploader_user_id (INT), uploader_username (TEXT), uploader_ip (TEXT)

Usage:
```bash
  python scripts/migrate_job_uploader.py
  python scripts/migrate_job_uploader.py --dry-run
```


This command will create the `direct_image_uploads` table if it does not already exist.
Add file_upload_quota and file_upload_count columns to the users table.
Also ensures the user_lab_units association table exists.

Usage:

```bash
  python scripts/migrate_user_upload_fields.py
```



Here’s a clean, idempotent Python script you can drop into scripts/init_direct_image_uploads.py. It drops and recreates the direct_image_uploads table in SQLite with the constraints and indexes we discussed, and ensures DIRECT_UPLOAD_DIR exists.

#!/usr/bin/env python3
"""
Initialize (drop & recreate) the direct_image_uploads table for SQLite.

- Requires your project's models.py to define:
  - Base, engine
  - DirectImageUpload (with CHECKs & Indexes)
  - DIRECT_UPLOAD_DIR (Path)

Usage:
  python scripts/init_direct_image_uploads.py


**Direct Image Anonymization Verifications**

This migration creates the `direct_image_verifications` table, which stores the verification status and remarks for direct image uploads after anonymization.

Usage:
```bash
  python scripts/setup_db.py --migrate-anonymization-verifications
  python scripts/setup_db.py --migrate-anonymization-verifications --check-only
```