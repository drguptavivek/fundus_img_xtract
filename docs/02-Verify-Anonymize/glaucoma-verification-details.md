# Glaucoma PDF Verification Workflow Details

This document provides detailed technical documentation for the Glaucoma PDF verification workflow.

## Overview

The Glaucoma verification workflow processes encounters that contain Glaucoma PDF reports from Remedio camera uploads. This workflow ensures that Glaucoma reports are reviewed and verified before allowing Glaucoma grading tasks to be created for the associated images.

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
| `/verify_remedio_glaucoma/glaucoma_list` | GET | List encounters with Glaucoma PDFs | `verify_remedio_glaucoma/list.html` |
| `/verify_remedio_glaucoma/glaucoma_edit/<int:report_id>` | GET/POST | Edit/view individual Glaucoma report | `verify_remedio_glaucoma/edit.html` |
| `/verify_remedio_glaucoma/glaucoma_verify/<int:report_id>` | POST | Verify a Glaucoma report | N/A (AJAX/Redirect) |
| `/verify_remedio_glaucoma/glaucoma_unverify/<int:report_id>` | POST | Unverify a Glaucoma report | N/A (AJAX/Redirect) |
| `/verify_remedio_glaucoma/glaucoma_results` | GET | Dashboard with statistics | `verify_remedio_glaucoma/results.html` |

### Key Files

- **Route Module**: `verify_remedio_glaucoma/routes.py`
- **Templates**: `templates/verify_remedio_glaucoma/`
- **Navigation**: `templates/base.html` (lines 156-167)

## Database Models

### Primary Models

1. **PatientEncounters**: Contains verification status fields
2. **GlaucomaReport**: Represents Glaucoma PDF reports
3. **GlaucomaResultsCleaned**: Processed/cleaned glaucoma results
4. **EncounterFile**: Represents images within encounters

### Key Fields

```python
# In PatientEncounters model
glaucoma_verified_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
glaucoma_verified_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
glaucoma_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

# In GlaucomaReport model
patient_encounter_id: Mapped[int] = mapped_column(ForeignKey('patient_encounters.id'))
vcdr_right: Mapped[str | None]
vcdr_left: Mapped[str | None]
result: Mapped[str]
qualitative_result: Mapped[str | None] = mapped_column(nullable=True)

# In GlaucomaResultsCleaned model
glaucoma_report_id: Mapped[int] = mapped_column(ForeignKey('glaucoma_reports.id'), unique=True)
vcdr_right_num: Mapped[float | None] = mapped_column(nullable=True)
vcdr_left_num: Mapped[float | None] = mapped_column(nullable=True)
```

## Verification Process

### 1. Listing Encounters for Verification

**Function**: `glaucoma_list()`

**Query Logic**:
```python
base_query = (
    db.query(GlaucomaReport)
    .join(PatientEncounters, GlaucomaReport.patient_encounter_id == PatientEncounters.id)
    .filter(GlaucomaReport.result.isnot(None))
)
```

**Features**:
- Pagination by date
- Filtering by verification status (all/verified/unverified)
- User-specific lab unit restrictions
- Search functionality
- Support for cleaned/unfiltered results view

### 2. Individual Report Verification

**Function**: `glaucoma_verify(report_id)`

**Process**:
1. Validate user permissions
2. Check if report exists and is accessible
3. Set verification status to 'verified'
4. Record verifier and timestamp
5. Create Glaucoma grading tasks for associated images
6. Commit transaction

**Key Code**:
```python
# Set verification status
enc.glaucoma_verified_status = 'verified'
enc.glaucoma_verified_by = getattr(current_user, 'username', 'unknown')
enc.glaucoma_verified_at = utcnow()

# Create grading tasks
try:
    glaucoma_disease = db.query(Disease).filter(
        func.lower(Disease.name) == 'glaucoma'
    ).first()
    
    if glaucoma_disease:
        images = db.query(EncounterFile).filter(
            EncounterFile.patient_encounter_id == enc.id
        ).all()
        
        for image in images:
            ensure_task(image.uuid, glaucoma_disease.id)
```

### 3. Unverification Process

**Function**: `glaucoma_unverify(report_id)`

**Process**:
1. Verify user permissions
2. Check if tasks can be removed (only pending tasks)
3. Clear verification status
4. Remove pending grading tasks
5. Commit transaction

### 4. Results Processing

**Function**: `glaucoma_results()`

**Features**:
- Dashboard with verification statistics
- Charts showing verification trends
- User-specific verification history
- Performance metrics

## Task Creation Logic

### Verification Gating

The Glaucoma verification system integrates with `TaskCreationServices` through the `_is_verified_for_disease()` function:

