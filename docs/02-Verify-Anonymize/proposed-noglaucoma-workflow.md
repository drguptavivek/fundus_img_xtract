# Proposed Solution: No Glaucoma Report Verification Workflow

This document outlines a proposed solution to address the critical gap in the verification system: the lack of a verification workflow for encounters without Glaucoma PDF reports.

## Problem Statement

Currently, the system has an asymmetric verification approach:

- **DR**: Has both PDF verification AND a fallback mechanism for encounters without PDFs
- **Glaucoma**: Only has PDF verification with NO fallback mechanism

This results in encounters without Glaucoma PDFs being unable to progress through the Glaucoma grading workflow.

## Proposed Solution

Create a new verification workflow `verify_remedio_noglaucoma` that mirrors the functionality of `verify_remedio_nodr` but for Glaucoma grading.

## Implementation Plan

### 1. Create Route Module

**File**: `verify_remedio_noglaucoma/routes.py`

**Structure**: Mirror the `verify_remedio_nodr/routes.py` structure with these key modifications:

```python
# Filter encounters WITHOUT glaucoma reports
def _base_encounter_query(db: Session, restricted_lab_units: set[int] | None):
    query = (
        db.query(PatientEncounters)
        .outerjoin(GlaucomaReport, GlaucomaReport.patient_encounter_id == PatientEncounters.id)
        .filter(GlaucomaReport.id.is_(None))  # Only encounters WITHOUT glaucoma reports
        .filter(PatientEncounters.zip_file_id.isnot(None))
    )
    if restricted_lab_units is not None:
        query = query.filter(PatientEncounters.lab_unit_id.in_(restricted_lab_units))
    return query

# Get glaucoma disease (instead of DR)
def _get_glaucoma_disease(db: Session) -> Disease | None:
    return (
        db.query(Disease)
        .filter(func.lower(Disease.name) == 'glaucoma')
        .first()
    )
```

### 2. Create Templates

**Directory**: `templates/verify_remedio_noglaucoma/`

**Files**:
- `list.html` - List encounters without glaucoma PDFs
- `edit.html` - Edit/view individual encounter with eye tagging

**Design**: Mirror the `verify_remedio_nodr` templates with Glaucoma-specific branding.

### 3. Update Navigation

**File**: `templates/base.html`

**Add to Glaucoma PDFs section** (around line 167):

```html
<li>
  <a class="dropdown-item {{ 'active' if (request.endpoint|default('', true)) == 'verify_remedio_noglaucoma.noglaucoma_list' else '' }}"
    href="{{ url_for('verify_remedio_noglaucoma.noglaucoma_list') }}">Verify (No Glaucoma Report)</a>
</li>
```

### 4. Update Task Creation Logic

**File**: `services/taskCreationServices.py`

**Modify `_is_verified_for_disease()` function**:

```python
def _is_verified_for_disease(db, kind: str, image_id: int, disease_id: int) -> bool:
    disease = db.get(Disease, disease_id)
    if not disease:
        return False
    name = (disease.name or '').strip().lower()
    
    if kind == 'direct':
        return db.execute(
            select(1).select_from(DirectImageVerify)
            .where(and_(DirectImageVerify.image_upload_id == image_id,
                        DirectImageVerify.verified_status == 'verified'))
        ).first() is not None
    
    # encounter
    ef = db.get(EncounterFile, image_id)
    if not ef:
        return False
    enc = db.get(PatientEncounters, ef.patient_encounter_id)
    if not enc:
        return False
    
    if name in ('diabetic retinopathy', 'dr'):
        return (enc.dr_verified_status == 'verified') or (enc.encounter_verified_status == 'verified')
    
    if name == 'glaucoma':
        # NEW: Add fallback mechanism for glaucoma
        return (enc.glaucoma_verified_status == 'verified') or (enc.encounter_verified_status == 'verified')
    
    # Future: 'amd' or others
    return False
```

### 5. Create Blueprint Registration

**File**: `verify_remedio_noglaucoma/__init__.py`

```python
from flask import Blueprint

bp = Blueprint('verify_remedio_noglaucoma', __name__)

from . import routes
```

### 6. Register Blueprint

**File**: `app.py` (or appropriate registration file)

```python
from verify_remedio_noglaucoma import bp as verify_remedio_noglaucoma_bp
app.register_blueprint(verify_remedio_noglaucoma_bp)
```

## Detailed Implementation

### Route Structure

| Route | Method | Purpose | Template |
|-------|--------|---------|----------|
| `/verify_remedio_noglaucoma/list` | GET | List encounters without Glaucoma PDFs | `verify_remedio_noglaucoma/list.html` |
| `/verify_remedio_noglaucoma/edit/<int:encounter_id>` | GET/POST | Edit/view individual encounter | `verify_remedio_noglaucoma/edit.html` |
| `/verify_remedio_noglaucoma/mark_eye/<int:encounter_id>` | POST | Mark image laterality | N/A (AJAX) |
| `/verify_remedio_noglaucoma/verify/<int:encounter_id>` | POST | Verify an encounter | N/A (AJAX/Redirect) |
| `/verify_remedio_noglaucoma/unverify/<int:encounter_id>` | POST | Unverify an encounter | N/A (AJAX/Redirect) |

### Key Implementation Details

#### 1. Query Logic

