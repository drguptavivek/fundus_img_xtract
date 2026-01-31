# Task 1: Schema and Data Models

## 📊 Database Modifications

### 1. `Diseases` Table Update
Add a scope flag to distinguish between image-level and set-level grading.
- `grading_scope`: Enum('image', 'encounter') - Default 'image'.

### 2. `PatientEncounters` Table Update
Allow encounters to exist without a legacy `ZipFile`.
- `zip_file_id`: Make Nullable.
- `is_set_based`: Boolean, default False.

### 3. `GradingTask` Table Update (Polymorphism)
Tasks must now link to either a single image or a full encounter.
- `encounter_file_id`: Existing (Nullable).
- `direct_image_upload_id`: Existing (Nullable).
- `patient_encounter_id`: New (Nullable).
- **Constraint**: Exactly one of these three must be non-null.

### 4. `EncounterSetImage` (New Table)
Stores individual files for set-based encounters.
- `id`: PK.
- `uuid`: String (Unique).
- `patient_encounter_id`: FK -> PatientEncounters.
- `spatial_position`: Integer (1-9).
- `original_filename`: String.
- `edited_filename`: String (used for grading).
- `thumbnail_filename`: String.
- `folder_rel`: String (Path storage).
- `file_hash`: MD5.
- `created_at`: UTC Timestamp.

## 🛠️ Migration Plan
1. Generate migration using `alembic revision --autogenerate`.
2. Edit migration to ensure **idempotency** (using `IF NOT EXISTS`).
3. Apply migration: `$DC exec web uv run alembic upgrade head`.
