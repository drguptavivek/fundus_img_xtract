# DirectImages DataFrame Enhancement Plan

## Overview
This document outlines the enhanced DataFrame generation function for DirectImages KPIs, including all required fields for comprehensive analysis.

## Enhanced DataFrame Function Specification

### Function Name
`generate_direct_image_kpi_df()`

### Required Fields (based on user requirements)

#### Core Image Information
- `image_id` - DirectImageUpload.id
- `image_uuid` - DirectImageUpload.uuid
- `filename` - DirectImageUpload.filename
- `file_hash` - DirectImageUpload.file_hash
- `content_hash` - DirectImageUpload.content_hash

#### Upload Information
- `upload_date` - DirectImageUpload.created_at.date()
- `upload_datetime` - DirectImageUpload.created_at
- `uploader_id` - DirectImageUpload.uploader_id
- `uploader_username` - User.username
- `uploader_full_name` - User.full_name

#### Location Information
- `hospital_id` - DirectImageUpload.hospital_id
- `hospital_name` - Hospital.name
- `lab_unit_id` - DirectImageUpload.lab_unit_id
- `lab_unit_name` - LabUnit.name

#### Camera & Disease Information
- `camera_id` - DirectImageUpload.camera_id
- `camera_name` - Camera.name
- `disease_id` - DirectImageUpload.disease_id
- `disease_name` - Disease.name
- `area_id` - DirectImageUpload.area_id
- `area_name` - Area.name

#### Image Properties
- `is_mydriatic` - DirectImageUpload.is_mydriatic
- `is_pregraded` - DirectImageUpload.is_pregraded

#### Verification Information
- `verification_status` - DirectImageVerify.verified_status
- `verification_remarks` - DirectImageVerify.remarks
- `verified_by_id` - DirectImageVerify.verified_by_id
- `verified_by_username` - User.username (verifier)
- `verified_at` - DirectImageVerify.verified_at
- `has_verification` - Boolean flag if verification exists

#### Task Information
- `task_count` - Count of grading tasks for this image

#### Grading Information
- `grading_count` - Count of gradings for this image

### ENRICHMENT
 - Add  `month_year_upload`  

