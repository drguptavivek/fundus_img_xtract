# Review Grade Feature Documentation

## Overview
This document describes the implementation of the Review Grade feature for the Fundus Image Manager application.

## Features Added

### 1. Discrepancy Review Page Enhancements (/review/discrepancy-review)

#### AI Grade Filter
- Added a "Has AI Grade" dropdown filter with options:
  - All Tasks (default)
  - Has AI Grade (filters for tasks with AI grades where slot=ai)
  - No AI Grade (filters for tasks without AI grades)

#### AI Model Filter
- Added a multi-select dropdown filter for AI Models
- Users can select one or more AI models to filter tasks by
- Shows model names with versions (e.g., "WadwaniAI vsep_2026")

#### UI/UX Improvements
- Made grade filters (Resident, Resident2, Arbitrator, Final) only visible when a disease is selected
- Improved checkbox visibility with better contrast and borders
- Added dark mode support for checkbox styling
- Fixed various alignment and display issues

### 2. Task Details Page - Review Grade Functionality (/review/reviewTaskDetails/)

#### Review Grade Feature
- Added a "Review Grade" section to the task details page
- Only users with Resident2 or Arbitrator permissions for the task's disease-lab_unit combination can add review grades
- Users can select a grade from the available options for the disease
- Users can add optional comments with their review
- Existing review grades can be updated

## Implementation Details

### Backend Changes

1. **New API Endpoint** (`/api/ai-models`) in `api/ai_models.py`
   - Fetches available AI models from the database
   - Returns JSON with model ID, name, and version

2. **Updated `review/route_discrepancy_review.py`**:
   - Added AI models query to fetch available models
   - Added filter logic for `has_ai_grade` parameter
   - Added filter logic for `ai_model_id` parameter
   - Enhanced grade processing to include AI model information

3. **Updated `review/task_review.py`**:
   - Added POST method handling for review grade submission
   - Added permission checking using existing utility functions
   - Added logic to create or update review grades

### Database Changes

1. **Updated `models.py`**:
   - Modified the Grade model's check constraint to include 'review' as a valid role_slot
   - Changed from: `CheckConstraint("role_slot IN ('resident','resident2','arbitrator','ai')", name='ck_grade_role_slot_valid')`
   - To: `CheckConstraint("role_slot IN ('resident','resident2','arbitrator','ai','review')", name='ck_grade_role_slot_valid')`

2. **Database Migration**:
   - Created migration script: `scripts/migrations/20250116_add_review_role_slot.sql`
   - Created shell script to run migration: `scripts/migrations/run_migration_20250116.sh`
   - The migration recreates the grades table with the updated constraint

### Frontend Changes

1. **Updated `templates/review/discrepancy_review.html`**:
   - Added new filter UI elements
   - Added AI Grade column to the results table
   - Enhanced JavaScript for filter interactions
   - Added CSS styling for better visibility

2. **Updated `templates/review/task_detail_review.html`**:
   - Added review grade form with radio buttons
   - Added comment field for review notes
   - Added JavaScript for visual feedback

## Security Considerations

1. **Permission Checking**:
   - Review grades can only be added by users with Resident2 or Arbitrator permissions
   - Permission checking is done using existing `dualGradingEligibility.py` functions

2. **CSRF Protection**:
   - All forms include CSRF tokens using the existing `_forms.html` partial

3. **Input Validation**:
   - Grade selections are validated against available disease gradings
   - Comments are properly sanitized

## Usage Instructions

### For Discrepancy Review Page:
1. Navigate to `/review/discrepancy-review`
2. Use the "Has AI Grade" filter to show tasks with or without AI grades
3. Use the "AI Models" filter to select specific AI models
4. Select a disease to show grade filters
5. Apply additional filters as needed

### For Task Details Page:
1. Navigate to a task details page via `/review/reviewTaskDetails/<task_id>`
2. If you have Resident2 or Arbitrator permissions, you'll see the "Review Grade" section
3. Select a grade from the available options
4. Add optional comments
5. Click "Save Review Grade" to submit

## Testing

A test script was created to verify:
1. The 'review' role_slot is properly accepted in the database
2. AI models can be queried successfully

The tests passed successfully after the database migration.

## Migration Notes

- The database migration recreates the grades table to update the check constraint
- All existing data is preserved during the migration
- The migration has been tested and verified to work correctly