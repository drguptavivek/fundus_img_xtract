# Scoping in Fundus Image Manager

This document describes the two primary scoping mechanisms used in the Fundus Image Manager application to control data access and workflow permissions.

## Overview

The application implements two distinct scoping mechanisms:

1. **User-LabUnit Scoping** - For general operations like uploading, reporting, editing images, verification, and dashboard access
2. **Slot-LabUnit Scoping** - For grading operations and task assignment

## 1. User-LabUnit Scoping

### Purpose
User-LabUnit scoping controls access to images and operations based on the lab units assigned to a user. This mechanism is used for most user-facing operations.

### Operations Using User-LabUnit Scoping
- **Image Upload**: Users can only upload images to their assigned lab units
- **Reporting**: Reports are filtered to show only data from user's assigned lab units
- **Image Editing**: Users can only edit images belonging to their assigned lab units
- **Verification**: Verification tasks are scoped to user's assigned lab units
- **Dashboard**: Dashboard displays data filtered by user's assigned lab units

### Implementation
Users are associated with lab units through the `user_lab_units` association table:

```python
user_lab_units = Table(
    'user_lab_units', Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete="CASCADE"), primary_key=True),
    Column('lab_unit_id', Integer, ForeignKey('lab_units.id', ondelete="CASCADE"), primary_key=True)
)
```

### Access Control Pattern
```python
# Example: Filtering images by user's lab units
user_lab_unit_ids = [lab_unit.id for lab_unit in current_user.lab_units]
images = session.query(Image).filter(Image.lab_unit_id.in_(user_lab_unit_ids)).all()
```

### Key Features
- Users can be assigned to multiple lab units
- Access is determined by the lab units explicitly assigned to the user
- Provides organizational boundaries for data access
- Used throughout the application for consistent data filtering

## 2. Slot-LabUnit Scoping

### Purpose
Slot-LabUnit scoping is specifically designed for the grading workflow. It determines which grading tasks a user can access based on their role permissions for specific diseases within lab units.

### Operations Using Slot-LabUnit Scoping
- **Task Assignment**: Grading tasks are assigned based on slot permissions
- **Grading Interface**: Users can only grade tasks for which they have slot permissions
- **Arbitration**: Arbitrators can only access tasks within their permitted slots
- **Quality Control**: Review processes are scoped by slot permissions

### Implementation
Slot permissions are managed through the `UserDiseaseUnitRole` model:

```python
class UserDiseaseUnitRole(Base):
    __tablename__ = 'user_disease_unit_role'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey('diseases.id', ondelete='CASCADE'), nullable=False, index=True)
    lab_unit_id: Mapped[int] = mapped_column(ForeignKey('lab_units.id', ondelete='CASCADE'), nullable=False, index=True)
    can_grade_resident: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_grade_resident2: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_arbitrate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
```

### Permission Types
- **can_grade_resident**: User can perform resident-level grading
- **can_grade_resident2**: User can perform resident2-level grading
- **can_arbitrate**: User can perform arbitration between conflicting grades

### Access Control Pattern
```python
# Example: Querying available grading tasks for a user
available_tasks = session.query(GradingTask).join(UserDiseaseUnitRole).filter(
    UserDiseaseUnitRole.user_id == current_user.id,
    UserDiseaseUnitRole.lab_unit_id == GradingTask.lab_unit_id,
    UserDiseaseUnitRole.disease_id == GradingTask.disease_id,
    UserDiseaseUnitRole.active == True,
    # Additional role-specific filters
).all()
```

### Key Features
- More granular control than User-LabUnit scoping
- Disease-specific permissions within lab units
- Role-based grading permissions (resident, resident2, arbitrator)
- Supports the dual grading workflow

## Comparison of Scoping Mechanisms

| Aspect | User-LabUnit Scoping | Slot-LabUnit Scoping |
|--------|---------------------|---------------------|
| **Purpose** | General data access | Grading workflow control |
| **Granularity** | Lab unit level | Disease + Lab unit + Role level |
| **Operations** | Upload, edit, verify, report, dashboard | Grading, arbitration, task assignment |
| **Model** | user_lab_units association table | UserDiseaseUnitRole model |
| **Flexibility** | Simple, broad access control | Complex, role-specific permissions |
| **Use Case** | Organizational data boundaries | Specialized grading workflow |

## Utility Functions and APIs for Scoping

### User-LabUnit Scoping Utilities

#### Upload Eligibility Functions
Located in [`utils/upload_eligibility.py`](utils/upload_eligibility.py):

