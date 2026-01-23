# DR Grading Pivot Materialized View

## Overview

`mvw_diabetic_retinopathy_grading_pivot` provides a wide-format, pivoted view of diabetic retinopathy grading data with all grader roles (resident, resident2, arbitrator, review, AI models) in a single row per task. This view is optimized for DR-specific analytics, performance comparison, and consensus tracking.

**Key difference from `mvw_grading_data_all`:** This view pivots grader roles into columns instead of one row per grade, making it ideal for side-by-side comparison and agreement analysis.

---

## Use Cases

- **Grader Performance Analysis** - Compare resident vs resident2 vs arbitrator grades
- **AI vs Human Comparison** - Analyze AI model performance against human graders
- **Consensus Tracking** - Track consensus grades, methods, and deciders
- **Feature-Based Analysis** - Query selected_features JSONB for specific DR features
- **Disagreement Detection** - Identify cases where grader opinions differ
- **Workflow Analytics** - Track task states, completion times, and grader throughput
- **DR-Specific Reporting** - Generate DR cohort reports and KPI dashboards

---

## Organization

### Image Identification
- `image_source` - Source type: 'encounter_file' or 'direct_upload'
- `image_id` - Unified image ID (encounter_files.id or direct_image_uploads.id)
- `image_uuid` - Image UUID for linking
- `filename` - Original filename
- `eye_side` - 'OD' (right) or 'OS' (left)

### Context & Metadata
- `patient_encounter_id`, `patient_encounter_name`, `patient_identifier`
- `hospital_name`, `lab_unit_name`, `camera_name`
- `capture_date`, `task_created_at`, `task_state`
- `is_mydriatic`, `is_pregraded` - Direct upload flags

### DR-Specific
- `disease_name` - Filtered for '%retinopathy%'
- `task_id`, `task_uuid` - Grading task references

### Pivoted Human Grader Columns

**Resident (Primary Grader)**
- `resident_grade_id`, `resident_grade` - Grade reference and impression
- `resident_grader` - Username
- `resident_grade_time` - Timestamp
- `resident_comment`, `resident_features` (JSONB)

**Resident2 (Secondary Grader)**
- `resident2_grade_id`, `resident2_grade`, `resident2_grader`
- `resident2_grade_time`, `resident2_comment`, `resident2_features`

**Arbitrator (Dispute Resolution)**
- `arbitrator_grade_id`, `arbitrator_grade`, `arbitrator_grader`
- `arbitrator_grade_time`, `arbitrator_comment`, `arbitrator_features`

**Review (Final Review)**
- `review_grade_id`, `review_grade`, `reviewer_name`
- `review_grade_time`, `review_comment`, `review_features`

### AI Model Grades (Up to 3 Models)
- `aimodel_1_grade`, `aimodel_1_name`, `aimodel_1_time`, `aimodel_1_features`
- `aimodel_2_grade`, `aimodel_2_name`, `aimodel_2_time`, `aimodel_2_features`
- `aimodel_3_grade`, `aimodel_3_name`, `aimodel_3_time`, `aimodel_3_features`

### Consensus
- `consensus_grade` - Final agreed grade
- `consensus_method` - How consensus was reached
- `consensus_decider` - Username who made final decision
- `consensus_time` - Decision timestamp

---

## Query Examples

### Example 1: Grader Agreement Analysis

Compare resident vs resident2 agreement for DR tasks:

```sql
SELECT
    resident_grader,
    resident2_grader,
    resident_grade,
    resident2_grade,
    COUNT(*) as task_count,
    CASE
        WHEN resident_grade = resident2_grade THEN 'Agree'
        ELSE 'Disagree'
    END as agreement_status
FROM mvw_diabetic_retinopathy_grading_pivot
WHERE resident_grade IS NOT NULL
  AND resident2_grade IS NOT NULL
  AND task_created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY resident_grader, resident2_grader, resident_grade, resident2_grade
ORDER BY task_count DESC;
```

### Example 2: AI vs Human Performance

Compare AI model performance against arbitrator grades:

```sql
SELECT
    aimodel_1_name as ai_model,
    aimodel_1_grade as ai_grade,
    arbitrator_grade,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentage
FROM mvw_diabetic_retinopathy_grading_pivot
WHERE aimodel_1_grade IS NOT NULL
  AND arbitrator_grade IS NOT NULL
  AND task_created_at >= CURRENT_DATE - INTERVAL '90 days'
GROUP BY aimodel_1_name, aimodel_1_grade, arbitrator_grade
ORDER BY aimodel_1_name, arbitrator_grade, count DESC;
```

### Example 3: Consensus Method Analysis

Track consensus methods and decider performance:

```sql
SELECT
    consensus_method,
    consensus_decider,
    consensus_grade,
    COUNT(*) as consensus_count,
    AVG(EXTRACT(EPOCH FROM (consensus_time - task_created_at))/3600) as avg_hours_to_consensus
FROM mvw_diabetic_retinopathy_grading_pivot
WHERE consensus_grade IS NOT NULL
  AND consensus_time >= CURRENT_DATE - INTERVAL '60 days'
GROUP BY consensus_method, consensus_decider, consensus_grade
ORDER BY consensus_count DESC;
```

### Example 4: Feature-Based Query

Query tasks with specific DR features (using JSONB index):

```sql
SELECT
    image_uuid,
    filename,
    resident_grade,
    resident_features
FROM mvw_diabetic_retinopathy_grading_pivot
WHERE resident_features @> '[{"feature": "microaneurysms", "present": true}]'
  AND task_created_at >= CURRENT_DATE - INTERVAL '30 days'
LIMIT 100;
```

---

## Refresh & Maintenance

**Refresh Function:** `refresh_diabetic_retinopathy_grading_pivot()`

**Automatic Schedule:** Every 30 minutes (configurable)

**Manual Refresh:**
```sql
REFRESH MATERIALIZED VIEW mvw_diabetic_retinopathy_grading_pivot;
-- or
SELECT refresh_diabetic_retinopathy_grading_pivot();
```

**Key Indexes:**
- Image identification: `image_uuid`, `image_id`, `image_source`
- Grade analysis: `resident_grade`, `arbitrator_grade`, `consensus_grade`
- Grader analysis: `resident_grader`, `arbitrator_grader`
- Time-based: `task_created_at`, `consensus_time`
- JSONB features: GIN indexes on all `*_features` columns

---

## Migration Details

**Migration File:** `/migrations/versions/cee197bc69ef_create_diabetic_retinopathy_grading_.py`

**Revision ID:** `cee197bc69ef`

**Created:** 2025-11-10

---

## Related Documentation

- **All Materialized Views:** `Materialized_Views_Reference.md`
- **Grading Data (All Diseases):** See `mvw_grading_data_all` in reference above
- **Encounter Analytics:** `Encounter_Pivot_Materialized_View.md`
- **Refresh Scheduler:** `../10-DEVELOP/APScheduler.md`

---

**Last Updated:** January 16, 2026
**Version:** 1.0
