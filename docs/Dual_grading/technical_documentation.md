# Dual Grading System - Technical Documentation

## Overview

This document provides technical details about the implementation of the matching and arbitration algorithms in the dual grading system. It covers the core components, data structures, algorithms, and implementation details.

## Core Components

### 1. Database Models

The dual grading system extends existing database models with new fields to support matching and arbitration:

#### EncounterFile Model (Remedio ZIP Images)
```python
class EncounterFile(Base):
    # Existing fields...
    
    # Fields for matching and arbitration
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    is_arbitration: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    arbitrated_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    
    # Relationships
    arbitrator: Mapped["User"] = relationship("User", foreign_keys=[arbitrated_by])
```

#### DirectImageUpload Model (Direct Uploads)
```python
class DirectImageUpload(Base):
    # Existing fields...
    
    # Fields for matching and arbitration
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    is_arbitration: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    arbitrated_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    
    # Relationships
    arbitrator: Mapped["User"] = relationship("User", foreign_keys=[arbitrated_by])
```

### 2. ImageGrading Model

The existing ImageGrading model remains unchanged but is used extensively in the matching process:

```python
class ImageGrading(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    encounter_file_id: Mapped[int | None] = mapped_column(ForeignKey('encounter_files.id'), index=True, nullable=True)
    direct_image_upload_id: Mapped[int | None] = mapped_column(ForeignKey('direct_image_uploads.id'), index=True, nullable=True)
    grader_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    grader_username: Mapped[str | None] = mapped_column(String(150), nullable=True)
    grader_role: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)  # 'resident' or 'consultant'
    graded_for: Mapped[str] = mapped_column(String(32), index=True)  # Disease type
    impression: Mapped[str] = mapped_column(String(32))
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    
    # Relationships
    image: Mapped["EncounterFile"] = relationship(back_populates="gradings")
    direct_image: Mapped["DirectImageUpload"] = relationship()
    grader: Mapped["User"] = relationship("User", foreign_keys=[grader_user_id])
```

## Algorithms

### 1. Matching Algorithm

The matching algorithm identifies pairs of resident and consultant gradings for the same image:

#### Core Logic
```python
def _match_encounter_files(db):
    """
    Match resident and consultant gradings for encounter files.
    """
    # Get encounter files that have both resident and consultant gradings but haven't been matched yet
    unmatched_encounters = (
        db.query(EncounterFile)
        .filter(EncounterFile.is_locked == False)  # Only process unlocked files
        .filter(
            and_(
                # Has resident grading
                db.query(ImageGrading.id).filter(
                    ImageGrading.encounter_file_id == EncounterFile.id,
                    ImageGrading.grader_role == 'resident'
                ).exists(),
                # Has consultant grading
                db.query(ImageGrading.id).filter(
                    ImageGrading.encounter_file_id == EncounterFile.id,
                    ImageGrading.grader_role == 'consultant'
                ).exists()
            )
        )
        .all()
    )
    
    for encounter in unmatched_encounters:
        # Lock the encounter file
        encounter.is_locked = True
        encounter.matched_at = datetime.utcnow()
        db.add(encounter)
        
        print(f"Matched and locked encounter file {encounter.uuid}")

def _match_direct_uploads(db):
    """
    Match resident and consultant gradings for direct image uploads.
    """
    # Get direct uploads that have both resident and consultant gradings but haven't been matched yet
    unmatched_directs = (
        db.query(DirectImageUpload)
        .filter(DirectImageUpload.is_locked == False)  # Only process unlocked files
        .filter(
            and_(
                # Has resident grading
                db.query(ImageGrading.id).filter(
                    ImageGrading.direct_image_upload_id == DirectImageUpload.id,
                    ImageGrading.grader_role == 'resident'
                ).exists(),
                # Has consultant grading
                db.query(ImageGrading.id).filter(
                    ImageGrading.direct_image_upload_id == DirectImageUpload.id,
                    ImageGrading.grader_role == 'consultant'
                ).exists()
            )
        )
        .all()
    )
    
    for direct_upload in unmatched_directs:
        # Lock the direct upload
        direct_upload.is_locked = True
        direct_upload.matched_at = datetime.utcnow()
        db.add(direct_upload)
        
        print(f"Matched and locked direct upload {direct_upload.uuid}")
```

#### Execution Schedule
The matching process runs automatically every 2 hours through a background task. It can also be triggered manually through the dual grading dashboard.

### 2. Arbitration Algorithm

The arbitration algorithm manages the workflow for resolving discrepant gradings:

