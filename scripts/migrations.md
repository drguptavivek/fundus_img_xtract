# Migrations

## Dual Grading Schema

This migration adds the tables required for the dual grading feature. The new tables are:
- `grading_tasks`
- `grades`
- `consensus`
- `user_disease_unit_role`
- `ai_grades` (optional)

These tables are created by ensuring the models are defined in `models.py` and running the `setup_db.py` script.

Usage:
```bash
  python scripts/setup_db.py --migrate-dual-grading
```

---

**Add disease_gradings table**

This migration creates the `disease_gradings` table, which stores the impressions and their display order for each disease.

Usage:
```bash
  python scripts/setup_db.py --migrate-disease-gradings
  python scripts/setup_db.py --migrate-disease-gradings --check-only
```


**Add missing roles to database**

This migration adds any roles that are used in the application but missing from the database.

Usage:
```bash
  python scripts/setup_db.py --migrate-missing-roles
  python scripts/setup_db.py --migrate-missing-roles --check-only
```

Or you can run the standalone script:

```bash
  python scripts/migrate_missing_roles.py
  python scripts/migrate_missing_roles.py --dry-run
```

**Add lab_unit_id to EncounterFile table**

This migration adds the `lab_unit_id` column to the `encounter_files` table, allowing each EncounterFile to be directly associated with a LabUnit.

Usage:
```bash
  python scripts/setup_db.py --migrate-encounter-files-lab-unit
  python scripts/setup_db.py --migrate-encounter-files-lab-unit --check-only
```

Or you can run the standalone script:

```bash
  python scripts/migrate_encounter_files_lab_unit.py
```

**Add lab_unit_id to PatientEncounters table**

This migration adds the `lab_unit_id` column to the `patient_encounters` table, allowing each PatientEncounter to be directly associated with a LabUnit.

Usage:
```bash
  python scripts/setup_db.py --migrate-patient-encounters-lab-unit
  python scripts/setup_db.py --migrate-patient-encounters-lab-unit --check-only
```

Or you can run the standalone script:

```bash
  python scripts/migrate_patient_encounters_lab_unit.py
  python scripts/migrate_patient_encounters_lab_unit.py --dry-run
```

**Add matching fields to DirectImageUploads table**

This migration adds the matching fields (`matched_at`, `is_locked`, `is_arbitration`, `arbitrated_by`) to the `direct_image_uploads` table, which are used for image matching and arbitration workflows.

Usage:
```bash
  python scripts/setup_db.py --migrate-direct-uploads-matching-fields
  python scripts/setup_db.py --migrate-direct-uploads-matching-fields --check-only
```

Or you can run the standalone script:

```bash
  python scripts/migrate_direct_uploads_matching_fields.py
  python scripts/migrate_direct_uploads_matching_fields.py --dry-run
```

**Set up standard gradings for core diseases**

This setup creates standard gradings for the core diseases (Glaucoma, DR, AMD) with appropriate guidelines and display order.

Usage:
```bash
  python scripts/setup_db.py --setup-core-disease-gradings
  python scripts/setup_db.py --setup-core-disease-gradings --check-only
```

Or you can run the standalone script:

```bash
  python scripts/setup_core_disease_gradings.py
  python scripts/setup_core_disease_gradings.py --dry-run
```

**Create user_disease_specializations table**

This migration creates the `user_disease_specializations` table, which stores the many-to-many relationship between users (ophthalmologists) and diseases they can grade.

Usage:
```bash
  python scripts/setup_db.py --migrate-user-disease-specializations
  python scripts/setup_db.py --migrate-user-disease-specializations --check-only
```

Or you can run the standalone script:

```bash
  python scripts/migrate_user_disease_specializations.py
```

**Ensure core diseases exist**

This migration ensures that the core diseases (Glaucoma, DR, AMD) exist with their specific IDs (1, 2, 3 respectively). These diseases cannot be deleted or renamed through the UI.

Usage:
```bash
  python scripts/setup_db.py --migrate-core-diseases
  python scripts/setup_db.py --migrate-core-diseases --check-only
```

Or you can run the standalone script:

```bash
  python scripts/migrate_core_diseases.py
  python scripts/migrate_core_diseases.py --dry-run
```

**Add guidelines column to disease_gradings table**

This migration adds a guidelines column to the disease_gradings table to store markdown guidelines for each grading.

Usage:
```bash
  python scripts/setup_db.py --migrate-disease-grading-guidelines
  python scripts/setup_db.py --migrate-disease-grading-guidelines --check-only
```

Or you can run the standalone script:

```bash
  python scripts/migrate_disease_grading_guidelines.py
  python scripts/migrate_disease_grading_guidelines.py --dry-run
```

**Separate PDF files into encounter_file_pdfs table**

This migration separates PDF files from the encounter_files table into a new encounter_file_pdfs table, retaining the encounter_files table for images only.

Usage:
```bash
  python scripts/setup_db.py --migrate-encounter-file-pdfs
  python scripts/setup_db.py --migrate-encounter-file-pdfs --check-only
```

Or you can run the standalone script:

```bash
  python scripts/migrate_encounter_file_pdfs.py
  python scripts/migrate_encounter_file_pdfs.py --check-only
```

**Remove matching and arbitration fields**

This migration removes the matching and arbitration fields (`matched_at`, `is_locked`, `is_arbitration`, `arbitrated_by`) from the `encounter_file_pdfs` and `direct_image_uploads` tables, which are no longer needed after removing the dual grading, matching, and arbitration workflows.

Usage:
```bash
  python scripts/setup_db.py --migrate-remove-matching-arbitration-fields
  python scripts/setup_db.py --migrate-remove-matching-arbitration-fields --check-only
```

Or you can run the standalone script:

```bash
  python scripts/migrate_remove_matching_arbitration_fields.py
  python scripts/migrate_remove_matching_arbitration_fields.py --dry-run
```
