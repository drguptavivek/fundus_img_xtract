# mvw_grading_data_all - Materialized View

## Overview

`mvw_grading_data_all` provides a comprehensive, non-pivoted view of all grading activity across the system. It unifies grading data from both encounter-based (ZIP upload) and direct upload workflows, containing one row per individual grade with complete context including image metadata, task information, grader details, AI model data, and consensus results.

This view serves as the foundational data source for cross-disease analytics, grading workflow analysis, and historical tracking of all grading activity regardless of disease type or role slot.

## Use Cases

- **Cross-disease analytics** - Compare grading patterns, completion rates, and grader performance across DR, Glaucoma, and AMD
- **Grading workflow analysis** - Track task progression through resident → resident2 → arbitrator consensus pipeline
- **Discrepancy detection** - Identify tasks where graders disagree by comparing grades within the same task
- **Export and reporting** - Generate detailed grading reports with full audit trail
- **Historical grade tracking** - Analyze grading trends and individual grader performance over time
- **AI vs human comparison** - Compare AI model grades against human grader outputs
- **Consensus analytics** - Analyze consensus methods, arbitrator decisions, and disagreement patterns

## Organization

### Image Source & Context
| Column | Purpose |
|--------|---------|
| `image_source` | Source type: `encounter_file` or `direct_upload` |
| `image_id` | Unified image ID (encounter_files.id or direct_image_uploads.id) |
| `image_uuid` | Unique image identifier for referencing |
| `filename` | Original filename of the uploaded image |
| `eye_side` | Eye side (left/right) if applicable |
| `file_type` | Image file type classification |
| `hospital_id`, `hospital_name` | Hospital context (direct uploads only) |
| `lab_unit_id`, `lab_unit_name` | Lab unit responsible for grading |
| `camera_id`, `camera_name` | Camera used for image capture |
| `area_id`, `area_name` | Geographic area classification |

### Task Information
| Column | Purpose |
|--------|---------|
| `task_id`, `task_uuid` | Grading task identifier |
| `disease_id`, `disease_name` | Disease being graded (DR/Glaucoma/AMD) |
| `task_state` | Current workflow state |
| `task_created_at` | Task creation timestamp |

### Individual Grade Details
| Column | Purpose |
|--------|---------|
| `grade_id` | Unique grade record identifier |
| `grade_role_slot` | Role: `resident`, `resident2`, `arbitrator`, `review`, `ai` |
| `grader_user_id`, `grader_username`, `grader_full_name` | Grader identity |
| `grade_name` | Grade/impression assigned |
| `grade_description` | Detailed grade description |
| `grade_comment` | Free-text comments from grader |
| `selected_features_json` | JSON array of selected features |
| `grade_time_taken` | Time spent grading (seconds) |
| `grade_start_time`, `grade_created_at` | Grade timestamps |

### AI Model Information
| Column | Purpose |
|--------|---------|
| `ai_model_id` | AI model identifier |
| `ai_model_name`, `ai_model_version` | Model metadata |

### Consensus Information
| Column | Purpose |
|--------|---------|
| `consensus_id` | Consensus record identifier |
| `consensus_method` | How consensus was reached (`auto`, `arbitrator`, etc.) |
| `consensus_final_grade_id` | Final agreed-upon grade ID |
| `consensus_final_grade_name` | Final agreed-upon grade name |
| `consensus_decided_by_user_id`, `consensus_decider_name` | Arbitrator identity |
| `consensus_created_at` | Consensus timestamp |

### Direct Upload Metadata (Nullable)
| Column | Purpose |
|--------|---------|
| `is_mydriatic` | Mydriatic imaging flag |
| `is_pregraded` | Pre-graded data flag |
| `file_hash`, `content_hash` | File integrity hashes |
| `folder_rel`, `edited_filename` | File organization metadata |
| `uploader_id` | User who uploaded the image |

## Query Examples

### Example 1: Find Disagreements Between Resident and Resident2
```sql
-- Identify tasks where resident and resident2 assigned different grades
WITH resident_grades AS (
    SELECT task_id, grade_name
    FROM mvw_grading_data_all
    WHERE grade_role_slot = 'resident'
),
resident2_grades AS (
    SELECT task_id, grade_name
    FROM mvw_grading_data_all
    WHERE grade_role_slot = 'resident2'
)
SELECT
    r.task_id,
    r.grade_name AS resident_grade,
    r2.grade_name AS resident2_grade,
    mv.disease_name,
    mv.image_uuid,
    mv.lab_unit_name
FROM resident_grades r
JOIN resident2_grades r2 ON r.task_id = r2.task_id
JOIN mvw_grading_data_all mv ON r.task_id = mv.task_id
WHERE r.grade_name != r2.grade_name
LIMIT 100;
```

### Example 2: Grader Performance Summary by Disease
```sql
-- Calculate grading metrics per grader, grouped by disease
SELECT
    grader_full_name,
    disease_name,
    grade_role_slot,
    COUNT(*) AS total_grades,
    COUNT(DISTINCT task_id) AS unique_tasks,
    AVG(grade_time_taken) AS avg_time_seconds,
    MIN(grade_created_at) AS first_grade,
    MAX(grade_created_at) AS last_grade
FROM mvw_grading_data_all
WHERE grade_role_slot IN ('resident', 'resident2', 'arbitrator')
    AND grade_created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY grader_full_name, disease_name, grade_role_slot
ORDER BY disease_name, grade_role_slot, total_grades DESC;
```

### Example 3: AI vs Human Grade Comparison
```sql
-- Compare AI model grades against final consensus grades
WITH ai_grades AS (
    SELECT
        task_id,
        ai_model_name,
        ai_model_version,
        grade_name AS ai_grade
    FROM mvw_grading_data_all
    WHERE grade_role_slot = 'ai'
),
consensus_grades AS (
    SELECT
        task_id,
        consensus_final_grade_name AS final_grade
    FROM mvw_grading_data_all
    WHERE consensus_id IS NOT NULL
)
SELECT
    ai.ai_model_name,
    ai.ai_model_version,
    COUNT(*) AS total_comparisons,
    SUM(CASE WHEN ai.ai_grade = c.final_grade THEN 1 ELSE 0 END) AS matches,
    ROUND(100.0 * SUM(CASE WHEN ai.ai_grade = c.final_grade THEN 1 ELSE 0 END) / COUNT(*), 2) AS agreement_percentage
FROM ai_grades ai
JOIN consensus_grades c ON ai.task_id = c.task_id
GROUP BY ai.ai_model_name, ai.ai_model_version
ORDER BY agreement_percentage DESC;
```

## Refresh & Maintenance

**Refresh Schedule:** Every 30 minutes (automatic) or on-demand via admin interface

**Refresh Function:**
```sql
SELECT refresh_grading_data_view();
```

**Manual Refresh:**
```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY mvw_grading_data_all;
```

**Indexes:** Comprehensive indexes on `image_uuid`, `task_id`, `grader_user_id`, `grade_role_slot`, `disease_id`, `task_created_at`, `grade_created_at`, `consensus_method`, `hospital_id`, `lab_unit_id`, `camera_id`

**Migration:** `/migrations/versions/ef304c5f8dd9_create_grading_data_materialized_view.py`

---

**Related Documentation:**
- Materialized Views Reference: `Materialized_Views_Reference.md`
- Scheduler: `utils/materialized_view_scheduler.py`
- Usage in discrepancy review: `review/route_discrepancy_review.py`
- Usage in KPIs: `api/kpis/direct_files_kpis.py`

**Last Updated:** January 16, 2026