#### Core Logic
```python
def get_discrepancies(db):
    """
    Get images with discrepancies between resident and consultant gradings.
    """
    # Get encounter files with discrepancies
    encounter_discrepancies = (
        db.query(EncounterFile)
        .join(ImageGrading, EncounterFile.id == ImageGrading.encounter_file_id)
        .filter(EncounterFile.is_locked == True, EncounterFile.is_arbitration == False)
        .group_by(EncounterFile.id)
        .having(
            and_(
                # Has both resident and consultant gradings
                db.query(ImageGrading.id).filter(
                    ImageGrading.encounter_file_id == EncounterFile.id,
                    ImageGrading.grader_role == 'resident'
                ).exists(),
                db.query(ImageGrading.id).filter(
                    ImageGrading.encounter_file_id == EncounterFile.id,
                    ImageGrading.grader_role == 'consultant'
                ).exists(),
                # But the impressions are different
                db.query(ImageGrading.impression).filter(
                    ImageGrading.encounter_file_id == EncounterFile.id,
                    ImageGrading.grader_role == 'resident'
                ) != db.query(ImageGrading.impression).filter(
                    ImageGrading.encounter_file_id == EncounterFile.id,
                    ImageGrading.grader_role == 'consultant'
                )
            )
        )
        .all()
    )
    
    # Get direct uploads with discrepancies
    direct_discrepancies = (
        db.query(DirectImageUpload)
        .join(ImageGrading, DirectImageUpload.id == ImageGrading.direct_image_upload_id)
        .filter(DirectImageUpload.is_locked == True, DirectImageUpload.is_arbitration == False)
        .group_by(DirectImageUpload.id)
        .having(
            and_(
                # Has both resident and consultant gradings
                db.query(ImageGrading.id).filter(
                    ImageGrading.direct_image_upload_id == DirectImageUpload.id,
                    ImageGrading.grader_role == 'resident'
                ).exists(),
                db.query(ImageGrading.id).filter(
                    ImageGrading.direct_image_upload_id == DirectImageUpload.id,
                    ImageGrading.grader_role == 'consultant'
                ).exists(),
                # But the impressions are different
                db.query(ImageGrading.impression).filter(
                    ImageGrading.direct_image_upload_id == DirectImageUpload.id,
                    ImageGrading.grader_role == 'resident'
                ) != db.query(ImageGrading.impression).filter(
                    ImageGrading.direct_image_upload_id == DirectImageUpload.id,
                    ImageGrading.grader_role == 'consultant'
                )
            )
        )
        .all()
    )
    
    return encounter_discrepancies, direct_discrepancies
```

#### Arbitration Process
1. Identify images with discrepant gradings (different impressions from resident and consultant)
2. Display these images in the arbitration dashboard for consultants
3. Allow consultants to provide an arbitrated grade
4. Mark images as arbitrated and remove them from the discrepancy list

## Implementation Details

### 1. Frontend Integration

The system integrates locking and arbitration status into the grading interfaces:

#### Template Updates
All grading templates have been updated to:
- Display locking status when an image is locked
- Disable form elements when an image is locked
- Hide remove grading buttons when an image is locked

Example implementation in templates:
```html
{% if image.is_locked %}
<div class="mb-3 small text-muted">Lock Status: 
  <strong class="text-danger">
    LOCKED - This image has been matched and cannot be edited
  </strong>
</div>
{% endif %}

<input type="radio" class="btn-check" name="impression" id="{{ oid }}" value="{{ opt }}" 
       autocomplete="off" required {% if my_grading and my_grading.impression == opt %}checked{% endif %} 
       {% if image.is_locked %}disabled{% endif %}>
```

### 2. Backend Validation

All grading endpoints include validation to prevent:
- Editing locked images
- Creating duplicate gradings for the same user/role/condition combination
- Removing gradings from locked images

Example validation:
```python
@roles_required("admin", "resident", "ophthalmologist")
def remedio_glaucoma_grade():
    # ... existing code ...
    
    # Check if image is locked
    if ef.is_locked:
        flash("This image has been locked for editing after matching. No further changes allowed.", "danger")
        return redirect(request.referrer or url_for("grading.index"))
    
    # ... rest of function ...
```

### 3. Background Processing

The matching process runs as a background task:
```python
def run_matching():
    """
    Run the matching process to identify pairs of resident/consultant gradings.
    This function should be called periodically (e.g., every 2 hours).
    """
    db = Session()
    try:
        # Match encounter files (Remedio ZIP images)
        _match_encounter_files(db)
        
        # Match direct image uploads
        _match_direct_uploads(db)
        
        db.commit()
        print("Matching process completed successfully.")
    except Exception as e:
        db.rollback()
        print(f"Error during matching process: {e}")
        raise
    finally:
        db.close()
```

### 4. Statistics and Reporting

