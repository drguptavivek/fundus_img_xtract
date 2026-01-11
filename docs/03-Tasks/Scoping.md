# Scoping in Fundus Image Manager

This document describes the scoping mechanisms used in the Fundus Image Manager application to control data access and workflow permissions.

## Overview

The application implements a **3-tier scoping system**:

1. **Hospital-Level Scoping** - Top-level organizational isolation
2. **User-LabUnit Scoping** - For hospital-bound operations (uploads, verification, analytics)
3. **Slot-LabUnit Scoping** - For cross-hospital grading workflow (shared medical expertise)

## Key Security Distinction

### Cross-Hospital Operations
**Small grader pool requires shared expertise:**
- ✅ **Grading** (resident, resident2 slots) - via Slot-LabUnit
- ✅ **Arbitration** (arbitrator slot) - via Slot-LabUnit
- ✅ **Dataset Creation** (AI training) - multi-hospital datasets
- ✅ **Research** (future) - multi-hospital studies
- ✅ **Master Admin** - system-wide access

**Why safe:** Optometrists anonymize all data BEFORE grading tasks are created

### Hospital-Bound Operations
**Organizational boundaries require strict isolation:**
- ✅ Image uploads, verification, file management
- ✅ Reports, dashboards, analytics (non-admin)
- ✅ AI grade review, human grade review
- ✅ QA/QC, discrepancy review
- ✅ User management (site admin)
- ✅ Regular data exports
- ✅ Pre-graded Excel import

---

## 1. Hospital-Level Scoping

### Purpose
Top-level organizational isolation ensuring data from one hospital cannot be accessed by another hospital's users (except for cross-hospital grading).

### Implementation
Users belong to a specific hospital:
```python
user.hospital_id  # Foreign key to hospitals table
user.is_master_admin  # True for system-wide access
```

### Access Control Pattern
```python
# Hospital-bound operations MUST filter by hospital
if not user.is_master_admin:
    query = query.filter(Model.hospital_id == user.hospital_id)
```

### Exceptions
- **Master Admin** (`is_master_admin=True`) - Can access all hospitals
- **Grading/Arbitration** - Cross-hospital via Slot-LabUnit scoping
- **Dataset Creator** - Cross-hospital for AI training datasets

---

## 2. User-LabUnit Scoping (Hospital-Bound)

### Purpose
User-LabUnit scoping controls access to images and operations based on the lab units assigned to a user. This mechanism is used for **hospital-bound operations only**.

### Operations Using User-LabUnit Scoping
- **Image Upload**: Users can only upload images to their assigned lab units
- **Reporting**: Reports are filtered to show only data from user's assigned lab units
- **Image Editing**: Users can only edit images belonging to their assigned lab units
- **Verification**: Verification tasks are scoped to user's assigned lab units
- **Dashboard**: Dashboard displays data filtered by user's assigned lab units
- **Analytics**: Analytics scoped to assigned lab units

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
# Example: Filtering images by user's lab units (hospital-bound)
if not user.is_master_admin:
    # First filter by hospital
    images = images.filter(Image.hospital_id == user.hospital_id)
    
    # Then filter by assigned lab units
    user_lab_unit_ids = [lu.id for lu in user.lab_units 
                         if lu.hospital_id == user.hospital_id]
    images = images.filter(Image.lab_unit_id.in_(user_lab_unit_ids))
