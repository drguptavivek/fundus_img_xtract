# Remedio Combined Verification

## Overview

The **Remedio Combined Verification** workflow provides a unified interface for verifying encounters that contain both DR (Diabetic Retinopathy) and Glaucoma reports from Remedio FOP software. Instead of navigating to separate workflows, optometrists can verify all reports and tag images in a single integrated page.

## Key Features

- **Unified Interface**: Verify DR reports, Glaucoma reports, and tag images on one page
- **Side-by-Side Reports**: View DR and Glaucoma PDFs simultaneously
- **Image Tagging**: Mark laterality (left/right/cannot tell) and centering (macula/disk/cannot tell)
- **3-State Visual Indicators**: Thumbnail dots show tagging status (red/yellow/green)
- **Navigation**: Previous/Next encounter for efficient batch processing

## Routes

| Route | Purpose |
|-------|---------|
| `GET /verify_remedio/list` | List encounters pending verification |
| `GET /verify_remedio/detail/<id>` | View encounter details (read-only) |
| `GET /verify_remedio/edit/<id>` | Edit and verify encounter |
| `POST /verify_remedio/edit/<id>/save` | Save encounter data changes |
| `POST /verify_remedio/edit/<id>/verify/dr` | Toggle DR verification |
| `POST /verify_remedio/edit/<id>/verify/glaucoma` | Toggle Glaucoma verification |
| `POST /verify_remedio/edit/<id>/verify/encounter` | Toggle encounter verification |
| `POST /verify_remedio/edit/<id>/tag-side` | Update image laterality |
| `POST /verify_remedio/edit/<id>/tag-centering` | Update image centering |

## Verification Requirements

### DR Verification
- **Independent of image tagging**: DR reports can be verified without tagging images
- Toggle-based: Click "DR Verified" switch to verify/unverify
- Status tracked: `dr_verified_status`, `dr_verified_by`, `dr_verified_at`

### Glaucoma Verification
- **Independent of image tagging**: Glaucoma reports can be verified without tagging images
- Toggle-based: Click "Glaucoma Verified" switch to verify/unverify
- Status tracked: `glaucoma_verified_status`, `glaucoma_verified_by`, `glaucoma_verified_at`

### Encounter Verification
- **Requires all conditions met**:
  1. DR verified (if DR reports present)
  2. Glaucoma verified (if Glaucoma reports present)
  3. All images tagged (both laterality AND centering)
- Status tracked: `encounter_verified_status`, `encounter_verified_by`, `encounter_verified_at`

## UI Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  ← Back  |  ← Prev | Next →                 [Save Changes]    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ ENCOUNTER DETAILS                                       │   │
│  │ Patient ID: [PEC-001    ]  Patient Name: [John Doe    ]│   │
│  │ Capture Date: [2026-01-31]  Zip File: [batch_123.zip ] │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ DR REPORTS                              [DR Verified] ✓ │   │
│  │ Verified by: optometrist_1                              │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │ Result: [Mild DR                              ]       │   │
│  │ Qualitative: [Mild findings with microaneurysms   ]    │   │
│  │ ┌─────────────────────────────────────────────────┐   │   │
│  │ │ │                                             │   │   │
│  │ │ │  DR PDF Viewer (iframe)                      │   │   │
│  │ │ │                                             │   │   │
│  │ └─────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ GLAUCOMA REPORTS                        [Glaucoma ✓]    │   │
│  │ Verified by: optometrist_1                              │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │ VCDR Right: [0.65  ]  VCDR Left: [0.45  ]              │   │
│  │ Result: [Glaucoma Suspect                   ]           │   │
│  │ Qualitative: [High risk, monitor closely     ]         │   │
│  │ ┌─────────────────────────────────────────────────┐   │   │
│  │ │ │                                             │   │   │
│  │ │ │  Glaucoma PDF Viewer (iframe)                │   │   │
│  │ │ │                                             │   │   │
│  │ └─────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ ENCOUNTER IMAGES                              [✓ Verified]│   │
│  │ Laterality + Centering (Macula/Disk/Cannot tell)         │   │
│  │ Verified by: optometrist_1                              │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │ ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐      │   │
│  │ │  🔴 │  🟢 │  🟢 │  🟡 │  🟢 │  🟢 │     │     │      │   │
│  │ │ img1│ img2│ img3│ img4│ img5│ img6│ ... │     │      │   │
│  │ └─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┘      │   │
│  │                                                           │   │
│  │ ┌─────────────────────────────────────────────────┐    │   │
│  │ │                                                  │    │   │
│  │ │            Main Image Viewer                    │    │   │
│  │ │                                                  │    │   │
│  │ └─────────────────────────────────────────────────┘    │   │
│  │                                                           │   │
│  │ ┌─────────────────────────────────────────────────┐    │   │
│  │ │ EYE SIDE:         CENTERING:                     │    │   │
│  │ │ [Left] [Right] [?]   [Macula] [Disk] [?]        │    │   │
│  │ └─────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Image Tagging System

