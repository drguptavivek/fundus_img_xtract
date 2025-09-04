# Direct Image Grading Documentation

This document provides an overview of the direct image grading functionality that allows clinicians to grade images uploaded directly to the system (bypassing the ZIP archive workflow).

## Overview

Direct image grading enables clinicians to grade fundus images that have been uploaded directly through the direct upload interface. This functionality is separate from the traditional grading of images extracted from ZIP archives and uses the `DirectImageUpload` model instead of `EncounterFile`.

## Routes

### 1. Direct Image Grading View
- **Route**: `/grading/direct/<uuid>`
- **Method**: GET
- **Permissions**: `admin`, `optometrist`, `ophthalmologist`
- **Description**: Displays a direct image upload for glaucoma grading
- **Access Control**: Consultants can only view images from their own lab units; admins can view all images

### 2. Save Direct Image Glaucoma Grading
- **Route**: `/grading/direct/glaucoma/grade`
- **Method**: POST
- **Permissions**: `admin`, `optometrist`, `ophthalmologist`
- **Description**: Saves a glaucoma grading for a direct image upload
- **Form Parameters**:
  - `uuid`: UUID of the direct image upload
  - `impression`: Grading impression (Normal, Glaucoma Suspect, Glaucoma, Other Retinal, Not gradable)
  - `remarks`: Optional remarks
  - `action`: Action to take after saving (save_close, save_next)
- **Access Control**: Consultants can only grade images from their own lab units; admins can grade all images

### 3. Remove Direct Image Glaucoma Grading
- **Route**: `/grading/direct/glaucoma/remove`
- **Method**: POST
- **Permissions**: `admin`, `optometrist`, `ophthalmologist`
- **Description**: Removes a glaucoma grading for a direct image upload
- **Form Parameters**:
  - `uuid`: UUID of the direct image upload
  - `grading_id`: ID of the grading to remove

## Database Models

### ImageGrading Model Updates

The `ImageGrading` model was updated to support direct image uploads:

- Added `direct_image_upload_id` column (nullable) as a foreign key to `direct_image_uploads`
- Modified `encounter_file_id` column to be nullable
- Added check constraint to ensure exactly one of `encounter_file_id` or `direct_image_upload_id` is set
- Added indexes for better query performance

### Migration

A migration script was created to update the database schema:

```bash
python scripts/migrate_image_grading_nullable_columns.py
python scripts/migrate_image_grading_nullable_columns.py --dry-run
```

## User Interface

### Grading Dashboard

The grading dashboard (`/grading`) was updated to include a "Start Direct Image Grading" button that:
- Jumps to a random verified direct image with Glaucoma disease that hasn't been graded by the current user
- Shows as disabled if no ungraded direct images are found

### Direct Image Grading Page

The direct image grading page (`/grading/direct/<uuid>`) includes:
- Image display with support for edited versions using the `_direct_viewer_card.html` template
- Image viewing controls (filters, brightness, contrast)
- Glaucoma grading form with impression options
- Remarks field for additional notes
- "Save & Close" and "Save & Next" buttons
- "Remove Grading" button for existing gradings
- Access control based on user role and lab unit

## Implementation Details

### Access Control

- Admins can grade any direct image upload
- Consultants (optometrist, ophthalmologist) can only grade images from their own lab units
- Access control is enforced in both the view and grading routes

### Data Validation

- Ensures the direct image upload exists
- Validates that the impression is one of the allowed values
- Checks that the image has been verified before allowing grading

### Workflow

1. User navigates to the grading dashboard
2. User clicks "Start Direct Image Grading" to jump to a random ungraded direct image
3. User selects an impression and optionally adds remarks
4. User clicks "Save & Close" to save and return to the dashboard, or "Save & Next" to save and go to another ungraded image
5. User can remove existing gradings using the "Remove Grading" button

## Future Enhancements

- Add support for DR grading of direct images
- Add support for AMD grading of direct images
- Implement intra-rater agreement tracking for direct image gradings