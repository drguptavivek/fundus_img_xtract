# EncounterSet Complete Workflow

> **Deprecated legacy model:** This workflow is retained for historical Strabismus/cardinal-gaze context. Current EncounterSet work should follow the EncounterSetType / Upload Profile model, where image-scoped schemes and encounter-scoped schemes can both be configured for one EncounterSet. See `docs/API/encounter-set-types/README.md` and `docs/API/upload-profiles/README.md`.

## End-to-End Pipeline

This document describes the complete workflow from mobile upload to final diagnosis for encounter-set based diseases like Strabismus.

## Phase 1: Mobile Upload (Ingestion)

```
┌─────────────────────────────────────────────────────────────────┐
│                        MOBILE APP                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   Image 1   │  │   Image 2   │  │   Image 3   │             │
│  │ Position: 1 │  │ Position: 5 │  │ Position: 9 │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
└─────────┼─────────────────┼─────────────────┼───────────────────┘
          │                 │                 │
          └─────────────────┴─────────────────┘
                           │
                           ▼
                 ┌─────────────────────┐
                 │  POST /v1/encounter- │
                 │      set/upload     │
                 └──────────┬──────────┘
                            │
                 ┌──────────▼──────────┐
                 │   JWT Validation    │
                 │   + Rate Limiting   │
                 └──────────┬──────────┘
                            │
                            ▼
              ┌─────────────────────────────┐
              │  Create PatientEncounters   │
              │  - is_set_based: True       │
              │  - uuid: new UUID4          │
              │  - capture_date: YYYY-MM-DD │
              └──────────────┬──────────────┘
                             │
                             ▼
              ┌─────────────────────────────┐
              │   Create EncounterSetImage  │
              │   - spatial_position: 1-9   │
              │   - original_filename: uuid │
              │   - folder_rel: date/id     │
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │   EXIF Stripping (OCR)      │
              │   - Check for PII           │
              │   - Remove metadata         │
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │   Schedule Thumbnail Job   │
              │   (Celery Background)      │
              └─────────────────────────────┘
```

**API Request Format:**

```http
POST /api/v1/encounter-set/upload
Authorization: Bearer <jwt_token>
Content-Type: multipart/form-data

encounter_uuid=optional-uuid  # Omit for new encounter
patient_id=PAT-001
patient_name=John Doe
capture_date=2026-01-31
spatial_position=5
file=@image.jpg
```

**Response:**
```json
{
  "message": "Image uploaded successfully",
  "encounter_id": 12345,
  "encounter_uuid": "abc-123-def-456",
  "image_uuid": "img-uuid-789",
  "spatial_position": 5
}
```

## Phase 2: Verification & Anonymization

```
┌─────────────────────────────────────────────────────────────────┐
│                   OPTOMETRIST WORKSTATION                       │
│                                                                 │
│  1. View Pending List                                          │
│     GET /verify_encounter_set/                                 │
│     ┌─────────────────────────────────────────────────────┐    │
│     │  PAT-001 | John Doe | 2026-01-31 | 9 images        │    │
│     │  PAT-002 | Jane Smith | 2026-01-30 | 6 images      │    │
│     └─────────────────────────────────────────────────────┘    │
│                                                                 │
│  2. Verify Specific Set                                         │
│     GET /verify_encounter_set/verify/<uuid>                   │
│     ┌───┬───┬───┐                                             │
│     │ 1 │ 2 │ 3 │  ← 3x3 grid view                            │
│     ├───┼───┼───┤                                             │
│     │ 4 │ 5 │ 6 │  ← Can drag-drop to reorder                 │
│     ├───┼───┼───┤                                             │
│     │ 7 │ 8 │ 9 │                                             │
│     └───┴───┴───┘                                             │
│                                                                 │
│  3. For Each Image:                                            │
│     ├─ Click image → Opens editor                              │
│     ├─ Check for PII (patient name, ID, barcode)              │
│     ├─ If PII found:                                           │
│     │  ├─ Use crop/mask tools                                  │
│     │  ├─ Save edited version                                  │
│     │  └─ is_anonymized=True, is_reviewed=True                │
│     └─ If no PII:                                              │
│        └─ Mark as anonymized (no edit needed)                  │
│                                                                 │
│  4. Handle Quality Issues:                                     │
│     ├─ If blurry/overexposed: Mark "Not Gradable"             │
│     └─ Provide reason for documentation                        │
│                                                                 │
│  5. Finalize Set                                               │
│     POST /verify_encounter_set/finalize/<uuid>                │
│     ├─ Validates all images reviewed                           │
│     ├─ encounter_verified_status = 'verified'                  │
│     └─ Triggers GradingTask creation                          │
└─────────────────────────────────────────────────────────────────┘
```

