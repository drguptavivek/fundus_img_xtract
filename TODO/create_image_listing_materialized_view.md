# Create Image Listing Materialized View

## Overview
Create a comprehensive materialized view `mvw_image_listing_all` that provides a complete catalog of all images with their grading status, AI integration, and consensus tracking.

## Column Structure

### Core Identification
- `image_uuid` - Primary UUID for the image
- `image_upload_task_uuid` - Upload task UUID reference
- `encounter_file_uuid` - Encounter file UUID reference (if applicable)

### Upload & Classification
- `upload_type` - 'ZIP' | 'Direct' | 'Pregraded'
- `verified_status_direct` - 0/1 for direct upload verification
- `verified_status_zip` - 0/1 for zip verification
- `is_pregraded` - 0/1 for pregraded images
- `has_dr_report` - 0/1
- `has_glaucoma_report` - 0/1

### Location & Metadata
- `hospital_name` - Hospital name
- `lab_unit_name` - Lab unit name
- `camera_name` - Camera equipment name
- `area_name` - Area/location name
- `is_mydriatic` - 0/1 for direct uploads
- `capture_date` - Capture date for ZIP images
- `upload_date_ist` - Upload date in IST timezone

### Task Configuration
- `has_dr_task` - 0/1
- `has_glaucoma_task` - 0/1
- `has_amd_task` - 0/1

### Disease Configuration
- `original_disease_uploaded` - Disease tag for upload (DR/Glaucoma/AMD)
- `additional_glaucoma_disease` - 0/1 if glaucoma added during ZIP processing

### Grading Analytics
- `dr_grading_count` - Number of DR gradings completed (human only)
- `glaucoma_grading_count` - Number of glaucoma gradings completed (human only)
- `amd_grading_count` - Number of AMD gradings completed (human only)
- `dr_ai_grading_count` - Number of DR AI gradings completed
- `glaucoma_ai_grading_count` - Number of glaucoma AI gradings completed
- `amd_ai_grading_count` - Number of AMD AI gradings completed

### Consensus Status
- `dr_consensus_status` - 0/1 for consensus achieved across DR gradings (human graders only)
- `glaucoma_consensus_status` - 0/1 for consensus achieved across glaucoma graders (human graders only)
- `amd_consensus_status` - 0/1 for consensus achieved across AMD graders (human graders only)

### Detailed Grading Data (JSON columns including AI)
- `dr_grading_details_json` - Denormalized DR grading data with UUIDs for both human and AI gradings
- `glaucoma_grading_details_json` - Denormalized glaucoma grading data with UUIDs for both human and AI gradings
- `amd_grading_details_json` - Denormalized AMD grading data with UUIDs for both human and AI gradings

## JSON Column Structure
Each disease-specific JSON column will contain:
- Human grader data (resident, resident2, arbitrator, review roles)
- AI model grading data (ai role)
- All grading instances with their UUIDs, grades, features, timestamps
- Grader type identification to distinguish human vs AI grades

## Minimal Indexing Strategy
- `idx_image_listing_uuid` on `image_uuid`
- `idx_image_listing_hospital` on `hospital_name`
- `idx_image_listing_lab_unit` on `lab_unit_name`
- `idx_image_listing_capture_date` on `capture_date`
- `idx_image_listing_upload_date` on `upload_date_ist`
- `idx_image_listing_upload_type` on `upload_type`
- `idx_image_listing_dr_grading_details` GIN on `dr_grading_details_json::jsonb`
- `idx_image_listing_glaucoma_grading_details` GIN on `glaucoma_grading_details_json::jsonb`
- `idx_image_listing_amd_grading_details` GIN on `amd_grading_details_json::jsonb`

## Implementation Steps

### Step 1: Database Migration
- Create alembic revision file
- Define materialized view SQL
- Add minimal indexes
- Create refresh function `refresh_image_listing_all()`
- Include proper upgrade/downgrade functions

### Step 2: Scheduler Integration
- Update `utils/materialized_view_scheduler.py`
- Add view to refresh list
- Update view descriptions
- Integrate with existing logging

### Step 3: Admin Interface
- Create admin route for monitoring
- Add manual refresh capability
- Include status monitoring
- Add to existing admin interface

### Step 4: Testing & Validation
- Test manual refresh
- Validate data accuracy
- Check consensus calculation
- Verify AI integration
- Performance testing

## Technical Requirements

### Database Session Management
- Use `db_transaction_manager` for proper session handling
- Follow existing patterns from other materialized views
- Implement proper error handling and logging

### Timezone Handling
- Store dates in UTC
- Display upload dates in IST
- Follow existing datetime patterns

### JSON Feature Analysis
- Include GIN indexes for JSON columns
- Support complex queries on grading data
- Maintain compatibility with existing analytics

### Privacy & Security
- No patient identifiers
- No file names or folder references
- Only UUIDs and non-PHI administrative data
- Follow existing security patterns

## Dependencies
- Existing `utils/materialized_view_scheduler.py`
- `db_transaction_manager` for session management
- Existing materialized view patterns
- Admin interface structure

## Success Criteria
- Materialized view created successfully
- Data accuracy validated
- Performance meets requirements
- Admin interface functional
- Scheduler integration working
- AI grades properly included