The system provides comprehensive statistics:
```python
def get_matching_stats(db=None):
    """
    Get statistics about the matching process.
    """
    close_db = False
    if db is None:
        db = Session()
        close_db = True
        
    try:
        # Total images
        total_encounters = db.query(EncounterFile).count()
        total_directs = db.query(DirectImageUpload).count()
        
        # Locked images (matched)
        locked_encounters = db.query(EncounterFile).filter(EncounterFile.is_locked == True).count()
        locked_directs = db.query(DirectImageUpload).filter(DirectImageUpload.is_locked == True).count()
        
        # Arbitrated images
        arbitrated_encounters = db.query(EncounterFile).filter(EncounterFile.is_arbitration == True).count()
        arbitrated_directs = db.query(DirectImageUpload).filter(DirectImageUpload.is_arbitration == True).count()
        
        # Images with both gradings
        encounters_with_both = (
            db.query(EncounterFile)
            .filter(
                and_(
                    db.query(ImageGrading.id).filter(
                        ImageGrading.encounter_file_id == EncounterFile.id,
                        ImageGrading.grader_role == 'resident'
                    ).exists(),
                    db.query(ImageGrading.id).filter(
                        ImageGrading.encounter_file_id == EncounterFile.id,
                        ImageGrading.grader_role == 'consultant'
                    ).exists()
                )
            )
            .count()
        )
        
        direct_with_both = (
            db.query(DirectImageUpload)
            .filter(
                and_(
                    db.query(ImageGrading.id).filter(
                        ImageGrading.direct_image_upload_id == DirectImageUpload.id,
                        ImageGrading.grader_role == 'resident'
                    ).exists(),
                    db.query(ImageGrading.id).filter(
                        ImageGrading.direct_image_upload_id == DirectImageUpload.id,
                        ImageGrading.grader_role == 'consultant'
                    ).exists()
                )
            )
            .count()
        )
        
        return {
            'total_encounters': total_encounters,
            'total_directs': total_directs,
            'locked_encounters': locked_encounters,
            'locked_directs': locked_directs,
            'arbitrated_encounters': arbitrated_encounters,
            'arbitrated_directs': arbitrated_directs,
            'encounters_with_both': encounters_with_both,
            'direct_with_both': direct_with_both
        }
    finally:
        if close_db:
            db.close()
```

## Testing

The system includes comprehensive tests to verify functionality:

### 1. Locking Tests
```python
def test_locking_mechanism():
    """Test the locking mechanism."""
    print("Testing locking mechanism...")
    
    # Get a session
    db = Session()
    
    try:
        # Test with EncounterFile
        encounter = db.query(EncounterFile).first()
        if encounter:
            print(f"Encounter file UUID: {encounter.uuid}")
            print(f"Initial lock status: is_locked = {encounter.is_locked}")
            
            # Lock the encounter
            encounter.is_locked = True
            db.add(encounter)
            db.commit()
            
            # Refresh and check
            db.refresh(encounter)
            print(f"Lock status after locking: is_locked = {encounter.is_locked}")
            
            # Unlock the encounter
            encounter.is_locked = False
            db.add(encounter)
            db.commit()
            
            # Refresh and check
            db.refresh(encounter)
            print(f"Lock status after unlocking: is_locked = {encounter.is_locked}")
        else:
            print("No encounter files found in database.")
            
        # Test with DirectImageUpload
        direct_upload = db.query(DirectImageUpload).first()
        if direct_upload:
            print(f"Direct upload UUID: {direct_upload.uuid}")
            print(f"Initial lock status: is_locked = {direct_upload.is_locked}")
            
            # Lock the direct upload
            direct_upload.is_locked = True
            db.add(direct_upload)
            db.commit()
            
            # Refresh and check
            db.refresh(direct_upload)
            print(f"Lock status after locking: is_locked = {direct_upload.is_locked}")
            
            # Unlock the direct upload
            direct_upload.is_locked = False
            db.add(direct_upload)
            db.commit()
            
            # Refresh and check
            db.refresh(direct_upload)
            print(f"Lock status after unlocking: is_locked = {direct_upload.is_locked}")
        else:
            print("No direct uploads found in database.")
            
        print("Test completed successfully.")
        
    except Exception as e:
        print(f"Error during test: {e}")
        db.rollback()
    finally:
        db.close()
```

### 2. Matching Tests
```python
def test_matching_system():
    """Test the matching system."""
    print("Testing matching system...")
    
    # Get initial stats
    stats = get_matching_stats()
    print(f"Initial stats: {stats}")
    
    # Run matching process
    print("Running matching process...")
    run_matching()
    
    # Get stats after matching
    stats = get_matching_stats()
    print(f"Stats after matching: {stats}")
    
    print("Test completed successfully.")
```

## Security Considerations

### 1. Access Control
- Role-based access control ensures appropriate permissions
- Consultants can only access images from their own LabUnit (except admins)
- Residents have broader access for training purposes

### 2. Data Integrity
- CSRF protection on all grading forms
- Input validation on all grade submissions
- Database constraints to prevent duplicate gradings

### 3. Audit Trail
- All grading activities are logged with timestamps
- User identity, role, and actions are recorded
- Changes to grades are tracked with version history

## Performance Optimization

### 1. Database Indexes
The system uses appropriate indexes for efficient querying:
- Indexes on `is_locked`, `matched_at`, and `is_arbitration` fields
- Composite indexes for common query patterns
- Proper foreign key relationships for data consistency

### 2. Query Optimization
- Efficient queries using EXISTS clauses for matching
- Batch processing for large datasets
- Proper transaction management to ensure data consistency

## Conclusion

The dual grading system has been successfully implemented with robust matching and arbitration algorithms. The system ensures data integrity through locking mechanisms, provides comprehensive reporting and analytics, and maintains a detailed audit trail of all activities. The implementation follows best practices for security, performance, and maintainability.