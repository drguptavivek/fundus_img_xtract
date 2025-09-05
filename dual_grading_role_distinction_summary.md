# Dual Graucoma Grading System - Role Distinction Summary

## Overview
This document summarizes the changes made to correctly distinguish between residents and optometrists in the dual grading workflow. The key insight is that residents are users with the 'optometrist' role, while consultants are users with the 'ophthalmologist' role. The system assigns 'resident' or 'consultant' as the grader_role during grading operations.

## Changes Made

### 1. Documentation Updates
- Updated TODO.md to correctly describe the role distinction
- Created workflow_design_document.md with detailed workflow design

### 2. Code Updates
- Modified grading/direct_disease.py to:
  - Allow 'optometrist' users to access the disease grading interface
  - Correctly assign 'resident' or 'consultant' to the grader_role field based on user's actual role
- Modified grading/remedio_dr.py to:
  - Correctly assign 'resident' or 'consultant' to the grader_role field based on user's actual role

### 3. Consistency Verification
- Verified that other grading files (remedio_glaucoma.py, glaucoma_direct.py) correctly implement the role distinction
- Verified that dual_grading/analysis.py correctly uses 'resident' and 'consultant' for grader_role values

### 4. Route Documentation
- The docs/route_list.md file contains the direct disease grading routes which now allow 'optometrist' users in addition to 'ophthalmologist' and 'admin' users

## Role Mapping
- Users with 'optometrist' role → Assigned 'resident' grader_role during grading
- Users with 'ophthalmologist' role → Assigned 'consultant' grader_role during grading
- Users with 'admin' role → Assigned 'admin' grader_role during grading (context-dependent)

## Future Considerations
- Consider updating the role assignment logic to be more consistent across all grading files
- Consider creating a utility function to handle role mapping to avoid duplication