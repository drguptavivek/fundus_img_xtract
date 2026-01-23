# Encounter Pivot Materialized View

## Overview

`mvw_encounter_pivot` provides encounter-level analytics with individual image-grade pivots for multi-disease grading (DR, Glaucoma, AMD). One row per patient encounter containing all images, tasks, grades (resident/resident2/arbitrator/AI/consensus), disease reports, and verification status.

**Use for:** Encounter-level dashboards, multi-disease cohort analysis, workflow monitoring, and operational reporting.

---

## Use Cases

- **Multi-disease cohort analysis** - Find encounters with specific disease/task combinations
- **Grading workflow monitoring** - Track task status (pending/resident_done/arbitration/final) by encounter
- **Research dataset curation** - Extract encounters with specific grade patterns or VCDR ranges
- **Operational reporting** - Hospital/lab workload stats, verification completeness, throughput trends
- **Quality assurance** - Identify incomplete grading, missing tasks, or data quality issues
- **Cross-disease correlation** - Analyze patients with multiple disease gradings

---

## Organization

### Core Columns

| Column | Purpose |
|--------|---------|
| `encounter_id`, `encounter_name`, `patient_identifier` | Encounter identification |
| `capture_date` | Encounter date (TIMESTAMP) |
| `hospital_id`, `hospital_name`, `lab_unit_id`, `lab_unit_name` | Context/hierarchy |
| `total_images` | Image count in encounter |
| `image_uuids`, `eye_sides`, `image_types` | JSON arrays of image metadata |

### Verification Status

| Column | Purpose |
|--------|---------|
| `encounter_verified_status` | Overall encounter verification |
| `glaucoma_verified_status` | Glaucoma report verification |
| `dr_verified_status` | DR report verification |

### Disease Task Counts

| Column | Purpose |
|--------|---------|
| `dr_task_count`, `glaucoma_task_count`, `amd_task_count` | Tasks by disease |
| `additional_disease_task_count` | Other diseases |
| `total_task_count` | Sum of all tasks |
| `pending_tasks`, `resident_done_tasks`, `resident2_done_tasks`, `arbitration_tasks`, `final_tasks` | Status breakdown |

### Disease Reports

| Column | Purpose |
|--------|---------|
| `dr_result`, `dr_qualitative_result`, `dr_report_file_name` | DR report output |
| `glaucoma_result`, `glaucoma_qualitative_result`, `glaucoma_report_file_name` | Glaucoma report output |
| `glaucoma_vcdr_right_num`, `glaucoma_vcdr_left_num` | VCDR values |

### Individual Image Grades (JSON)

**Column:** `image_grade_pivots` (JSON array)

Each object contains all grades for one image:
```json
{
  "image_id": 123,
  "image_uuid": "uuid",
  "eye_side": "left",
  "file_type": "image",
  "dr_resident_grade": "Mild NPDR",
  "dr_resident2_grade": "Moderate NPDR",
  "dr_arbitrator_grade": "Mild NPDR",
  "dr_ai_grade": "Moderate NPDR",
  "dr_consensus_grade": "Mild NPDR",
  "glaucoma_resident_grade": "Normal",
  "glaucoma_arbitrator_grade": "Normal",
  "glaucoma_consensus_grade": "Normal",
  "amd_resident_grade": "None",
  ...
}
```

### Activity Tracking

| Column | Purpose |
|--------|---------|
| `last_grading_activity` | Most recent grading timestamp |

---

## Query Examples

### 1. Encounter-Level Workflow Status

```sql
-- Find encounters with incomplete DR grading
SELECT
    encounter_id,
    patient_identifier,
    total_images,
    dr_task_count,
    pending_tasks,
    resident_done_tasks,
    arbitration_tasks
FROM mvw_encounter_pivot
WHERE dr_task_count > 0
    AND final_tasks < dr_task_count
ORDER BY capture_date DESC;
```

### 2. Multi-Disease Cohort Extraction

```sql
-- Find patients graded for both DR and Glaucoma with specific criteria
SELECT
    encounter_id,
    patient_identifier,
    dr_result,
    glaucoma_vcdr_right_num,
    glaucoma_qualitative_result
FROM mvw_encounter_pivot
WHERE dr_task_count > 0
    AND glaucoma_task_count > 0
    AND dr_result = 'Refer'
    AND glaucoma_vcdr_right_num > 0.7
ORDER BY capture_date DESC;
```

### 3. Hospital Workload Summary

```sql
-- Daily workload by hospital
SELECT
    hospital_name,
    DATE(capture_date) as date,
    COUNT(*) as encounters,
    SUM(total_images) as images,
    SUM(dr_task_count) as dr_tasks,
    SUM(glaucoma_task_count) as glaucoma_tasks,
    SUM(final_tasks) as completed_tasks
FROM mvw_encounter_pivot
WHERE capture_date >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY hospital_name, DATE(capture_date)
ORDER BY date DESC, encounters DESC;
```

---

## Refresh

**Schedule:** 4 times daily (07:00, 13:30, 19:00, 01:30 IST)

**Manual refresh:**
```sql
SELECT refresh_encounter_pivot();
-- or
REFRESH MATERIALIZED VIEW CONCURRENTLY mvw_encounter_pivot;
```

**View size:** ~500 bytes per encounter

---

## Related

- **Migration:** `/migrations/versions/1ea459b0d658_create_encounter_pivot_materialized_.py`
- **Scheduler:** `/utils/materialized_view_scheduler.py`
- **Detailed User Guide:** `/docs/11-KPI and DFs/06-Encounter-Pivot-View-User-Guide.md`
- **Reference:** `/docs/05-Analytics/Materialized_Views_Reference.md`

---

**Last Updated:** January 16, 2026