## Phase 3: Task Creation

```
┌─────────────────────────────────────────────────────────────────┐
│                    TASK CREATION SERVICE                        │
│                                                                 │
│  Trigger: Encounter verified                                    │
│                                                                 │
│  1. Query Disease Configuration                                │
│     ┌────────────────────────────────────────────────────┐      │
│     │ disease: Strabismus                                │      │
│     │ grading_scope: 'encounter'  ← Set-based flag      │      │
│     │ task_creation_rules: ...                           │      │
│     └────────────────────────────────────────────────────┘      │
│                                                                 │
│  2. Create GradingTask                                         │
│     ┌────────────────────────────────────────────────────┐      │
│     │ GradingTask {                                       │      │
│     │   uuid: new_uuid4()                                │      │
│     │   patient_encounter_id: 12345  ← NOT file_id       │      │
│     │   disease_id: strabismus_id                        │      │
│     │   task_type: 'encounter_set'                      │      │
│     │   state: 'pending'                                │      │
│     │   assigned_to: NULL (pick up by eligible grader)   │      │
│     │ }                                                   │      │
│     └────────────────────────────────────────────────────┘      │
│                                                                 │
│  3. Assign to Residents                                         │
│     ├─ Add to task queue for lab unit                          │
│     └─ Appears in grading dashboard                            │
└─────────────────────────────────────────────────────────────────┘
```

## Phase 4: Dual Grading

```
┌─────────────────────────────────────────────────────────────────┐
│                     GRADING DASHBOARD                           │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  PENDING TASKS                                          │   │
│  │  ┌─────────────────────────────────────────────────┐   │   │
│  │  │ ST-001 | Strabismus | Patient: PAT-001 | 9 img  │   │   │
│  │  │ ST-002 | Strabismus | Patient: PAT-005 | 7 img  │   │   │
│  │  └─────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            ↓ Click                             │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              3x3 GRID VIEWER                            │   │
│  │  ┌─────┬─────┬─────┐                                   │   │
│  │  │ [1] │ [2] │ [3] │  ← Synchronized zoom/pan          │   │
│  │  ├─────┼─────┼─────┤                                   │   │
│  │  │ [4] │ [5] │ [6] │  ← Position 5 highlighted         │   │
│  │  ├─────┼─────┼─────┤     (primary gaze)                │   │
│  │  │ [7] │ [8] │ [9] │                                   │   │
│  │  └─────┴─────┴─────┘                                   │   │
│  │                                                         │   │
│  │  ☐ Sync Zoom/Pan                                       │   │
│  │                                                         │   │
│  │  Diagnosis:                                             │   │
│  │  ⚪ No Strabismus                                       │   │
│  │  ⚪ Intermittent Strabismus                             │   │
│  │  ⚪ Constant - Small Angle                             │   │
│  │  ⚪ Constant - Large Angle                             │   │
│  │  ⚪ Not Gradable                                        │   │
│  │                                                         │   │
│  │  Comment: [________________]                          │   │
│  │                                                         │   │
│  │  [Submit Grade]  [Save Draft]                          │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Dual Grading Flow

```
         PATIENT ENCOUNTER SET
                 │
        ┌────────┴────────┐
        ▼                 ▼
   RESIDENT          RESIDENT2
    Grade              Grade
        │                 │
        ▼                 ▼
  resident_2       resident2_
   complete          complete
        │                 │
        └────────┬────────┘
                 ▼
        ┌────────────────┐
        │  CONSENSUS     │
        │  CHECK         │
        └───────┬────────┘
                │
       ┌────────┴────────┐
       ▼                 ▼
   AGREE            DISAGREE
       │                 │
       ▼                 ▼
  CONSENSUS         ARBITRATOR
   GRADE              GRADE
       │                 │
       └────────┬────────┘
                ▼
         FINAL DIAGNOSIS
