# AMD Grading Pivot Materialized View

## Overview

`mvw_amd_grading_pivot` is a PostgreSQL materialized view that provides pivoted Age-related Macular Degeneration (AMD) grading data with all grader roles in a single row per task. It unifies image metadata from both encounter files (ZIP-based) and direct uploads, presenting AMD-specific grades from resident, resident2, arbitrator, review, and AI model graders in horizontal columns for simplified analysis.

The view filters specifically for AMD-related diseases (names matching `%amd%` or `%macular degeneration%`) and includes JSONB-indexed feature arrays for detailed grading characteristic analysis.

---

## Use Cases

- **AMD Grading Analytics:** Track AMD grading workflow metrics, completion rates, and grader productivity
- **Grader Performance Analysis:** Compare inter-grader consistency between residents, arbitrators, and reviewers
- **AI Model Evaluation:** Benchmark AI model predictions against human grader consensus for AMD
- **Cohort Analysis:** Extract AMD-graded image cohorts for research or training dataset curation
- **Consensus Tracking:** Monitor consensus agreement rates and arbitrator intervention patterns
- **Feature Analysis:** Query JSONB feature arrays to analyze AMD grading characteristic distributions

---

## Organization

### Image Identification
| Column | Description |
|--------|-------------|
| `image_source` | Source type: `encounter_file` or `direct_upload` |
| `image_id` | Unified image ID (encounter_files.id or direct_image_uploads.id) |
| `image_uuid` | Unique image identifier |
| `filename` | Original filename |
| `eye_side` | Eye side (Left/Right) |

### Context Metadata
| Column | Description |
|--------|-------------|
| `patient_encounter_id` | Patient encounter foreign key |
| `patient_encounter_name` | Encounter display name |
| `patient_identifier` | Patient ID |
| `capture_date` | Image capture date |
| `hospital_name` | Hospital name |
| `lab_unit_name` | Lab unit name |
| `camera_name` | Camera device name |

### Task Information
| Column | Description |
|--------|-------------|
| `task_id` | Grading task ID |
| `task_uuid` | Task unique identifier |
| `task_state` | Task workflow state |
| `task_created_at` | Task creation timestamp |

### Pivoted Grade Columns

Each grader role has the following columns:

**Resident Grade:**
- `resident_grade_id`, `resident_grade`, `resident_grader`
- `resident_grade_time`, `resident_comment`, `resident_features` (JSON)

**Resident2 Grade:**
- `resident2_grade_id`, `resident2_grade`, `resident2_grader`
- `resident2_grade_time`, `resident2_comment`, `resident2_features` (JSON)

**Arbitrator Grade:**
- `arbitrator_grade_id`, `arbitrator_grade`, `arbitrator_grader`
- `arbitrator_grade_time`, `arbitrator_comment`, `arbitrator_features` (JSON)

**Review Grade:**
- `review_grade_id`, `review_grade`, `reviewer_name`
- `review_grade_time`, `review_comment`, `review_features` (JSON)

**AI Model Grades (up to 3 models):**
- `aimodel_1_grade_id`, `aimodel_1_grade`, `aimodel_1_name`, `aimodel_1_time`, `aimodel_1_features` (JSON)
- `aimodel_2_grade_id`, `aimodel_2_grade`, `aimodel_2_name`, `aimodel_2_time`, `aimodel_2_features` (JSON)
- `aimodel_3_grade_id`, `aimodel_3_grade`, `aimodel_3_name`, `aimodel_3_time`, `aimodel_3_features` (JSON)

### Consensus Information
| Column | Description |
|--------|-------------|
| `consensus_grade` | Final consensus grade impression |
| `consensus_method` | Consensus determination method |
| `consensus_decider` | Username of consensus decider |
| `consensus_time` | Consensus timestamp |

---

## Query Examples

### 1. AMD Grading Completion by Lab Unit

```sql
SELECT
    lab_unit_name,
    COUNT(*) as total_tasks,
    COUNT(resident_grade_id) as resident_completed,
    COUNT(resident2_grade_id) as resident2_completed,
    COUNT(arbitrator_grade_id) as arbitrator_completed,
    COUNT(consensus_grade) as consensus_reached
FROM mvw_amd_grading_pivot
GROUP BY lab_unit_name
ORDER BY total_tasks DESC;
```

### 2. Inter-Grader Agreement Analysis

```sql
SELECT
    resident_grader,
    resident2_grader,
    COUNT(*) as total_graded,
    SUM(CASE WHEN resident_grade = resident2_grade THEN 1 ELSE 0 END) as agreement_count,
    ROUND(100.0 * SUM(CASE WHEN resident_grade = resident2_grade THEN 1 ELSE 0 END) / COUNT(*), 2) as agreement_percentage
FROM mvw_amd_grading_pivot
WHERE resident_grade_id IS NOT NULL
  AND resident2_grade_id IS NOT NULL
GROUP BY resident_grader, resident2_grader
ORDER BY agreement_percentage DESC;
```

### 3. AI vs Human Consensus Comparison

```sql
SELECT
    aimodel_1_name as ai_model,
    consensus_grade as human_consensus,
    aimodel_1_grade as ai_prediction,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY aimodel_1_name), 2) as percentage
FROM mvw_amd_grading_pivot
WHERE aimodel_1_grade_id IS NOT NULL
  AND consensus_grade IS NOT NULL
GROUP BY aimodel_1_name, consensus_grade, aimodel_1_grade
ORDER BY ai_model, consensus_grade, count DESC;
```

---

## Technical Details

### Refresh Function
```sql
SELECT refresh_amd_grading_pivot();
```

### Key Indexes
- Image identification: `image_uuid`, `image_source`, `image_id`
- Grade access: `resident_grade_id`, `arbitrator_grade_id`, `consensus_grade`
- Feature search: GIN indexes on all `*_features` JSONB columns
- Time-based: `task_created_at`, `consensus_time`, `last_updated`
- AMD-specific: `disease_name`, `lab_unit_name`, `hospital_name`

### Migration
**File:** `/migrations/versions/cd23f993eaf2_create_amd_grading_pivot_view.py`
**Created:** November 9, 2025

### Automated Refresh
- **Scheduler:** Refreshes every 30 minutes via `materialized_view_scheduler.py`
- **Priority:** 4th in refresh order (after DR and Glaucoma pivots)
- **Manual:** Use admin interface at `/admin/materialized-view-status`

---

## Related Documentation

- **Materialized Views Overview:** `Materialized_Views_Reference.md`
- **Dataset Curation:** `Dataset_Curation_Technical_Reference.md`
- **Scheduler Configuration:** `../10-DEVELOP/APScheduler.md`

---

**Last Updated:** January 16, 2026
**Version:** 1.0