Filter encounters that have ZIP files but NO glaucoma reports:

```python
base_query = (
    db.query(PatientEncounters)
    .outerjoin(GlaucomaReport, GlaucomaReport.patient_encounter_id == PatientEncounters.id)
    .filter(GlaucomaReport.id.is_(None))  # Key: Exclude encounters WITH glaucoma reports
    .filter(PatientEncounters.zip_file_id.isnot(None))  # Only ZIP uploads
)
```

#### 2. Verification Logic

Same eye tagging requirement as no-DR workflow:

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
```

#### 3. Task Creation

Create Glaucoma tasks instead of DR tasks:

```python
# Create Glaucoma grading tasks
try:
    glaucoma_disease = _get_glaucoma_disease(db)
    if glaucoma_disease:
        images = db.query(EncounterFile).filter(
            EncounterFile.patient_encounter_id == encounter.id
        ).all()
        
        for image in images:
            ensure_task(image.uuid, glaucoma_disease.id)
            current_app.logger.info("Created Glaucoma grading task for image UUID %s via No-Glaucoma verification", image.uuid)
```

### UI Design Considerations

#### 1. Navigation Integration

Add the new option under "Glaucoma PDFs" section:

```
Verify
├── Glaucoma PDFs
│   ├── Verify (glaucoma PDFs)
│   ├── Verify (No Glaucoma Report) ← NEW
│   └── Dashboard
└── DR PDFs
    ├── Verify (DR PDFs)
    └── Verify (No DR Report)
```

#### 2. Visual Design

- Use same color scheme as other glaucoma verification pages
- Include clear indication that this is for encounters WITHOUT glaucoma PDFs
- Maintain consistency with no-DR workflow design patterns

#### 3. User Guidance

- Clear instructions about the purpose of this workflow
- Help text explaining why eye tagging is required
- Visual indicators for completion status

## Benefits of This Solution

### 1. Completes the Verification System

- Provides symmetric coverage for both DR and Glaucoma
- Ensures all encounters can be verified regardless of PDF availability
- Eliminates gaps in the workflow

### 2. Reuses Existing Infrastructure

- Leverages existing eye tagging system
- Uses same verification status model
- Follows established patterns and conventions

### 3. Minimal Code Changes

- Only requires modification to task creation logic
- Most functionality can be copied from no-DR workflow
- Low risk implementation

### 4. Improves Data Coverage

- Allows Glaucoma grading for all encounters
- Increases the dataset available for Glaucoma AI training
- Reduces missed grading opportunities

## Implementation Steps

### Phase 1: Core Implementation

1. Create `verify_remedio_noglaucoma` package
2. Implement basic routes (list, edit, verify, unverify)
3. Create templates mirroring no-DR design
4. Test basic functionality

### Phase 2: Integration

1. Register blueprint in main application
2. Update navigation menu
3. Modify task creation logic
4. Test end-to-end workflow

### Phase 3: Polish and Deploy

1. Add error handling and logging
2. Implement user feedback mechanisms
3. Add monitoring and metrics
4. Deploy to production

### Phase 4: Validation

1. Monitor usage patterns
2. Collect user feedback
3. Verify task creation works correctly
4. Make adjustments based on usage

## Risk Assessment

### Low Risk

- **Reuses proven patterns**: Based on existing no-DR workflow
- **Isolated functionality**: Doesn't affect existing workflows
- **Rollback capability**: Can be easily disabled if issues arise

### Medium Risk

- **Task creation logic change**: Requires careful testing
- **Database queries**: Need to ensure performance with large datasets
- **User training**: Users need to understand new workflow

### Mitigation Strategies

- **Thorough testing**: Test in development environment first
- **Gradual rollout**: Enable for specific lab units initially
- **Monitoring**: Track usage and errors closely
- **User documentation**: Provide clear instructions

## Success Metrics

### Quantitative Metrics

- **Number of encounters verified**: Track usage of new workflow
- **Task creation success rate**: Verify tasks are created correctly
- **Processing time**: Monitor performance impact
- **Error rates**: Track any issues that arise

### Qualitative Metrics

- **User feedback**: Collect feedback from optometrists
- **Workflow efficiency**: Assess if it improves overall process
- **Data quality**: Verify quality of graded images
- **Coverage improvement**: Measure increase in gradable encounters

## Future Enhancements

### Potential Improvements

1. **Bulk Operations**: Add bulk verification capabilities
2. **Advanced Filtering**: More sophisticated filtering options
3. **Quality Metrics**: Enhanced quality assurance features
4. **Automation**: Potential for automated eye detection
5. **Integration**: Better integration with other workflows

### Long-term Considerations

1. **Unified Verification**: Eventually merge DR and Glaucoma workflows
2. **AI Assistance**: Use AI to suggest eye laterality
3. **Mobile Support**: Optimize for tablet/mobile use
4. **Performance**: Optimize for large-scale deployments

## Conclusion

This proposed solution addresses a critical gap in the verification system while minimizing risk and leveraging existing infrastructure. By creating a no-glaucoma verification workflow that mirrors the successful no-DR workflow, we can ensure complete coverage of all encounters regardless of PDF availability.

The implementation is straightforward, low-risk, and provides immediate benefits to the system's completeness and data coverage. It represents a logical extension of existing patterns rather than a radical departure from established approaches.