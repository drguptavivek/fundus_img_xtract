# EncounterSet Grading System

> **Deprecated legacy model:** This document reflects the original Strabismus/cardinal-gaze EncounterSet design. The active direction is the EncounterSetType / Upload Profile model: image-scoped grading schemes apply to verified, task-eligible clinical images, while encounter-scoped grading schemes apply to the entire EncounterSet. See `docs/API/encounter-set-types/README.md` and `docs/API/upload-profiles/README.md`.

## Overview

The EncounterSet grading system extends the fundus imaging platform to support diseases requiring **multiple spatially-related images** for a single diagnosis. The primary use case is **Strabismus** (9-cardinal gaze positions), but the architecture supports any multi-image set-based workflow.

## Architecture

### Data Model

```
PatientEncounters (Set Container)
│
├── is_set_based: BOOLEAN           # Distinguishes set-based encounters
├── encounter_verified_status: ENUM # pending/verified
│
└── EncounterSetImage[] (1-9 images per encounter)
    ├── spatial_position: INTEGER (1-9)   # Grid position
    ├── original_filename: STRING         # Original uploaded file
    ├── edited_filename: STRING?          # PII-masked version
    ├── thumbnail_filename: STRING?       # Thumbnail for UI
    │
    ├── is_anonymized: BOOLEAN           # PII masking complete
    ├── is_reviewed: BOOLEAN              # Optometrist reviewed
    ├── is_not_gradable: BOOLEAN          # Cannot be graded
    ├── not_gradable_reason: STRING?      # Reason if not gradable
    │
    └── S3 Fields (nullable for local/S3 hybrid)
        ├── hospital_id: INTEGER?
        ├── s3_config_id: INTEGER?
        ├── s3_object_key: STRING?
        ├── s3_object_key_edited: STRING?
        └── s3_object_key_thumbnail: STRING?
```

### Key Concepts

| Concept | Description |
|---------|-------------|
| **Spatial Position** | Integer 1-9 representing grid location (e.g., 5 = primary gaze for Strabismus) |
| **Set-Based** | `is_set_based=True` indicates grading occurs at encounter level, not per-image |
| **Edited Version** | PII-masked/cropped version created during verification; used for grading |
| **Not Gradable** | Image quality insufficient for grading; requires reason documentation |

## Database Relationships

```python
# In models.py
class EncounterSetImage(Base):
    __tablename__ = 'encounter_set_images'

    patient_encounter_id: Mapped[int] = mapped_column(
        ForeignKey('patient_encounters.id', ondelete='CASCADE')
    )

    patient_encounter: Mapped["PatientEncounters"] = relationship(
        back_populates="encounter_set_images"
    )

class PatientEncounters(Base):
    # ... existing fields ...

    encounter_set_images: Mapped[List["EncounterSetImage"]] = relationship(
        back_populates="patient_encounter",
        cascade="all, delete-orphan"
    )
```

## Storage Model

### Local Storage (Default)

```
files/encounter_sets/YYYY_MM_DD/<encounter_id>/
├── <uuid>.jpg              # Original image
├── <uuid>_edited.jpg       # PII-masked version (if created)
└── thm_<uuid>.jpg          # Thumbnail
```

### S3 Storage (Optional)

Images can be stored in S3 while keeping metadata in PostgreSQL. S3 fields are nullable:
- `NULL` = Local storage
- Non-NULL = S3 storage with config reference

## Polymorphic GradingTask

For set-based diseases, `GradingTask` links to `PatientEncounters` directly:

```python
class GradingTask(Base):
    # Single-image tasks
    encounter_file_id: Mapped[int | None]
    direct_image_upload_id: Mapped[int | None]

    # Set-based tasks (NEW)
    patient_encounter_id: Mapped[int | None]

    # Constraint: Exactly ONE must be non-null
```

## Related Documentation

- [Anonymization Workflow](../02-Verify-Anonymize/encounterSet_anonymization.md) - PII masking process
- [Grading Interface](../04-Grade/encounterSet_Grading.md) - Grading workflow
- [Complete Workflow](../08-Workflow/EncounterSet_grading_workflow.md) - End-to-end flow
