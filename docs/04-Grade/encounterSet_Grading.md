# EncounterSet Grading

> **Deprecated legacy model:** This document describes the older Strabismus/cardinal-gaze EncounterSet workflow where a single encounter-level task grades the whole set. The current model is defined by EncounterSetType and Upload Profile mappings: image-scoped grading schemes apply to task-eligible clinical images, and encounter-scoped grading schemes apply to the overall EncounterSet. See `docs/API/encounter-set-types/README.md` and `docs/API/upload-profiles/README.md`.

## Overview

Grading for encounter sets occurs at the **encounter level**, not per-image. A single `GradingTask` is created for the entire `PatientEncounters`, and graders view all images in a synchronized grid to make a consolidated diagnosis.

## Key Differences from Image-Based Grading

| Aspect | Image-Based | Set-Based (EncounterSet) |
|--------|-------------|---------------------------|
| **Task Scope** | Per image | Per encounter |
| **GradingTask Link** | `encounter_file_id` | `patient_encounter_id` |
| **Viewer** | Single image | 3x3 synchronized grid |
| **Diagnosis** | Individual image grade | Single grade for entire set |
| **Not Gradable** | Skip single image | Mark entire set or specific positions |

## Grading Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. TASK CREATION                                               │
│     ├─ Triggered after encounter verification                   │
│     ├─ One GradingTask per PatientEncounters                   │
│     ├─ task_type: 'encounter_set'                              │
│     └─ Links to patient_encounter_id (NOT encounter_file_id)   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  2. GRADER ASSIGNMENT                                           │
│     ├─ Resident gets task (state: pending)                     │
│     ├─ Access via: GET /grading/encounter_set/<task_uuid>     │
│     └─ Dual grading: Resident → Resident2 → Arbitrator        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  3. GRID VIEWER                                                 │
│     ├─ 3x3 grid displaying positions 1-9                       │
│     ├─ Empty slots shown for missing positions                 │
│     ├─ Sync-zoom/pan across all images                         │
│     └─ Toggle sync available for detailed inspection           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  4. GRADING SUBMISSION                                          │
│     ├─ POST /grading/encounter_set/submit                      │
│     ├─ Select disease grading label (e.g., Strabismus severity)│
│     ├─ Optional comment field                                  │
│     └─ Single grade applies to entire encounter                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  5. DUAL GRADING FLOW                                           │
│     ├─ Resident grade → state: resident_complete               │
│     ├─ Resident2 grade → state: resident2_complete             │
│     ├─ Consensus check → auto-arbitrate or escalate            │
│     └─ Arbitrator resolves if disagree                         │
└─────────────────────────────────────────────────────────────────┘
```

## Routes

### Grading Interface

```http
GET /grading/encounter_set/<task_uuid>
Authorization: Session cookie
Roles: resident, resident2, ophthalmologist, arbitrator, admin
```

**Template Data:**
```python
{
    "task": GradingTask,
    "encounter": PatientEncounters,
    "grid": {1: EncounterSetImage|None, ..., 9: EncounterSetImage|None},
    "images": [EncounterSetImage],
    "disease": Disease,
    "grading_labels": [DiseaseGrading],
    "existing_grade": Grade|None,  # User's previous submission
    "not_gradable_count": int       # How many images marked not gradable
}
```

### Submit Grade

```http
POST /grading/encounter_set/submit
Content-Type: application/x-www-form-urlencoded

task_uuid=<uuid>
slot=resident              # or resident2, arbitrator
label_id=5
comment=Optional notes
```

**Response:**
- `302` - Redirect to grading index
- `400` - Missing parameters
- `404` - Task not found

**Backend Actions:**
1. Creates/updates `Grade` record with:
   - `task_id`, `grader_user_id`, `role_slot`
   - `disease_grading_id`, `comment`
2. Calls `update_task_state_based_on_grades()`
3. Calls `create_or_update_consensus()`

## Grid Layout

```
┌─────────┬─────────┬─────────┐
│   1     │    2    │    3    │  ← Top row
│ Up-Left │ Up      │ Up-Right│
├─────────┼─────────┼─────────┤
│   4     │    5    │    6    │  ← Middle row
│ Left    │PRIMARY  │ Right   │  ← Position 5 = Primary Gaze
├─────────┼─────────┼─────────┤
│   7     │    8    │    9    │  ← Bottom row
│ Down-Left│ Down   │Down-Right│
└─────────┴─────────┴─────────┘
```

**Note:** For Strabismus:
- Position 5 = Primary gaze (most important)
- Positions 1-4, 6-9 = Cardinal gazes
- Empty slots are acceptable (e.g., patient couldn't look in a direction)

## Grading Labels

Labels are fetched from `DiseaseGrading` table:

```python
grading_labels = db.query(DiseaseGrading).filter_by(
    disease_id=task.disease_id,
    is_active=True
).order_by(DiseaseGrading.display_order).all()
```

**Example Strabismus Labels:**
1. No Strabismus
2. Intermittent Strabismus
3. Constant Strabismus - Small Angle
4. Constant Strabismus - Large Angle
5. Not Gradable

## Not Gradable Handling

When some images are marked `is_not_gradable=True` during verification:

1. **Count displayed**: `not_gradable_count` shown in UI
2. **Grading still possible**: Grader can assess based on available images
3. **Not Gradable label**: Disease grading may include "Not Gradable" option
4. **Comment required**: If selecting "Not Gradable", comment should explain why

## Dual Grading Integration

The encounter set grading uses existing dual grading infrastructure:

```python
from utils.dualGradingConsensusUtils import (
    update_task_state_based_on_grades,
    create_or_update_consensus
)
```

**Task States:**
- `pending` → Assigned to resident
- `resident_complete` → Resident submitted
- `resident2_complete` → Resident2 submitted
- `consensus` → Grades agree
- `arbitration_required` → Disagreement detected
- `arbitration_complete` → Arbitrator resolved

## Media Serving

Encounter set images are served via these routes:

```python
# Original image
GET /media/encounter-set/<uuid>

# Edited version (PII-masked) - takes priority
GET /media/encounter-set/<uuid>/edited

# Thumbnail
GET /media/encounter-set/<uuid>/thumbnail
```

**Priority Logic:**
```python
def serve_encounter_set_image(uuid):
    img = get_encounter_set_image(uuid)
    if img.edited_filename:
        return serve_edited()  # Grading always uses masked version
    return serve_original()
```

## S3 Storage Support

Images stored in S3 are served through the same routes:

```python
if img.s3_object_key_edited:
    # Serve from S3
    return s3_proxy(img.s3_object_key_edited)
elif img.s3_object_key:
    # Serve original from S3
    return s3_proxy(img.s3_object_key)
else:
    # Serve from local filesystem
    return serve_local(img.folder_rel, img.edited_filename or img.original_filename)
```

## Related Documentation

- [Core System](../00-Core/encounterSet_grading_system.md) - Data model and architecture
- [Verification](../02-Verify-Anonymize/encounterSet_anonymization.md) - Pre-grading workflow
- [Complete Workflow](../08-Workflow/EncounterSet_grading_workflow.md) - End-to-end flow
- [Dual Grading](comprehensive_dual_grading_system.md) - Consensus and arbitration
