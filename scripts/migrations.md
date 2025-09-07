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