### Laterality (Eye Side)

| Button | Value | Icon |
|--------|-------|------|
| Left | `left` | 👁️ |
| Right | `right` | 👁️ |
| Cannot Tell | `cannot_tell` | ❓ |

### Centering

| Button | Value | Description |
|--------|-------|-------------|
| Macula | `macula` | Image centered on macula |
| Disk | `disk` | Image centered on optic disk |
| Cannot Tell | `cannot_tell` | Cannot determine centering |

### Thumbnail Status Indicator

| Color | State | Meaning |
|-------|-------|---------|
| 🔴 Red | `tag_ok=false` | Neither side nor centering tagged |
| 🟡 Yellow | `tag_partial=true` | Only side OR centering tagged |
| 🟢 Green | `tag_ok=true` | Both side AND centering tagged |

## API Endpoints

### Verify/Unverify DR

```http
POST /verify_remedio/edit/<encounter_id>/verify/dr
Content-Type: application/x-www-form-urlencoded
X-CSRFToken: <token>

Response:
{
  "ok": true,
  "status": "verified",
  "by": "optometrist_1"
}
```

### Verify/Unverify Glaucoma

```http
POST /verify_remedio/edit/<encounter_id>/verify/glaucoma
Content-Type: application/x-www-form-urlencoded
X-CSRFToken: <token>

Response:
{
  "ok": true,
  "status": "verified",
  "by": "optometrist_1"
}
```

### Verify/Unverify Encounter

```http
POST /verify_remedio/edit/<encounter_id>/verify/encounter
Content-Type: application/x-www-form-urlencoded
X-CSRFToken: <token>

Response:
{
  "ok": true,
  "status": "verified",
  "by": "optometrist_1",
  "next_url": "/verify_remedio/edit/25"  # Auto-advance if enabled
}
```

### Update Image Laterality

```http
POST /verify_remedio/edit/<encounter_id>/tag-side
Content-Type: application/x-www-form-urlencoded
X-CSRFToken: <token>

ef_id=<image_id>
side=left

Response:
{
  "ok": true,
  "ef_id": 456
}
```

### Update Image Centering

```http
POST /verify_remedio/edit/<encounter_id>/tag-centering
Content-Type: application/x-www-form-urlencoded
X-CSRFToken: <token>

ef_id=<image_id>
centering=macula

Response:
{
  "ok": true,
  "ef_id": 456
}
```

