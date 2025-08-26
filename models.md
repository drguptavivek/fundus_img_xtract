Here’s a **structured documentation** of the SQLite schema generated from your provided SQLAlchemy models. I’ve described each table, its columns, relationships, and constraints.

---

# 📄 Database Schema Documentation (`zip_processing.db`)

This database is designed to manage **uploaded ZIP files**, their associated **patient encounters**, and **diagnostic reports** (Diabetic Retinopathy & Glaucoma). It also stores metadata about **individual files** extracted from the encounters.

---

## 1. **`zip_files`**

Stores metadata for uploaded ZIP archives.

| Column         | Type    | Constraints | Description                                        |
| -------------- | ------- | ----------- | -------------------------------------------------- |
| `id`           | Integer | Primary Key | Unique identifier for each ZIP file.               |
| `zip_filename` | String  | Unique      | Name of the uploaded ZIP file.                     |
| `md5_hash`     | String  | Unique      | MD5 checksum of the ZIP file to detect duplicates. |

**Relationships**

* **1-to-1** with `patient_encounters` (`ZipFile.patient_encounter`).
* Cascade delete: removing a `ZipFile` deletes its linked `PatientEncounters`.

---

## 2. **`patient_encounters`**

Represents a clinical encounter for a patient, extracted from a ZIP file.

| Column         | Type    | Constraints                           | Description                                      |
| -------------- | ------- | ------------------------------------- | ------------------------------------------------ |
| `id`           | Integer | Primary Key                           | Unique identifier for the encounter.             |
| `zip_file_id`  | Integer | Foreign Key → `zip_files.id` (Unique) | Links encounter to its source ZIP file (1-to-1). |
| `name`         | String  | Required                              | Patient name (from metadata).                    |
| `patient_id`   | String  | Required                              | Patient identifier (e.g., hospital ID).          |
| `capture_date` | String  | Required                              | Date of image/report capture.                    |

**Relationships**

* **1-to-1** with `zip_files`.
* **1-to-many** with `encounter_files`.
* **1-to-many** with `diabetic_retinopathy_reports`.
* **1-to-many** with `glaucoma_reports`.
* Cascade delete ensures linked files and reports are removed if an encounter is deleted.

---

## 3. **`encounter_files`**

Stores individual files (images, PDFs, etc.) linked to an encounter.

| Column                 | Type    | Constraints                           | Description                      |
| ---------------------- | ------- | ------------------------------------- | -------------------------------- |
| `id`                   | Integer | Primary Key                           | Unique file entry.               |
| `patient_encounter_id` | Integer | Foreign Key → `patient_encounters.id` | Belongs to a specific encounter. |
| `filename`             | String  | Required                              | Name of the file.                |
| `file_type`            | String  | Required                              | Type of file (e.g., PDF, JPEG).  |
| `ocr_processed`        | Boolean | Default = False, Not Null             | Whether OCR has been applied.    |

**Relationships**

* **Many-to-1** with `patient_encounters`.

---

## 4. **`diabetic_retinopathy_reports`**

Stores diagnostic results for diabetic retinopathy.

| Column                 | Type    | Constraints                           | Description                        |
| ---------------------- | ------- | ------------------------------------- | ---------------------------------- |
| `id`                   | Integer | Primary Key                           | Unique report ID.                  |
| `patient_encounter_id` | Integer | Foreign Key → `patient_encounters.id` | Belongs to a patient encounter.    |
| `result`               | String  | Required                              | Primary diagnosis result.          |
| `qualitative_result`   | String  | Nullable                              | Additional qualitative findings.   |
| `report_file_name`     | String  | Nullable                              | Name of the extracted DR PDF file. |

**Relationships**

* **Many-to-1** with `patient_encounters`.

---

## 5. **`glaucoma_reports`**

Stores diagnostic results for glaucoma.

| Column                 | Type    | Constraints                           | Description                              |
| ---------------------- | ------- | ------------------------------------- | ---------------------------------------- |
| `id`                   | Integer | Primary Key                           | Unique report ID.                        |
| `patient_encounter_id` | Integer | Foreign Key → `patient_encounters.id` | Belongs to a patient encounter.          |
| `vcdr_right`           | String  | Nullable                              | Vertical Cup-to-Disc Ratio (right eye).  |
| `vcdr_left`            | String  | Nullable                              | Vertical Cup-to-Disc Ratio (left eye).   |
| `result`               | String  | Required                              | Primary diagnosis result.                |
| `qualitative_result`   | String  | Nullable                              | Additional qualitative findings.         |
| `report_file_name`     | String  | Nullable                              | Name of the extracted Glaucoma PDF file. |

**Relationships**

* **Many-to-1** with `patient_encounters`.

---

# 🔗 Entity-Relationship Overview

```
ZipFile (1) ──── (1) PatientEncounters (1) ──── (∞) EncounterFile
                                       └────── (∞) DiabeticRetinopathyReport
                                       └────── (∞) GlaucomaReport
```

---

# ⚙️ Initialization

* Database: `zip_processing.db` (SQLite).
* To create tables:

```bash
python models.py
```

This will call `create_db_and_tables()` which initializes all tables.

---

