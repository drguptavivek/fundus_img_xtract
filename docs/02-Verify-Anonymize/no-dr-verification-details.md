# No DR Report Verification Workflow Details

This document provides detailed technical documentation for the "No DR Report" verification workflow, which serves as a fallback mechanism for encounters without DR PDF reports.

## Overview

The No DR Report verification workflow processes encounters that do NOT contain DR PDF reports from Remedio camera uploads. This workflow provides a fallback mechanism to ensure that DR grading tasks can still be created for images even when no DR PDF is available. It requires manual verification of image quality and laterality before allowing DR grading tasks to be created.

## Table of Contents

1. [Route Structure](#route-structure)
2. [Database Models](#database-models)
3. [Verification Process](#verification-process)
4. [Task Creation Logic](#task-creation-logic)
5. [UI Components](#ui-components)
6. [API Endpoints](#api-endpoints)
7. [Error Handling](#error-handling)
8. [Security Considerations](#security-considerations)

## Route Structure

### Main Routes

| Route | Method | Purpose | Template |
|-------|--------|---------|----------|
| `/verify_remedio_nodr/list` | GET | List encounters without DR PDFs | `verify_remedio_nodr/list.html` |
| `/verify_remedio_nodr/edit/<int:encounter_id>` | GET/POST | Edit/view individual encounter | `verify_remedio_nodr/edit.html` |
| `/verify_remedio_nodr/mark_eye/<int:encounter_id>` | POST | Mark image laterality | N/A (AJAX) |
| `/verify_remedio_nodr/verify/<int:encounter_id>` | POST | Verify an encounter | N/A (AJAX/Redirect) |
| `/verify_remedio_nodr/unverify/<int:encounter_id>` | POST | Unverify an encounter | N/A (AJAX/Redirect) |

### Key Files

- **Route Module**: `verify_remedio_nodr/routes.py`
- **Templates**: `templates/verify_remedio_nodr/`
- **Navigation**: `templates/base.html` (lines 181-183)

## Database Models

### Primary Models

1. **PatientEncounters**: Contains verification status fields
2. **EncounterFile**: Represents images within encounters (with eye_side field)
3. **DiabeticRetinopathyReport**: Used to filter OUT encounters with DR reports

### Key Fields

```python
# In PatientEncounters model
encounter_verified_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
encounter_verified_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
encounter_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

# In EncounterFile model
eye_side: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
```

### Eye Side Values

- `'right'`: Right eye image
- `'left'`: Left eye image
- `'cannot_tell'`: Unable to determine laterality
- `NULL`: Not yet tagged (default state)

## Verification Process

### 1. Listing Encounters for Verification

**Function**: `nodr_list()`

**Query Logic**:
```python
def _base_encounter_query(db: Session, restricted_lab_units: set[int] | None):
    query = (
        db.query(PatientEncounters)
        .outerjoin(DiabeticRetinopathyReport, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
        .filter(DiabeticRetinopathyReport.id.is_(None))  # Only encounters WITHOUT DR reports
        .filter(PatientEncounters.zip_file_id.isnot(None))
    )
    if restricted_lab_units is not None:
        query = query.filter(PatientEncounters.lab_unit_id.in_(restricted_lab_units))
    return query
```

**Features**:
- Date-based pagination
- Filtering by verification status (all/verified/unverified)
- User-specific lab unit restrictions
- Recent verification activity tracking

### 2. Individual Encounter Verification

**Function**: `nodr_verify(encounter_id)`

**Process**:
1. Validate user permissions
2. Check if encounter exists and is accessible
3. **Verify all images have eye side tagged** (critical requirement)
4. Set verification status to 'verified'
5. Record verifier and timestamp
6. Create DR grading tasks for associated images
7. Commit transaction

**Key Code**:
```python
# Check that all images have eye side tagged
missing = [ef for ef in encounter.encounter_files 
           if ef.file_type == 'image' and (ef.eye_side not in {'right', 'left', 'cannot_tell'})]

if missing:
    msg = f"{len(missing)} image(s) still untagged; cannot verify."
    return {"ok": False, "error": "incomplete", "message": msg}

# Set verification status
encounter.encounter_verified_status = 'verified'
encounter.encounter_verified_by = getattr(current_user, 'username', 'unknown')
encounter.encounter_verified_at = utcnow()

# Create DR grading tasks
try:
    dr_disease = _get_dr_disease(db)
    if dr_disease:
        images = db.query(EncounterFile).filter(
            EncounterFile.patient_encounter_id == encounter.id
        ).all()
        
        for image in images:
            ensure_task(image.uuid, dr_disease.id)
```

### 3. Image Laterality Tagging

**Function**: `nodr_mark_eye(encounter_id)`

**Process**:
1. Validate user permissions
2. Check if image belongs to encounter
3. Set eye side (right/left/cannot_tell)
4. Update database
5. Return AJAX response

**Key Code**:
```python
side = (request.form.get("side") or "").strip().lower()
if side not in {"right", "left", "cannot_tell"}:
    return {"ok": False, "error": "invalid_side"}, 400

ef.eye_side = side
db.add(ef)
db.commit()

return {"ok": True, "ef_id": ef.id, "side": ef.eye_side}
```

### 4. Unverification Process

**Function**: `nodr_unverify(encounter_id)`

**Process**:
1. Verify user permissions
2. Check if tasks can be removed (only pending tasks)
3. Clear verification status
4. Remove pending DR grading tasks
5. Commit transaction

## Task Creation Logic

### Verification Gating

The No DR verification system integrates with `TaskCreationServices` through the `_is_verified_for_disease()` function:

```python
def _is_verified_for_disease(db, kind: str, image_id: int, disease_id: int) -> bool:
    # For DR: requires dr_verified_status == 'verified' OR encounter_verified_status == 'verified'
    if name in ('diabetic retinopathy', 'dr'):
        return (enc.dr_verified_status == 'verified') or (enc.encounter_verified_status == 'verified')
```

### Fallback Mechanism

This workflow provides the **fallback mechanism** for DR verification:

- **Primary path**: DR PDF verification (`dr_verified_status`)
- **Fallback path**: General encounter verification (`encounter_verified_status`)
- **Either path** can enable DR task creation

### Task Creation Flow

1. **Verification Trigger**: User verifies an encounter without DR PDF
2. **Disease Lookup**: Find DR disease in database
3. **Image Identification**: Get all images for the encounter
4. **Task Creation**: Call `ensure_task()` for each image
5. **Error Handling**: Log any task creation failures

## UI Components

### List View Features

- **Date-based pagination**: Navigate by capture dates
- **Status filtering**: Show all/verified/unverified encounters
- **Quick actions**: Edit/verify buttons
- **Recent activity**: Show user's recent verifications
- **Navigation links**: Quick access to recent verified/unverified dates

### Edit View Features

- **Image gallery**: Display all images in the encounter
- **Eye side tagging**: Interactive buttons to tag each image
- **Patient details**: Edit patient information
- **Verification toggle**: Switch verification status (only enabled when all images tagged)
- **Progress indicators**: Show completion status

### Eye Tagging Interface

**JavaScript-powered interactive elements**:
```html
<div class="eye-tagging-interface">
  <div class="image-preview">
    <img src="{{ image_url }}" alt="Fundus image">
  </div>
  <div class="eye-selection-buttons">
    <button class="btn btn-outline-primary" onclick="tagEye('{{ image_id }}', 'right')">
      Right Eye
    </button>
    <button class="btn btn-outline-primary" onclick="tagEye('{{ image_id }}', 'left')">
      Left Eye
    </button>
    <button class="btn btn-outline-secondary" onclick="tagEye('{{ image_id }}', 'cannot_tell')">
      Cannot Tell
    </button>
  </div>
</div>
```

### JavaScript Interactions

- **AJAX eye tagging**: Tag images without page reload
- **Real-time validation**: Enable verification only when all images tagged
- **Progress tracking**: Show tagging completion status
- **Form validation**: Ensure all required steps completed

## API Endpoints

### Eye Tagging Endpoint

**URL**: `POST /verify_remedio_nodr/mark_eye/<int:encounter_id>`

**Request**:
```json
{
  "side": "right|left|cannot_tell",
  "ef_id": "123",
  "csrf_token": "..."
}
```

**Response**:
```json
{
  "ok": true,
  "ef_id": 123,
  "side": "right"
}
```

### Verification Endpoint

**URL**: `POST /verify_remedio_nodr/verify/<int:encounter_id>`

**Request**:
```json
{
  "csrf_token": "..."
}
```

**Response (Success)**:
```json
{
  "ok": true,
  "status": "verified",
  "by": "username"
}
```

**Response (Error - Incomplete tagging)**:
```json
{
  "ok": false,
  "error": "incomplete",
  "message": "2 image(s) still untagged; cannot verify."
}
```

## Error Handling

### Common Error Scenarios

1. **Permission Denied**: User lacks required roles
2. **Encounter Not Found**: Invalid encounter ID
3. **Incomplete Tagging**: Not all images have eye side tagged
4. **Task Creation Failure**: Unable to create grading tasks
5. **Database Constraint Violation**: Invalid data state

### Error Handling Pattern

```python
try:
    # Verification logic
    db.commit()
    flash("Encounter verified successfully.", "success")
except Exception as e:
    db.rollback()
    current_app.logger.exception("Failed to verify encounter %s: %s", encounter_id, e)
    flash("Failed to verify encounter. Please try again.", "danger")
```

### Validation Rules

```python
# Validate eye side values
if side not in {"right", "left", "cannot_tell"}:
    return {"ok": False, "error": "invalid_side"}, 400

# Check all images are tagged before verification
missing = [ef for ef in encounter.encounter_files 
           if ef.file_type == 'image' and (ef.eye_side not in {'right', 'left', 'cannot_tell'})]

if missing:
    msg = f"{len(missing)} image(s) still untagged; cannot verify."
    return {"ok": False, "error": "incomplete", "message": msg}
```

## Security Considerations

### Access Control

- **Role-based access**: Requires `admin`, `optometrist`, or `data_manager` roles
- **Lab unit restrictions**: Users can only access assigned lab units
- **CSRF protection**: All forms include CSRF tokens

### Data Integrity

- **Transaction management**: All operations wrapped in database transactions
- **Audit trail**: Track who verified what and when
- **Validation**: Input validation and sanitization
- **Completeness checks**: Ensure all required data is provided

### Privacy Considerations

- **Patient data**: Handle PHI according to privacy requirements
- **Access logging**: Log all verification and tagging actions
- **Data retention**: Follow data retention policies

## Performance Considerations

### Database Optimization

- **Indexing**: Verification status and eye side fields are indexed
- **Query optimization**: Efficient joins and filtering
- **Pagination**: Limit results per page
- **Image loading**: Optimize image preview loading

### Caching Strategy

- **User permissions**: Cache user lab unit assignments
- **Disease lookups**: Cache disease information
- **Static assets**: Optimize image loading
- **Thumbnail generation**: Pre-generate image thumbnails

## Workflow Integration

### Relationship to Other Workflows

1. **Complementary to DR PDF verification**: Handles cases where DR PDF is missing
2. **Independent of Glaucoma verification**: Separate workflow for different disease
3. **Task creation integration**: Creates DR tasks through same mechanism as DR PDF verification

### Quality Assurance

The workflow includes several quality assurance steps:

1. **Manual review**: User must manually review each image
2. **Laterality confirmation**: Explicit eye side tagging required
3. **Completeness check**: All images must be tagged before verification
4. **Audit trail**: Complete record of who tagged what and when

## Monitoring and Logging

### Key Metrics to Monitor

- **Tagging completion rates**: Track how many encounters get fully tagged
- **Verification rates**: Track verification completion after tagging
- **Processing times**: Monitor time from upload to verification
- **User activity**: Monitor tagging and verification patterns
- **Error rates**: Track failed tagging/verification attempts

### Logging Strategy

```python
current_app.logger.info("Encounter %s verified by %s via No-DR workflow", encounter_id, current_user.username)
current_app.logger.info("Image %s tagged as %s by %s", image_id, side, current_user.username)
current_app.logger.exception("Failed to create DR tasks for no-DR encounter %s: %s", encounter_id, e)
```

## Best Practices

### For Users

1. **Tag all images**: Ensure every image has eye side specified
2. **Use "Cannot Tell" appropriately**: When laterality is unclear
3. **Verify image quality**: Only verify encounters with good quality images
4. **Document decisions**: Use comments when verification decisions are unclear

### For Developers

1. **Validate inputs**: Ensure all eye side values are valid
2. **Handle edge cases**: Account for encounters with no images
3. **Provide feedback**: Clear error messages for incomplete tagging
4. **Maintain audit trail**: Log all tagging and verification actions

## Related Documentation

- [Verification Workflows Overview](verification-workflows-overview.md)
- [DR Verification Details](dr-verification-details.md)
- [Glaucoma Verification Details](glaucoma-verification-details.md)
- [Task Creation Services](../03-Tasks/taskCreationServices.md)
- [Database Schema](../00-Core/models.md)