```python
def _is_verified_for_disease(db, kind: str, image_id: int, disease_id: int) -> bool:
    # For Glaucoma: requires glaucoma_verified_status == 'verified' (no fallback)
    if name == 'glaucoma':
        return (enc.glaucoma_verified_status == 'verified')
```

### Critical Difference from DR

**DR**: Has fallback mechanism via `encounter_verified_status`
**Glaucoma**: No fallback mechanism - requires explicit glaucoma verification

### Task Creation Flow

1. **Verification Trigger**: User verifies a Glaucoma report
2. **Disease Lookup**: Find Glaucoma disease in database
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
- **Results toggle**: Switch between cleaned and unfiltered results

### Edit View Features

- **PDF viewer**: Display the Glaucoma report
- **VCDR values**: Display and edit vertical cup-to-disk ratios
- **Patient details**: Edit patient information
- **Verification toggle**: Switch verification status
- **Image preview**: Show associated fundus images
- **Navigation**: Previous/next report navigation

### Results Dashboard Features

- **Verification statistics**: Overall progress metrics
- **User performance**: Individual verification rates
- **Time-based charts**: Verification trends over time
- **Quality metrics**: Data quality indicators

### JavaScript Interactions

- **AJAX verification**: Toggle verification without page reload
- **Form validation**: Ensure required fields are completed
- **Loading states**: Show progress during operations
- **Chart rendering**: Display statistical charts

## API Endpoints

### Verification Endpoint

**URL**: `POST /verify_remedio_glaucoma/glaucoma_verify/<int:report_id>`

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
5. **VCDR Validation**: Invalid VCDR values

### Error Handling Pattern

```python
try:
    # Verification logic
    db.commit()
    flash("Report verified successfully.", "success")
except Exception as e:
    db.rollback()
    current_app.logger.exception("Failed to verify Glaucoma report %s: %s", report_id, e)
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
- **VCDR validation**: Ensure VCDR values are within valid ranges

### Privacy Considerations

- **Patient data**: Handle PHI according to privacy requirements
- **Access logging**: Log all verification actions
- **Data retention**: Follow data retention policies

## Performance Considerations

### Database Optimization

- **Indexing**: Verification status fields are indexed
- **Query optimization**: Efficient joins and filtering
- **Pagination**: Limit results per page
- **Cleaned results**: Optimized queries for processed data

### Caching Strategy

- **User permissions**: Cache user lab unit assignments
- **Disease lookups**: Cache disease information
- **Static assets**: Optimize PDF and image loading
- **Dashboard data**: Cache statistical computations

## Data Quality Features

### VCDR Processing

The system includes specialized handling for Vertical Cup-to-Disk Ratio (VCDR) values:

```python
# Raw VCDR values from PDF
vcdr_right: Mapped[str | None]
vcdr_left: Mapped[str | None]

# Processed numeric values
vcdr_right_num: Mapped[float | None]
vcdr_left_num: Mapped[float | None]
```

### Data Cleaning

- **String to numeric conversion**: Convert VCDR strings to floats
- **Range validation**: Ensure VCDR values are clinically valid
- **Quality flags**: Flag questionable values for review

## Monitoring and Logging

### Key Metrics to Monitor

- **Verification rates**: Track verification completion
- **Processing times**: Monitor verification performance
- **Error rates**: Track failed verification attempts
- **User activity**: Monitor verification patterns
- **VCDR distribution**: Monitor data quality metrics

### Logging Strategy

```python
current_app.logger.info("Glaucoma report %s verified by %s", report_id, current_user.username)
current_app.logger.exception("Failed to create Glaucoma tasks for report %s", report_id)
```

## Critical Gap: Missing No-Glaucoma Workflow

### Current Limitation

Unlike DR verification, Glaucoma verification lacks a fallback mechanism for encounters without Glaucoma PDFs:

- **DR has**: `verify_remedio_nodr` for encounters without DR PDFs
- **Glaucoma lacks**: No equivalent workflow for encounters without Glaucoma PDFs

### Impact

1. **Incomplete coverage**: Encounters without Glaucoma PDFs cannot be verified
2. **Task creation block**: No Glaucoma grading tasks created for these encounters
3. **Workflow asymmetry**: Inconsistent handling between DR and Glaucoma

### Recommended Solution

See [Verification Workflows Overview](verification-workflows-overview.md) for proposed solution to create a `verify_remedio_noglaucoma` workflow.

## Related Documentation

- [Verification Workflows Overview](verification-workflows-overview.md)
- [DR Verification Details](dr-verification-details.md)
- [No DR Report Verification Details](no-dr-verification-details.md)
- [Task Creation Services](../03-Tasks/taskCreationServices.md)
- [Database Schema](../00-Core/models.md)