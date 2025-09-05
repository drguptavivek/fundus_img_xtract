# Dual Glaucoma Grading System Workflow Design

## Overview

This document details the workflow design for the dual glaucoma grading system, which requires each image to be independently graded by both a resident and a consultant (ophthalmologist).

## Role Definitions

### Resident
- Users with the 'resident' system role
- Assigned 'resident' grader_role during grading
- Primary graders who perform initial image assessment
- Can only grade images that haven't been graded by a resident

### Consultant (Ophthalmologist)
- Users with the 'ophthalmologist' system role
- Assigned 'consultant' grader_role during grading
- Senior graders who provide secondary assessment
- Can only grade images that haven't been graded by a consultant

### Administrator
- Users with the 'admin' system role
- Can be assigned either 'resident' or 'consultant' grader_role based on context
- Have full access to all grading functions

## Workflow Requirements

### 1. Dual Grading Requirement
Each image must be graded independently by both a resident and a consultant. The system must:
- Track which images have been graded by which role
- Prevent duplicate gradings by the same role from the same user
- Allow the same user to grade the same image with different roles (in special cases)

### 2. Image Access Control
- Residents can access all images for grading
- Consultants can only access images from their own LabUnit (except admins)
- Admins have unrestricted access to all images

### 3. Grading Status Tracking
The system tracks the following grading statuses for each image:
- Not Graded: No gradings by either role
- Resident Only: Graded by resident but not consultant
- Consultant Only: Graded by consultant but not resident
- Both Graded: Graded by both resident and consultant

### 4. Save & Next Feature Enhancement
The "Save & Next" feature prioritizes images for grading based on:
1. Images graded by the other role but not by the current user's role
2. Images not yet graded by any role
3. Random selection among eligible images

## Implementation Details

### Role Determination Logic
```python
# Determine user's role for grading
if current_user.has_role('ophthalmologist'):
    user_role = 'consultant'
elif current_user.has_role('resident'):
    user_role = 'resident'
elif current_user.has_role('admin'):
    user_role = 'admin'  # Assigned contextually
```

### Grading Status Calculation
```python
# Fetch existing gradings for an image
existing_gradings = db.query(ImageGrading).filter(
    ImageGrading.encounter_file_id == image_id,
    ImageGrading.graded_for == 'glaucoma'
).all()

# Determine status
resident_grading = any(g.grader_role == 'resident' for g in existing_gradings)
consultant_grading = any(g.grader_role == 'consultant' for g in existing_gradings)

if resident_grading and consultant_grading:
    grading_status = "Both Graded"
elif resident_grading:
    grading_status = "Resident Only"
elif consultant_grading:
    grading_status = "Consultant Only"
else:
    grading_status = "Not Graded"
```

### Save & Next Algorithm
For residents and consultants:
1. Find images that have been graded by the other role but not by the current user's role
2. If no such images exist, find any ungraded images
3. Select a random image from the eligible pool

### Data Integrity
The system ensures data integrity by:
- Using upsert operations to prevent duplicate gradings by the same user/role combination
- Implementing proper foreign key constraints
- Validating user roles before allowing grading operations
- Providing audit trails for all grading activities

## Reporting and Analysis

### Inter-rater Reliability
The system provides reports to analyze agreement between residents and consultants:
- Overall agreement statistics
- Discrepancy analysis
- Kappa statistics for inter-rater reliability

### Audit Trail
All grading activities are logged with:
- Timestamp
- User ID and role
- Image ID
- Grading details (impression, remarks)
- Any modifications or deletions

## Future Enhancements

### Intra-rater Agreement
To support intra-rater agreement analysis, the system could be modified to:
- Allow multiple gradings by the same user/role combination
- Add a time-based component to distinguish repeated gradings
- Implement a more sophisticated grading history tracking system

### Automated Discrepancy Resolution
Future versions could include:
- Automated flagging of significant discrepancies
- Workflow for arbitration of discrepant gradings
- Integration with AI-based grading as a third opinion


  I've successfully implemented "resident" as a unique system role separate from "optometrist" in the dual grading workflow. Here are the key changes
  I made:

   1. Added "resident" to System Roles:
      - Updated auth/roles.py to include "resident" in the DEFAULT_ROLES list

   2. Updated Role Assignment Logic:
      - Modified all grading files (remedio_glaucoma.py, glaucoma_direct.py, remedio_dr.py, direct_disease.py) to check for the "resident" system role
        directly instead of mapping "optometrist" users to "resident" grader_role

   3. Updated Route Decorators:
      - Modified all grading files to require the "resident" role instead of "optometrist" role for accessing grading routes

   4. Updated Documentation:
      - Updated TODO.md and workflow_design_document.md to reflect that "resident" is now a separate system role

  The system now correctly treats "resident" as a distinct system role rather than just a value used in the grader_role field for "optometrist" users.
  Users who should have resident privileges need to be assigned the "resident" system role, and those who previously had the "optometrist" role for
  grading purposes may need to have the "resident" role assigned to them.

  I've also created a summary document (dual_grading_resident_role_implementation_summary.md) that details all the changes made and provides migration
  notes for transitioning existing users.