```

### Key Features
- Users can be assigned to multiple lab units
- Lab units must belong to user's assigned hospital
- Access is determined by the lab units explicitly assigned to the user
- Provides organizational boundaries within a hospital
- Used throughout the application for hospital-bound operations

---

## 3. Slot-LabUnit Scoping (Cross-Hospital Grading)

### Purpose
Slot-LabUnit scoping is specifically designed for the **cross-hospital grading workflow**. It determines which grading tasks a user can access based on their role permissions for specific diseases within lab units, **regardless of hospital**.

### Operations Using Slot-LabUnit Scoping
- **Task Assignment**: Grading tasks can be assigned across hospitals
- **Grading Interface**: Users grade tasks based on slot permissions (not hospital)
- **Arbitration**: Arbitrators can access tasks from any hospital
- **Quality Control**: Grading quality metrics (cross-hospital)

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
- **can_grade_resident**: User can perform resident-level grading (slot 1)
  - **Note:** Always equals `can_grade_resident2` (database constraint enforced)
- **can_grade_resident2**: User can perform resident2-level grading (slot 2)
  - **Note:** Always equals `can_grade_resident` (database constraint enforced)
- **can_arbitrate**: User can perform arbitration between conflicting grades (slot 3)

### 2-Week Cooling-Off Period
Due to the small grader pool, the same ophthalmologist can grade both resident slots (R1 and R2) for the same image, but **only after a 2-week cooling-off period** to ensure independence:

```python
# Ophthalmologist grades as R1
grade_r1_timestamp = datetime.now()

# Same ophthalmologist can grade as R2 only if:
if (datetime.now() - grade_r1_timestamp) >= timedelta(weeks=2):
    can_assign_r2 = True  # Memory decay provides independence
else:
    assign_to_different_grader = True  # Assign to another ophthalmologist
```

### Access Control Pattern
```python
# Example: Querying available grading tasks (NO hospital filter)
available_tasks = session.query(GradingTask).join(UserDiseaseUnitRole).filter(
    UserDiseaseUnitRole.user_id == current_user.id,
    UserDiseaseUnitRole.lab_unit_id == GradingTask.lab_unit_id,
    UserDiseaseUnitRole.disease_id == GradingTask.disease_id,  
    UserDiseaseUnitRole.active == True,
    # Additional role-specific filters
    # NOTE: NO hospital_id filter - intentionally cross-hospital!
).all()
```

### Key Features
- **Cross-hospital grading** - Can grade tasks from any hospital (via permissions)
- More granular control than User-LabUnit scoping
- Disease-specific permissions within lab units
- Role-based grading permissions (resident, resident2, arbitrator)
- Supports the dual grading workflow
- Lab units can be from different hospitals
- **Anonymization enforced** - Graders see ZERO PII

---

## Anonymization Workflow (CRITICAL Security Feature)

### Optometrist as Anonymization Gatekeeper

**Why cross-hospital grading can work safely:**

```
Step 1: Image Upload
├─ data_manager uploads image with PII
└─ State: UPLOADED (contains patient data)

Step 2: Optometrist Verification ⭐ CRITICAL STEP
├─ Reviews image quality
├─ Strips ALL PII:
│  ├─ Removes patient_name
│  ├─ Hashes patient_id → UUID
│  ├─ Removes phone, MRN, address
│  └─ Removes any hospital-identifying info
└─ State: VERIFIED & ANONYMIZED

Step 3: Grading Task Creation
├─ Task created with ONLY:
│  ├─ UUID (no patient data)
│  ├─ Disease type
│  └─ Image URL (UUID-based)
└─ State: PENDING_GRADING

Step 4: Cross-Hospital Grading
├─ Any ophthalmologist can grade (via UserDiseaseUnitRole)
├─ Sees ZERO PII
├─ Cannot determine source hospital
└─ Grading is truly anonymized
```

**Result:** Cross-hospital grading works safely because optometrists have already removed all PII before tasks enter the grading workflow.

---

## Comparison of Scoping Mechanisms

| Aspect | Hospital-Level | User-LabUnit | Slot-LabUnit |
|--------|---------------|--------------|--------------|
| **Purpose** | Org isolation | General data access | Cross-hospital grading |
| **Granularity** | Hospital | Lab unit | Disease + Lab + Role |
| **Cross-hospital?** | No (except admin) | No | Yes (grading only) |
| **Operations** | All | Upload, verify, report | Grading, arbitration |
| **Model** | users.hospital_id | user_lab_units | UserDiseaseUnitRole |
| **Bypass** | is_master_admin | is_master_admin | N/A (no bypass) |

---

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