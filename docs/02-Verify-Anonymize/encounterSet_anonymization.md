# EncounterSet Anonymization & Verification

## Overview

The verification phase is where optometrists review EncounterSet images, confirm spatial positioning, and apply PII (Personally Identifiable Information) masking. This is a **critical security step** before images reach graders.

## Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. MOBILE UPLOAD                                               │
│     ├─ Patient uploads 1-9 images via API                       │
│     ├─ Images stored with EXIF stripped                        │
│     └─ Status: pending, is_set_based=True                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  2. VERIFICATION LISTING                                        │
│     ├─ Optometrist views unverified sets                        │
│     ├─ GET /verify_encounter_set/                               │
│     └─ Filters: is_set_based=True, verified_status!=verified   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  3. GRID VERIFICATION                                           │
│     ├─ GET /verify_encounter_set/verify/<uuid>                 │
│     ├─ Review spatial positions (1-9 grid)                     │
│     ├─ Reorder images via drag-drop or API                     │
│     └─ Confirm correct cardinal positions                       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  4. PII MASKING (Per-Image)                                    │
│     ├─ GET /verify_encounter_set/edit/<uuid>                   │
│     ├─ Open image editor with crop/mask tools                  │
│     ├─ Create edited version: <uuid>_edited.jpg                │
│     └─ Mark as: is_anonymized=True, is_reviewed=True          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  5. QUALITY CHECK                                               │
│     ├─ Mark poor quality images: is_not_gradable=True          │
│     ├─ Provide reason: "Blurry", "Overexposed", etc.           │
│     └─ Alternative: Mark all as anonymized (no PII detected)   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  6. FINALIZE                                                     │
│     ├─ POST /verify_encounter_set/finalize/<uuid>              │
│     ├─ Validates: All images reviewed                          │
│     ├─ Sets: encounter_verified_status='verified'              │
│     └─ Triggers: GradingTask creation                          │
└─────────────────────────────────────────────────────────────────┘
```

## API Endpoints

### Listing Unverified Sets

```http
GET /verify_encounter_set/
Authorization: Session cookie
```

Returns HTML page with list of pending encounter sets.

### Verify Specific Set

```http
GET /verify_encounter_set/verify/<uuid>
Authorization: Session cookie
```

Returns grid view with images in positions 1-9.

### Update Spatial Position

```http
POST /verify_encounter_set/update_position
Content-Type: application/json

{
  "image_uuid": "abc-123",
  "position": 5
}
```

**Response:**
- `200` - Position updated
- `404` - Image not found
- `409` - Position occupied (auto-swaps if implemented)

### Edit Image (PII Masking)

```http
GET /verify_encounter_set/edit/<uuid>
```

Returns editor interface with:
- Original or edited image display
- Crop/mask tools
- Save and restore options

### Save Edited Image

```http
POST /verify_encounter_set/save_edit/<uuid>
Content-Type: application/json

{
  "crop_coords": { "x": 10, "y": 10, "width": 800, "height": 600 },
  "mask_regions": [...]
}
```

**Backend actions:**
1. Creates `<uuid>_edited.jpg` using PIL
2. Updates `edited_filename` in database
3. Sets `is_anonymized=True`, `is_reviewed=True`

### Mark Anonymized (No Editing Required)

```http
POST /verify_encounter_set/mark_anonymized/<uuid>
```

Use when image has no PII but needs review confirmation.

### Mark All Anonymized (Batch)

```http
POST /verify_encounter_set/mark_all_anonymized/<encounter_uuid>
```

Marks all images in set as reviewed and anonymized.

### Mark Not Gradable

```http
POST /verify_encounter_set/mark_not_gradable/<uuid>
Content-Type: application/json

{
  "reason": "Image too blurry for assessment"
}
```

**Backend actions:**
1. Sets `is_not_gradable=True`
2. Stores `not_gradable_reason`
3. Sets `is_reviewed=True` (reviewed but cannot be graded)

### Restore Original

```http
POST /verify_encounter_set/restore_original/<uuid>
```

**Actions:**
- Deletes `<uuid>_edited.jpg` file
- Sets `edited_filename=NULL`
- Blocked if grading tasks are in progress

### Finalize Verification

```http
POST /verify_encounter_set/finalize/<encounter_uuid>
```

**Prerequisites:**
- All images have `is_reviewed=True`
- Every gradable, task-eligible image has values for metadata fields used by active image-task routing rules (for example, `laterality`)

**Actions:**
- Sets `encounter_verified_status='verified'`
- Records `encounter_verified_by`, `encounter_verified_at`
- Triggers `GradingTask` creation for the encounter

## Image States

| State | `is_reviewed` | `is_anonymized` | `is_not_gradable` | Meaning |
|-------|---------------|-----------------|-------------------|---------|
| Pending | `False` | `False` | `False` | New upload, not reviewed |
| Ready | `True` | `True` | `False` | No PII found, ready for grading |
| Masked | `True` | `True` | `False` | PII masked, edited version created |
| Not Gradable | `True` | `False` | `True` | Quality insufficient, reason stored |
| Edited | `True` | `True` | `False` | Has edited version for grading |

## Security Considerations

### Editing Restrictions

Once grading tasks are created, image editing is **blocked**:

```python
active_tasks = [s for s in task_states if s and s.lower() != 'pending']
if active_tasks:
    # Block editing - grading in progress
```

### Media Serving Priority

Grading viewers always prioritize the edited version:

```python
if img.edited_filename:
    return serve_edited_version()
else:
    return serve_original()
```

### Access Control

All verification routes require:
- Authentication: `@login_required`
- Roles: `@roles_required("admin", "optometrist", "data_manager")`
- Lab Unit Scoping: User must belong to encounter's `lab_unit_id`

## File Management

### Storage Paths

```
files/encounter_sets/YYYY_MM_DD/<encounter_id>/
├── <uuid>.jpg              # Original (always kept)
├── <uuid>_edited.jpg       # Edited (created during verification)
└── thm_<uuid>.jpg          # Thumbnail (background job)
```

### Deletion Policy

- **Original**: Never deleted (audit trail)
- **Edited**: Deleted when "Restore Original" is clicked
- **Thumbnail**: Regenerated if missing

## Related Documentation

- [Core System](../00-Core/encounterSet_grading_system.md) - Data model overview
- [Grading Workflow](../04-Grade/encounterSet_Grading.md) - Post-verification flow
- [Complete Workflow](../08-Workflow/EncounterSet_grading_workflow.md) - Full pipeline
