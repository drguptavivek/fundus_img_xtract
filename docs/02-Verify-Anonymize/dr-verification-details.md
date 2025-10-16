# DR PDF Verification Workflow Details

This document provides detailed technical documentation for the DR (Diabetic Retinopathy) PDF verification workflow.

## Overview

The DR verification workflow processes encounters that contain DR PDF reports from Remedio camera uploads. This workflow ensures that DR reports are reviewed and verified before allowing DR grading tasks to be created for the associated images.

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
| `/verify_remedio_dr/verify_dr_list` | GET | List encounters with DR PDFs | `verify_remedio_dr/list.html` |
| `/verify_remedio_dr/verify_dr_edit/<int:report_id>` | GET/POST | Edit/view individual DR report | `verify_remedio_dr/edit.html` |
| `/verify_remedio_dr/verify_dr_verify/<int:report_id>` | POST | Verify a DR report | N/A (AJAX/Redirect) |
| `/verify_remedio_dr/verify_dr_unverify/<int:report_id>` | POST | Unverify a DR report | N/A (AJAX/Redirect) |
| `/verify_remedio_dr/verify_dr_results` | GET | Dashboard with statistics | `verify_remedio_dr/results.html` |

### Key Files

- **Route Module**: `verify_remedio_dr/routes.py`
- **Templates**: `templates/verify_remedio_dr/`
- **Navigation**: `templates/base.html` (lines 176-183)

## Database Models

### Primary Models

1. **PatientEncounters**: Contains verification status fields
2. **DiabeticRetinopathyReport**: Represents DR PDF reports
3. **EncounterFile**: Represents images within encounters

### Key Fields

```python
# In PatientEncounters model
dr_verified_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
dr_verified_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
dr_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

# In DiabeticRetinopathyReport model
patient_encounter_id: Mapped[int] = mapped_column(ForeignKey('patient_encounters.id'))
result: Mapped[str]
qualitative_result: Mapped[str | None] = mapped_column(nullable=True)
```

## Verification Process

### 1. Listing Encounters for Verification

**Function**: `verify_dr_list()`

**Query Logic**:
```python
base_query = (
    db.query(DiabeticRetinopathyReport)
    .join(PatientEncounters, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
    .filter(DiabeticRetinopathyReport.result.isnot(None))
)
```

**Features**:
- Pagination by date
- Filtering by verification status (all/verified/unverified)
- User-specific lab unit restrictions
- Search functionality

### 2. Individual Report Verification

**Function**: `verify_dr_verify(report_id)`

**Process**:
1. Validate user permissions
2. Check if report exists and is accessible
3. Set verification status to 'verified'
4. Record verifier and timestamp
5. Create DR grading tasks for associated images
6. Commit transaction

**Key Code**:
```python
# Set verification status
enc.dr_verified_status = 'verified'
enc.dr_verified_by = getattr(current_user, 'username', 'unknown')
enc.dr_verified_at = utcnow()

# Create grading tasks
try:
    dr_disease = db.query(Disease).filter(
        func.lower(Disease.name) == 'diabetic retinopathy'
    ).first()
    
    if dr_disease:
        images = db.query(EncounterFile).filter(
            EncounterFile.patient_encounter_id == enc.id
        ).all()
        
        for image in images:
            ensure_task(image.uuid, dr_disease.id)
```

### 3. Unverification Process

**Function**: `verify_dr_unverify(report_id)`

**Process**:
1. Verify user permissions
2. Check if tasks can be removed (only pending tasks)
3. Clear verification status
4. Remove pending grading tasks
5. Commit transaction

## Task Creation Logic

### Verification Gating

The DR verification system integrates with `TaskCreationServices` through the `_is_verified_for_disease()` function:

```python
def _is_verified_for_disease(db, kind: str, image_id: int, disease_id: int) -> bool:
    # For DR: requires dr_verified_status == 'verified' OR encounter_verified_status == 'verified'
    if name in ('diabetic retinopathy', 'dr'):
        return (enc.dr_verified_status == 'verified') or (enc.encounter_verified_status == 'verified')
```

### Task Creation Flow

1. **Verification Trigger**: User verifies a DR report
2. **Disease Lookup**: Find DR disease in database
3. **Image Identification**: Get all images for the encounter
4. **Task Creation**: Call `ensure_task()` for each image
5. **Error Handling**: Log any task creation failures

## UI Components

### List View Features

- **Date-based pagination**: Navigate by capture dates
- **Status filtering**: Show all/verified/unverified reports
- **Quick actions**: Verify/unverify buttons
- **Search functionality**: Filter by patient details
- **Recent activity**: Show user's recent verifications

### Edit View Features

- **PDF viewer**: Display the DR report
- **Patient details**: Edit patient information
- **Verification toggle**: Switch verification status
- **Image preview**: Show associated fundus images
- **Navigation**: Previous/next report navigation

### JavaScript Interactions

- **AJAX verification**: Toggle verification without page reload
- **Form validation**: Ensure required fields are completed
- **Loading states**: Show progress during operations

## API Endpoints

### Verification Endpoint

**URL**: `POST /verify_remedio_dr/verify_dr_verify/<int:report_id>`

**Request**:
```json
{
  "csrf_token": "..."
}
```

**Response (AJAX)**:
```json
{
  "ok": true,
  "status": "verified",
  "by": "username"
}
```

**Error Response**:
```json
{
  "ok": false,
  "error": "permission_denied"
}
```

## Error Handling

### Common Error Scenarios

1. **Permission Denied**: User lacks required roles
2. **Report Not Found**: Invalid report ID
3. **Task Creation Failure**: Unable to create grading tasks
4. **Database Constraint Violation**: Invalid data state

### Error Handling Pattern

```python
try:
    # Verification logic
    db.commit()
    flash("Report verified successfully.", "success")
except Exception as e:
    db.rollback()
    current_app.logger.exception("Failed to verify DR report %s: %s", report_id, e)
    flash("Failed to verify report. Please try again.", "danger")
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

### Privacy Considerations

- **Patient data**: Handle PHI according to privacy requirements
- **Access logging**: Log all verification actions
- **Data retention**: Follow data retention policies

## Performance Considerations

### Database Optimization

- **Indexing**: Verification status fields are indexed
- **Query optimization**: Efficient joins and filtering
- **Pagination**: Limit results per page

### Caching Strategy

- **User permissions**: Cache user lab unit assignments
- **Disease lookups**: Cache disease information
- **Static assets**: Optimize PDF and image loading

## Monitoring and Logging

### Key Metrics to Monitor

- **Verification rates**: Track verification completion
- **Processing times**: Monitor verification performance
- **Error rates**: Track failed verification attempts
- **User activity**: Monitor verification patterns

### Logging Strategy

```python
current_app.logger.info("DR report %s verified by %s", report_id, current_user.username)
current_app.logger.exception("Failed to create DR tasks for report %s", report_id)
```

## Related Documentation

- [Verification Workflows Overview](verification-workflows-overview.md)
- [Glaucoma Verification Details](glaucoma-verification-details.md)
- [No DR Report Verification Details](no-dr-verification-details.md)
- [Task Creation Services](../03-Tasks/taskCreationServices.md)
- [Database Schema](../00-Core/models.md)