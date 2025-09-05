# Dual Glaucoma Grading System Implementation Plan

## Tasks

1. [x] Design database schema for dual glaucoma grading system
2. [x] Create separate grading workflows for direct upload images and Remed.io ZIP file images
3. [ ] Implement resident grading interface for direct upload images
4. [ ] Implement consultant grading interface for direct upload images
5. [ ] Implement resident grading interface for Remed.io ZIP file images
6. [ ] Implement consultant grading interface for Remed.io ZIP file images
7. [ ] Develop matching algorithm to pair resident and consultant gradings for the same image
8. [ ] Create reporting system to analyze inter-rater reliability between residents and consultants
9. [ ] Implement audit trail to track all grading activities
10. [ ] Design user interface for viewing paired gradings and discrepancy analysis

## Task 1 Details: Design database schema for dual glaucoma grading system

The existing `ImageGrading` model in `models.py` already supports the requirements for a dual grading system with minimal modifications.

### Key Findings:
1. The `grader_role` field comes from the user's role in the system:
   - In existing code, roles are determined based on user permissions ('ophthalmologist', 'optometrist', 'admin')
   - For the dual grading system, we will use 'resident' for residents and 'consultant' for consultants

2. The existing schema already supports:
   - References to both Remed.io ZIP images (`encounter_file_id`) and direct uploads (`direct_image_upload_id`)
   - Timestamps for tracking when gradings were performed
   - Composite indexes for efficient querying

3. To identify paired gradings (resident and consultant grading the same image), we can query for gradings with the same image ID but different `grader_role` values ('resident' vs 'consultant').

No structural modifications to the `ImageGrading` table are required for the basic dual grading functionality.

## Task 2 Details: Create separate grading workflows for direct upload images and Remed.io ZIP file images

A detailed workflow design has been created and documented in `workflow_design_document.md`.

### Key Design Decisions:

1. Role Distinction:
   - Residents will be identified by a 'resident' role (users with 'optometrist' role)
   - Consultants will be identified by a 'consultant' role (users with 'ophthalmologist' role)
   - Admin users can be assigned either role based on context

2. Dual Grading Requirement:
   - Each image must be graded by both a resident and a consultant
   - The system will track which images have been graded by which role
   - Users will only be able to grade images that haven't been graded by their role yet

3. Workflow Modifications:
   - Direct Upload Images: Modify access control to allow both residents and consultants
   - Remed.io ZIP File Images: Update role determination logic to identify residents vs consultants

4. Key Features:
   - Role determination logic updated to assign 'resident' or 'consultant' roles
   - Grading status tracking to show which roles have graded an image
   - Enhanced "Save & Next" feature to prioritize images that haven't been graded by both roles

The existing ImageGrading table already supports the dual grading workflow without requiring schema modifications.