- **[`get_user_uploadVerify_eligibility(user_id)`](utils/upload_eligibility.py:11)**: Returns upload eligibility details with hospital → lab unit mapping
- **[`get_user_lab_unit_ids(user_id)`](utils/upload_eligibility.py:94)**: Returns set of lab unit IDs user can access

#### General Access Control
Located in [`utils/utils.py`](utils/utils.py):

- **[`require_owner_or_roles(upload, *roles)`](utils/utils.py:19)**: Checks if user has required roles or is the upload owner

### Slot-LabUnit Scoping Utilities

#### Grading Eligibility Functions
Located in [`utils/dualGradingEligibility.py`](utils/dualGradingEligibility.py):

- **[`get_user_grading_eligibility_details(db, user_id)`](utils/dualGradingEligibility.py:16)**: Returns detailed grading eligibility grouped by hospital, lab unit, and disease
- **[`_get_user_eligible_lab_unit_ids(db, user_id, disease_id, role_slot)`](utils/dualGradingEligibility.py:82)**: Gets eligible lab unit IDs for specific role and disease
- **[`check_arbitration_eligibility(db, user_id, disease_id, lab_unit_id)`](utils/dualGradingEligibility.py:135)**: Checks if user can arbitrate for specific disease and lab unit
- **[`get_user_eligibility_for_task(db, user_id, task_id, role_slot)`](utils/dualGradingEligibility.py:157)**: Checks if user is eligible for specific task and role

#### API Endpoints for Grading Eligibility
Located in [`api/grading_eligibility.py`](api/grading_eligibility.py):

- **`/api/grading-eligibility/<user_id>`**: Returns all grading eligibility for a user
- **`/api/grading-eligibility/<user_id>/active`**: Returns active grading eligibility for a user

### Implementation Examples

#### Checking User-LabUnit Access
```python
from utils.upload_eligibility import get_user_lab_unit_ids

def can_user_access_image(user_id, image):
    """Check if user can access an image based on User-LabUnit scoping"""
    user_lab_unit_ids = get_user_lab_unit_ids(user_id)
    return image.lab_unit_id in user_lab_unit_ids
```

#### Checking Slot-LabUnit Permissions
```python
from utils.dualGradingEligibility import get_user_eligibility_for_task

def can_user_grade_task(db, user_id, task_id, role_slot):
    """Check if user can grade a task based on Slot-LabUnit scoping"""
    return get_user_eligibility_for_task(db, user_id, task_id, role_slot)
```

#### Getting Upload Eligibility
```python
from utils.upload_eligibility import get_user_uploadVerify_eligibility

def get_upload_options(user_id):
    """Get upload options for a user"""
    return get_user_uploadVerify_eligibility(user_id)
```

#### Getting Grading Eligibility
```python
from utils.dualGradingEligibility import get_user_grading_eligibility_details
from models import Session

def get_grading_options(user_id):
    """Get grading options for a user"""
    db = Session()
    try:
        return get_user_grading_eligibility_details(db, user_id)
    finally:
        db.close()
```

## Scoping in the Application Flow

### Image Upload Flow
1. User selects lab unit (filtered by User-LabUnit assignments)
2. Image is uploaded with lab_unit_id
3. User can only see/verify images from their assigned lab units

### Grading Workflow Flow
1. System creates grading tasks for images
2. Tasks are assigned based on Slot-LabUnit permissions
3. Users see only tasks they have permission to grade
4. Progression through grading roles follows slot permissions

## Management and Administration

### Managing User-LabUnit Assignments
- Admin users can assign users to lab units
- Assignments are managed through user management interface
- Changes immediately affect data access permissions

### Managing Slot-LabUnit Permissions
- Requires careful role-based permission management
- Disease-specific expertise must be considered
- Regular audits ensure appropriate permissions
- Changes affect grading task availability

## Best Practices

1. **Principle of Least Privilege**: Assign only necessary lab units and slot permissions
2. **Regular Audits**: Periodically review both types of scoping assignments
3. **Clear Documentation**: Maintain clear records of who has access to what
4. **Separation of Concerns**: Keep User-LabUnit and Slot-LabUnit scoping independent
5. **Testing**: Verify scoping works correctly for all user roles and operations

## Security Considerations

- User-LabUnit scoping prevents unauthorized data access across organizational boundaries
- Slot-LabUnit scoping ensures only qualified users perform grading tasks
- Both mechanisms work together to provide comprehensive access control
- Regular security audits should verify both scoping mechanisms are working correctly