# Glaucoma Grading Pivot Materialized View

## Overview

`mvw_glaucoma_grading_pivot` is a PostgreSQL materialized view that provides glaucoma-specific grading analytics with pivoted grader columns. It consolidates data from grading tasks, patient encounters, and multi-tier grading workflows into a single denormalized table optimized for analytics and reporting. The view supports the dual-grading workflow (resident → resident2 → arbitrator) and includes AI model grades and consensus decisions.

## Use Cases

- **Grading Analytics:** Track glaucoma grade distributions, severity patterns, and clinical decision trends
- **Grader Performance:** Compare resident, resident2, and arbitrator grading patterns and consistency
- **AI vs Human Comparison:** Analyze agreement between AI model predictions and human graders
- **Quality Assurance:** Identify discrepant cases requiring arbitration or review
- **Dataset Curation:** Export filtered glaucoma grading data for AI training datasets
- **Workflow Monitoring:** Track task completion rates by lab unit, hospital, and grader
- **Consensus Tracking:** Monitor consensus grade outcomes and decision methods

## Organization

### Image Identification

| Column | Purpose |
|--------|---------|
| `image_source` | Source type: `encounter_file` or `direct_upload` |
| `image_id` | Unified image ID (encounter_files.id or direct_image_uploads.id) |
| `image_uuid` | Image UUID for linking to other systems |
| `filename` | Original filename |
| `eye_side` | `OD` (right) or `OS` (left) |

### Context & Metadata

| Column | Purpose |
|--------|---------|
| `patient_encounter_id` | FK to patient_encounters |
| `patient_identifier` | Patient ID from encounter |
| `capture_date` | Image capture date |
| `hospital_name` | Hospital name (for direct uploads) |
| `lab_unit_name` | Lab unit assigned to task |
| `disease_name` | Filtered to glaucoma variants |
| `is_mydriatic` | Mydriatic imaging flag (direct uploads) |
| `is_pregraded` | Pre-graded data flag (direct uploads) |

### Task Information

| Column | Purpose |
|--------|---------|
| `task_id` | Grading task primary key |
| `task_uuid` | Task UUID for API references |
| `task_state` | Task state (pending, in_progress, completed) |
| `task_created_at` | Task creation timestamp |

### Pivoted Grader Columns

**Resident Grade (First Pass):**
- `resident_grade_id`, `resident_grade`, `resident_grader`
- `resident_grade_time`, `resident_comment`
- `resident_features` (JSONB with GIN index)

**Resident2 Grade (Second Pass):**
- `resident2_grade_id`, `resident2_grade`, `resident2_grader`
- `resident2_grade_time`, `resident2_comment`
- `resident2_features` (JSONB with GIN index)

**Arbitrator Grade (Dispute Resolution):**
- `arbitrator_grade_id`, `arbitrator_grade`, `arbitrator_grader`
- `arbitrator_grade_time`, `arbitrator_comment`
- `arbitrator_features` (JSONB with GIN index)

**Review Grade (Quality Assurance):**
- `review_grade_id`, `review_grade`, `reviewer_name`
- `review_grade_time`, `review_comment`
- `review_features` (JSONB with GIN index)

### AI Model Grades (Up to 3 Models)

| Column | Purpose |
|--------|---------|
| `aimodel_1_grade_id`, `aimodel_1_grade`, `aimodel_1_name` | First AI model prediction |
| `aimodel_1_time`, `aimodel_1_features` | Timing and feature data |
| `aimodel_2_*`, `aimodel_3_*` | Additional AI model columns |

### Consensus & Metadata

| Column | Purpose |
|--------|---------|
| `consensus_grade` | Final agreed grade |
| `consensus_method` | How consensus was reached |
| `consensus_decider` | User who made final decision |
| `consensus_time` | When consensus was reached |
| `last_updated` | Task last updated timestamp |

## Query Examples

### Example 1: Grader Agreement Analysis

Compare resident and resident2 grades for glaucoma cases:

```sql
SELECT
    resident_grader,
    resident2_grader,
    resident_grade,
    resident2_grade,
    COUNT(*) as case_count,
    CASE
        WHEN resident_grade = resident2_grade THEN 'Agree'
        ELSE 'Disagree'
    END as agreement_status
FROM mvw_glaucoma_grading_pivot
WHERE resident_grade IS NOT NULL
  AND resident2_grade IS NOT NULL
GROUP BY resident_grader, resident2_grader, resident_grade, resident2_grade, agreement_status
ORDER BY case_count DESC;
```

### Example 2: Arbitration Cases by Hospital

Identify cases requiring arbitration for quality review:

```sql
SELECT
    hospital_name,
    lab_unit_name,
    COUNT(*) FILTER (WHERE arbitrator_grade_id IS NOT NULL) as arbitration_count,
    COUNT(*) FILTER (WHERE arbitrator_grade_id IS NOT NULL
                     AND resident_grade != arbitrator_grade) as resident_overturned,
    COUNT(*) FILTER (WHERE arbitrator_grade_id IS NOT NULL
                     AND resident2_grade != arbitrator_grade) as resident2_overturned,
    AVG(EXTRACT(EPOCH FROM (arbitrator_grade_time - resident_grade_time))/3600) as avg_hours_to_arbitration
FROM mvw_glaucoma_grading_pivot
WHERE task_created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY hospital_name, lab_unit_name
ORDER BY arbitration_count DESC;
```

### Example 3: AI Model Performance vs Human Graders

Compare AI model predictions with final consensus grades:

```sql
SELECT
    aimodel_1_name as ai_model,
    aimodel_1_grade as ai_prediction,
    consensus_grade as human_consensus,
    COUNT(*) as case_count,
    ROUND(100.0 * COUNT(*) FILTER (WHERE aimodel_1_grade = consensus_grade) / COUNT(*), 2) as agreement_percentage
FROM mvw_glaucoma_grading_pivot
WHERE aimodel_1_grade IS NOT NULL
  AND consensus_grade IS NOT NULL
  AND task_created_at >= CURRENT_DATE - INTERVAL '90 days'
GROUP BY ai_model, ai_prediction, consensus_grade
ORDER BY case_count DESC
LIMIT 20;
```

## Refresh & Maintenance

**Refresh Function:** `refresh_glaucoma_grading_pivot()`

**Automatic Schedule:** 4x daily (07:00, 13:30, 19:00, 01:30 IST) via scheduler

**Manual Refresh:**
```sql
SELECT refresh_glaucoma_grading_pivot();
-- OR
REFRESH MATERIALIZED VIEW CONCURRENTLY mvw_glaucoma_grading_pivot;
```

**Index Count:** 25+ optimized indexes including:
- Image identification (uuid, source, id)
- Grade IDs for direct access
- Grade values for filtering
- GIN indexes on JSONB feature columns
- Time-based indexes for trending
- Grader and hospital analysis indexes

## Migration

**File:** `/migrations/versions/6c48c37fc19a_create_glaucoma_grading_pivot_view.py`

**Created:** 2025-11-09

**Dependencies:** Requires `diseases` table with glaucoma entries

## Related Documentation

- **Materialized Views Overview:** `Materialized_Views_Reference.md`
- **DR Pivot View:** `DR_Grading_Pivot_Materialized_View.md`
- **AMD Pivot View:** `AMD_Grading_Pivot_Materialized_View.md`
- **Scheduler:** `../10-DEVELOP/APScheduler.md`
- **Analytics System:** `../11-KPI and DFs/comprehensive_analytics_reporting_system.md`

---

**Last Updated:** January 16, 2026
**Version:** 1.0