## Verification Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. LIST ENCOUNTERS                                             │
│     GET /verify_remedio/list                                   │
│     ├─ Filter by capture date                                  │
│     ├─ Show patient ID, name, capture date                     │
│     └─ Click "Edit" to verify                                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  2. EDIT ENCOUNTER                                              │
│     GET /verify_remedio/edit/<id>                              │
│     ├─ Review DR report (if present)                           │
│     ├─ Review Glaucoma report (if present)                     │
│     └─ Tag images with laterality and centering                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  3. VERIFY REPORTS (Independent)                               │
│     ├─ Toggle "DR Verified" if DR report looks correct         │
│     └─ Toggle "Glaucoma Verified" if Glaucoma report correct   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  4. TAG IMAGES                                                  │
│     ├─ Click each image thumbnail                             │
│     ├─ Select eye side (left/right/cannot tell)               │
│     ├─ Select centering (macula/disk/cannot tell)             │
│     └─ Thumbnail dot changes: red → yellow → green            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  5. FINALIZE ENCOUNTER VERIFICATION                            │
│     ├─ All reports verified (if present)                      │
│     ├─ All images tagged (green dots)                         │
│     └─ Toggle "Encounter Verified"                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  6. AUTO-ADVANCE                                                │
│     └─ Redirect to next unverified encounter                   │
└─────────────────────────────────────────────────────────────────┘
```

## Database Model

### PatientEncounters Verification Fields

```python
# DR-specific verification
dr_verified_status: Mapped[str | None]  # 'verified' or NULL
dr_verified_by: Mapped[str | None]      # Username
dr_verified_at: Mapped[datetime | None] # Timestamp

# Glaucoma-specific verification
glaucoma_verified_status: Mapped[str | None]  # 'verified' or NULL
glaucoma_verified_by: Mapped[str | None]      # Username
glaucoma_verified_at: Mapped[datetime | None] # Timestamp

# General encounter verification
encounter_verified_status: Mapped[str | None]  # 'verified' or NULL
encounter_verified_by: Mapped[str | None]      # Username
encounter_verified_at: Mapped[datetime | None] # Timestamp
```

### EncounterFile Tagging Fields

```python
eye_side: Mapped[str | None]      # 'left', 'right', 'cannot_tell'
centering: Mapped[str | None]     # 'macula', 'disk', 'cannot_tell'
```

## Glaucoma Data Processing

### Raw Report Cleaning

The system automatically creates "cleaned" rows from raw Glaucoma reports:

```python
def _ensure_glaucoma_cleaned_rows(db, encounter):
    """
    Creates GlaucomaResultsCleaned rows from GlaucomaReport.

    Extracts numeric VCDR values from OCR text:
    - "0.65" → 0.65
    - "0.65 ± 0.05" → 0.65
    - "0.6-0.7" → 0.6
    """
```

### Cleaned Row Fields

| Field | Source | Description |
|-------|--------|-------------|
| `vcdr_right_num` | Parsed from `vcdr_right` | Numeric value (0.0-1.0) |
| `vcdr_left_num` | Parsed from `vcdr_left` | Numeric value (0.0-1.0) |
| `original_vcdr_right` | Raw `vcdr_right` | Original OCR text |
| `original_vcdr_left` | Raw `vcdr_left` | Original OCR text |
| `result` | From report | Result text |
| `qualitative_result` | From report | Qualitative assessment |

## Task Creation Integration

After verification, grading tasks are created based on verified status:

```python
# DR task created if:
enc.dr_verified_status == 'verified'  # Direct DR verification
# OR
enc.encounter_verified_status == 'verified'  # General verification

# Glaucoma task created if:
enc.glaucoma_verified_status == 'verified'  # Glaucoma verification
```

## Differences from Separate Workflows

| Aspect | Combined (`verify_remedio`) | Separate (`verify_remedio_dr`, `verify_remedio_glaucoma`) |
|--------|----------------------------|--------------------------------------------------------------|
| **Interface** | Single page with all reports | Separate pages for each disease |
| **Navigation** | Prev/Next between encounters | Separate lists per disease |
| **Image Tagging** | Integrated on same page | Separate workflow |
| **Best For** | Encounters with multiple reports | Focusing on one disease at a time |

## Access Control

**Required Roles:**
- `admin`
- `local_admin`
- `fileUploader`
- `optometrist`
- `data_manager`

**Lab Unit Scoping:**
- Users can only verify encounters from their assigned lab units
- Cross-lab access returns 404

## Related Documentation

- [DR Verification Details](dr-verification-details.md) - DR-specific workflow
- [Glaucoma Verification Details](glaucoma-verification-details.md) - Glaucoma-specific workflow
- [No DR Verification Details](no-dr-verification-details.md) - Fallback for missing DR reports
- [Verification Workflows Overview](verification-workflows-overview.md) - System-wide overview
