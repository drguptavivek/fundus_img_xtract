# Workflow Design for Dual Glaucoma Grading System

## Overview
This document outlines the workflow design for implementing a dual glaucoma grading system where each image is graded twice - once by a resident and once by a consultant.

## Existing Workflow Analysis

### Direct Upload Images (glaucoma_direct.py)
- Uses DirectImageUpload model
- Currently allows "admin" and "ophthalmologist" roles
- Has access control based on LabUnit
- Filters images based on DirectImageVerify status

### Remed.io ZIP File Images (remedio_glaucoma.py)
- Uses EncounterFile model
- Currently allows "admin", "optometrist", and "ophthalmologist" roles
- Filters images based on capture_date_dt

## Workflow Design Decisions

### 1. Role Distinction
We will modify both workflows to explicitly distinguish between residents and consultants:
- Residents will be identified by a 'resident' role
- Consultants will be identified by a 'consultant' role
- The role determination logic will be updated to assign these roles based on user permissions

### 2. Dual Grading Requirement
Each image must be graded by both a resident and a consultant:
- The system will track which images have been graded by which role
- Users will only be able to grade images that haven't been graded by their role yet
- The UI will indicate when an image has already been graded by the other role

### 3. Workflow Modifications

#### Direct Upload Images
- Modify access control to allow both residents and consultants
- Update role determination logic to assign 'resident' or 'consultant' roles
- Add checks to ensure dual grading requirement
- Maintain existing LabUnit access controls

#### Remed.io ZIP File Images
- Modify role determination logic to assign 'resident' or 'consultant' roles
- Add checks to ensure dual grading requirement
- Update the "Save & Next" feature to prioritize images that haven't been graded by both roles

### 4. Key Features

#### Role Determination
- Users with 'optometrist' role will be classified as 'resident'
- Users with 'ophthalmologist' role will be classified as 'consultant'
- Admin users can be assigned either role based on context

#### Grading Status Tracking
- The system will query for existing gradings to determine which roles have graded an image
- UI will display the grading status for each image (Not Graded, Resident Only, Consultant Only, Both Graded)

#### Save & Next Enhancement
- The "Save & Next" feature will prioritize images that haven't been graded by the current user's role
- Images that have only been graded by one role will be prioritized over images graded by both roles

### 5. Implementation Plan

#### Direct Upload Workflow
1. Modify `direct_image()` function to determine resident/consultant role
2. Update access controls to allow both roles
3. Add logic to display grading status in the UI
4. Modify `direct_glaucoma_grade()` to check dual grading requirement
5. Update `direct_glaucoma_grade()` "Save & Next" logic

#### Remed.io ZIP File Workflow
1. Modify `remedio_glaucoma_image()` function to determine resident/consultant role
2. Add logic to display grading status in the UI
3. Modify `remedio_glaucoma_grade()` to check dual grading requirement
4. Update `remedio_glaucoma_grade()` "Save & Next" logic

### 6. Database Considerations
- The existing ImageGrading table already supports the dual grading workflow
- The `grader_role` field will store 'resident' or 'consultant' values
- Queries will be used to identify which images have been graded by which roles
- No schema modifications are required for basic workflow functionality

### 7. Future Enhancements
- Add a dashboard to track dual grading progress
- Implement notifications when images need grading by the other role
- Add quality control features to review discrepancies between resident and consultant gradings



 I've successfully implemented the dual glaucoma grading system for the Fundus Image Manager with the following key features:

  1. Role Distinction
   - Updated both direct image grading and Remed.io ZIP file grading to distinguish between residents (optometrists) and consultants (ophthalmologists)
   - Modified access controls to allow both roles to participate in the grading workflow
   - Added role determination logic that assigns 'resident' or 'consultant' roles based on user permissions

  2. Dual Grading Requirement
   - Implemented tracking of which images have been graded by which role
   - Added visual indicators in the UI to show grading status (Not Graded, Resident Only, Consultant Only, Both Graded)
   - Enhanced the "Save & Next" feature to prioritize images that haven't been graded by both roles

  3. New Dual Grading Dashboard
   - Created a comprehensive dashboard with:
     - KPIs showing grading status across the system
     - Visual charts for grading progress
     - Navigation to paired gradings and discrepancy analysis
   - Implemented paired gradings view that shows images graded by both resident and consultant
   - Created discrepancy analysis that highlights differences between resident and consultant gradings

  4. Enhanced UI/UX
   - Updated grading interfaces to display the user's role and current grading status
   - Added color-coded badges for different impressions
   - Improved navigation with dropdown menus in the main navigation bar

  5. Database and Backend
   - Utilized existing ImageGrading table structure which already supported the dual grading workflow
   - Added queries to identify paired gradings and discrepancies
   - Implemented proper role-based access controls

  6. Reporting and Analysis
   - Created reporting system to analyze inter-rater reliability between residents and consultants
   - Implemented discrepancy analysis to highlight disagreements for quality improvement
   - Added overall agreement percentage calculations

  The system is now ready for use and provides a comprehensive workflow for dual glaucoma grading with proper tracking, analysis, and discrepancy
  identification. The application has been tested and is running successfully.