```

## Phase 5: Consensus & Completion

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONSENSUS SERVICE                            │
│                                                                 │
│  1. Check Agreement                                             │
│     ┌────────────────────────────────────────────────────┐      │
│     │ resident_grade == resident2_grade ?                 │      │
│     │   YES → Create consensus, state='consensus'         │      │
│     │   NO  → state='arbitration_required'               │      │
│     └────────────────────────────────────────────────────┘      │
│                                                                 │
│  2. If Consensus:                                               │
│     ├─ Create GradeConsensus record                            │
│     ├─ Link to agreed DiseaseGrading                           │
│     └─ Task complete, ready for export                         │
│                                                                 │
│  3. If Disagreement:                                            │
│     ├─ Assign to Arbitrator                                    │
│     ├─ Show both grades in UI                                  │
│     └─ Arbitrator's grade becomes final                        │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow Summary

```
┌────────────────┐     ┌─────────────────┐     ┌────────────────┐
│  MOBILE UPLOAD │ ──▶ │  VERIFICATION   │ ──▶ │ GRADING TASKS  │
│                │     │                 │     │                │
│ • JWT auth     │     │ • Grid review   │     │ • Dual grading │
│ • 1-9 images   │     │ • PII masking   │     │ • Consensus    │
│ • EXIF strip   │     │ • Not gradable  │     │ • Arbitration  │
└────────────────┘     └─────────────────┘     └────────────────┘
                                                       │
                                                       ▼
                                             ┌────────────────┐
                                             │ FINAL DIAGNOSIS│
                                             │                │
                                             │ • Consensus    │
                                             │ • Export ready │
                                             │ • Audit trail  │
                                             └────────────────┘
```

## State Transitions

### PatientEncounters

| State | Trigger | Next State |
|-------|---------|------------|
| `is_set_based=False` | Created via ZIP | N/A (legacy) |
| `is_set_based=True` | Created via API | `verified_status='pending'` |
| `verified_status='pending'` | Initial state | Awaiting verification |
| `verified_status='verified'` | Optometrist finalizes | Tasks created |

### EncounterSetImage

| State | Trigger | Next State |
|-------|---------|------------|
| `is_reviewed=False` | Initial upload | Pending review |
| `is_reviewed=True` | Optometrist marks reviewed | Ready for grading |
| `is_anonymized=True` | PII masked or none found | Edited version used |
| `is_not_gradable=True` | Quality insufficient | Excluded from assessment |

### GradingTask

| State | Trigger | Next State |
|-------|---------|------------|
| `pending` | Created | `resident_complete` |
| `resident_complete` | Resident submits | `resident2_complete` |
| `resident2_complete` | Resident2 submits | `consensus` or `arbitration_required` |
| `consensus` | Grades agree | Complete |
| `arbitration_required` | Grades disagree | `arbitration_complete` |
| `arbitration_complete` | Arbitrator decides | Complete |

## Related Documentation

- [Core System](../00-Core/encounterSet_grading_system.md) - Data model and architecture
- [Verification](../02-Verify-Anonymize/encounterSet_anonymization.md) - PII masking details
- [Grading Interface](../04-Grade/encounterSet_Grading.md) - Grader UI and submission
- [Dual Grading](comprehensive_dual_grading_system.md) - Consensus algorithms
