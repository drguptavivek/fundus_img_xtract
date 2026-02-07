# mvw_image_listing_all_v2 (Per-Disease)

## Purpose
Per-disease materialized views optimized for discrepancy review and export. These views precompute task, consensus, role, and AI data to avoid runtime joins.

## Naming
Each disease gets its own MV:
- `mvw_image_listing_<slug>_<disease_id>_v2`

Slug rules:
- Lowercase
- Non-alphanumeric replaced with `_`
- Example: `Corneal Opacity` -> `mvw_image_listing_corneal_opacity_6_v2`

## Refresh Cadence
- Creation/ensure (daily at 02:00 UTC):
  - `celery_tasks.tasks.mv_tasks.ensure_image_listing_v2_task`
- Refresh (every 30 minutes):
  - `celery_tasks.tasks.mv_tasks.refresh_image_listing_v2_task`

## Base Fields (All Rows)
- `image_uuid`
- `direct_image_uuid`, `encounter_file_uuid`
- `direct_image_upload_id`, `encounter_file_id`, `patient_encounter_id`
- `upload_type` (`Direct`, `Pregraded`, `ZIP`, `SET`)
- `hospital_name`, `lab_unit_name`, `camera_name`, `area_name`
- `direct_filename`, `direct_edited_filename`, `direct_folder_rel`
- `encounter_filename`, `encounter_upload_date`
- `image_filename`, `image_folder_rel`
- `is_set_based`
- `capture_date`, `upload_date_utc`
- `disease_id`, `disease_name`

## Task and Consensus
- `task_id`, `task_uuid`, `task_state`, `task_lab_unit_id`
- `has_consensus`
- `consensus_type` (`match`, `adjudication`, `task_review`)
- `final_grade_name`

## Latest Role Grades (by `grades.created_at`)
- `resident_grade_name`
- `resident2_grade_name`
- `arbitrator_grade_name`
- `review_grade_name`
- `resident_comment`, `resident_selected_features_json`
- `resident2_comment`, `resident2_selected_features_json`
- `arbitrator_comment`, `arbitrator_selected_features_json`
- `review_comment`, `review_selected_features_json`

## Role Presence Flags
- `has_resident`
- `has_resident2`
- `has_arbitrator`
- `has_review`
- `has_ai`

## Derived Field
- `resident_vs_resident2` (`match`, `mismatch`, `null`)

## AI Model Map
- `ai_models_json` (JSONB map keyed by `ai_model_id`)

Each entry:
- `ai_model_id`, `ai_model_name`, `ai_model_version`
- `ai_grade_id`, `ai_grade_name`, `ai_grade_created_at`
- `ai_comment`, `ai_selected_features`
- `ai_review_status`, `ai_review_comment`, `ai_reviewed_by_user_id`, `ai_reviewed_at`
- `ai_probability` parsed from comment (`AI probability: <value>`)

## Implementation Notes
- Rows are task-scoped per disease (no cross-disease or image-only rows).
- New diseases are auto-created by the daily ensure task; no migration needed.
