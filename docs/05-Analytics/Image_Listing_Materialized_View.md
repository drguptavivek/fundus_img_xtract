# Image Listing Materialized View

## Overview

`mvw_image_listing_all` provides a unified catalog of all fundus images from both Direct Upload and ZIP-based ingestion sources. This view normalizes data from `direct_image_uploads` and `encounter_files` into a single queryable interface, with comprehensive task counts, grading statistics, and JSON-formatted grading details for each image.

The view supports image-level analytics across upload types, enabling cross-source search, verification workflow tracking, and inventory management without expensive JOINs on base tables.

## Use Cases

- **Image search and filtering** - Find images by upload type, verification status, lab unit, camera, hospital, or date range
- **Verification workflow tracking** - Monitor verified vs unverified images for Direct (verified_status_direct) and ZIP (verified_status_zip) uploads
- **Cross-upload-type analytics** - Compare Direct, Pregraded, and ZIP upload patterns side-by-side
- **Grading progress monitoring** - Track task creation and grading counts per image/disease
- **Discrepancy review** - Query images with specific grading patterns for quality review (see `review/route_discrepancy_review.py`)
- **Dataset curation** - Filter images by grading completeness, AI model usage, or consensus status for AI training datasets

## Organization

### Core Identification

| Column | Purpose |
|--------|---------|
| `image_uuid` | Unique image identifier (primary key for queries) |
| `image_upload_task_uuid` | Direct upload task UUID (NULL for ZIP images) |
| `encounter_file_uuid` | ZIP encounter file UUID (NULL for Direct uploads) |
| `direct_image_upload_id` | Foreign key to `direct_image_uploads.id` |
| `encounter_file_id` | Foreign key to `encounter_files.id` |

### Upload Classification

| Column | Purpose |
|--------|---------|
| `upload_type` | 'Direct', 'Pregraded', or 'ZIP' |
| `verified_status_direct` | 1 if Direct upload verified, else 0 |
| `verified_status_zip` | 1 if ZIP image has eye_side marked, else 0 |
| `is_pregraded` | TRUE for pregraded Direct uploads |
| `laterality` | Eye side ('OD'/OS'/OU') for ZIP uploads, NULL for Direct |

### Location & Metadata

| Column | Purpose |
|--------|---------|
| `hospital_name` | Hospital name (Direct uploads only) |
| `lab_unit_name` | Lab unit name (all sources) |
| `camera_name` | Camera name (Direct uploads only) |
| `area_name` | Area name (Direct uploads only) |
| `is_mydriatic` | Mydriatic flag (Direct uploads only) |
| `original_disease_uploaded` | Primary disease configured for image |
| `additional_glaucoma_disease` | 1 if ZIP image has Glaucoma report, else 0 |

### Date Tracking

| Column | Purpose |
|--------|---------|
| `capture_date` | Original capture date (ZIP only) |
| `upload_date_utc` | Upload timestamp (all sources) |

### Report Availability (ZIP only)

| Column | Purpose |
|--------|---------|
| `has_glaucoma_report` | 1 if Glaucoma report exists, else 0 |
| `has_dr_report` | 1 if DR report exists, else 0 |

### Task & Grading Counts

| Column | Purpose |
|--------|---------|
| `has_dr_task` / `has_glaucoma_task` / `has_amd_task` | Task existence flags (1/0) |
| `dr_grading_count` / `glaucoma_grading_count` / `amd_grading_count` | Total human grades per disease |
| `dr_ai_grading_count` / `glaucoma_ai_grading_count` / `amd_ai_grading_count` | AI grades per disease |
| `dr_consensus_status` / `glaucoma_consensus_status` / `amd_consensus_status` | Consensus existence flags (1/0) |

### Grading Details (JSONB)

| Column | Purpose |
|--------|---------|
| `dr_grading_details_json` | Array of all DR grades with grader, grade, AI model, features |
| `glaucoma_grading_details_json` | Array of all Glaucoma grades with grader, grade, AI model, features |
| `amd_grading_details_json` | Array of all AMD grades with grader, grade, AI model, features |

Each JSON object includes:
- `grade_id`, `role_slot` (resident/resident2/arbitrator/review/ai)
- `grader_user_id`, `grade_name`, `grade_description`, `comment`
- `selected_features` (JSON array), `ai_model_id`, `ai_model_name`
- `created_at` timestamp

## Query Examples

### Find unverified Direct uploads by lab unit

```sql
SELECT image_uuid, hospital_name, camera_name, upload_date_utc
FROM mvw_image_listing_all
WHERE upload_type = 'Direct'
  AND verified_status_direct = 0
  AND lab_unit_name = 'Lab Unit A'
ORDER BY upload_date_utc DESC;
```

### Find ZIP images missing Glaucoma grading

```sql
SELECT
    image_uuid,
    capture_date,
    has_glaucoma_report,
    glaucoma_grading_count,
    glaucoma_consensus_status
FROM mvw_image_listing_all
WHERE upload_type = 'ZIP'
  AND has_glaucoma_task = 1
  AND glaucoma_grading_count = 0
ORDER BY capture_date DESC;
```

### Search images with specific grading patterns (using JSONB)

```sql
-- Find DR images with resident grade 'Moderate' but no consensus
SELECT
    image_uuid,
    upload_type,
    dr_grading_count,
    dr_consensus_status,
    dr_grading_details_json
FROM mvw_image_listing_all
WHERE dr_grading_count > 0
  AND dr_consensus_status = 0
  AND EXISTS (
      SELECT 1
      FROM jsonb_array_elements(dr_grading_details_json::jsonb) elem
      WHERE elem->>'role_slot' = 'resident'
        AND elem->>'grade_name' = 'Moderate'
  );
```

### Track verification progress by upload type

```sql
SELECT
    upload_type,
    COUNT(*) as total_images,
    SUM(verified_status_direct) as verified_direct,
    SUM(verified_status_zip) as verified_zip,
    ROUND(100.0 * SUM(verified_status_direct + verified_status_zip) / COUNT(*), 2) as verification_pct
FROM mvw_image_listing_all
GROUP BY upload_type;
```

## Refresh Schedule

Refreshes every 30 minutes via the materialized view scheduler (see `utils/materialized_view_scheduler.py`). Manual refresh available via admin interface using `refresh_image_listing_all()` function.

## Migration

Created in `/migrations/versions/819e7a97ca1f_create_image_listing_materialized_view.py`

## Key Integrations

- **`utils/mvw_all_img_search.py`** - Primary search interface using MV for complex filtering
- **`review/route_discrepancy_review.py`** - Discrepancy review queries against MV
- **`public/analytics.py`** - Analytics dashboard queries
- **`utils/review_navigation.py`** - Review workflow navigation

## Performance Notes

- 30+ indexes including GIN indexes on JSONB columns for fast JSON queries
- Composite indexes on common query patterns (lab_unit + date, disease + tasks)
- Typical query response time: <100ms for filtered searches with pagination
