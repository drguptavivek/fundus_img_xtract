# Encounter Pivot Materialized View - User Guide

## 🎯 Overview

The `mvw_encounter_pivot` materialized view is a powerful analytics resource that consolidates all encounter-level data into a single, optimized row per patient encounter. It provides comprehensive disease-specific image grade pivots and is designed for both research analytics and operational reporting.

## 📋 Table of Contents

1. [Quick Start](#quick-start)
2. [View Structure](#view-structure)
3. [Query Examples](#query-examples)
4. [Advanced JSON Queries](#advanced-json-queries)
5. [Performance Tips](#performance-tips)
6. [Common Use Cases](#common-use-cases)
7. [Maintenance](#maintenance)

---

## 🚀 Quick Start

### Basic Usage

```sql
-- Get all encounters with their basic information
SELECT
    encounter_id,
    encounter_name,
    patient_identifier,
    total_images,
    dr_task_count,
    glaucoma_task_count,
    amd_task_count,
    capture_date
FROM mvw_encounter_pivot
ORDER BY encounter_id DESC
LIMIT 10;
```

### Disease-Specific Analysis

```sql
-- Analyze DR-specific task distribution
SELECT
    hospital_name,
    COUNT(*) as total_encounters,
    SUM(dr_task_count) as total_dr_tasks,
    AVG(dr_task_count) as avg_dr_tasks_per_encounter
FROM mvw_encounter_pivot
WHERE dr_task_count > 0
GROUP BY hospital_name;
```

---

## 📊 View Structure

### Core Columns

| Column | Type | Description |
|--------|------|-------------|
| `encounter_id` | INTEGER | Primary encounter identifier |
| `encounter_name` | VARCHAR | Encounter display name |
| `patient_identifier` | VARCHAR | Patient ID/number |
| `total_images` | INTEGER | Number of images in encounter |
| `capture_date` | TIMESTAMP | Encounter capture date |
| `hospital_id` | INTEGER | Hospital identifier |
| `hospital_name` | VARCHAR | Hospital name |
| `lab_unit_id` | INTEGER | Lab unit identifier |
| `lab_unit_name` | VARCHAR | Lab unit name |

### Disease Task Counts

| Column | Type | Description |
|--------|------|-------------|
| `dr_task_count` | INTEGER | Number of DR grading tasks |
| `glaucoma_task_count` | INTEGER | Number of Glaucoma grading tasks |
| `amd_task_count` | INTEGER | Number of AMD grading tasks |
| `additional_disease_task_count` | INTEGER | Tasks for other diseases |
| `total_task_count` | INTEGER | Total number of all tasks |

### Disease-Specific Image Grade Pivots

#### `dr_image_grades` (JSON Array)
Each object contains:
```json
{
  "image_id": 102,
  "image_uuid": "1f493f71-54aa-4459-aa4f-0216b8b9161e",
  "eye_side": "left",
  "file_type": "image",
  "resident_grade": "Mild NPDR",
  "resident2_grade": "Moderate NPDR",
  "arbitrator_grade": "Mild NPDR",
  "ai_grade": "Moderate NPDR",
  "review_grade": "Mild NPDR",
  "consensus_grade": "Mild NPDR"
}
```

#### `glaucoma_image_grades` (JSON Array)
Same structure as DR but with glaucoma-specific grades.

#### `amd_image_grades` (JSON Array)
Same structure but with AMD-specific grades.

#### `additional_disease_image_grades` (JSON Array)
For any other diseases with additional `disease_name` field:
```json
{
  "image_id": 105,
  "disease_name": "Retinal Detachment",
  "resident_grade": "Attached",
  "consensus_grade": "Attached"
}
```

### Disease Report Information

| Column | Type | Description |
|--------|------|-------------|
| `dr_result` | VARCHAR | DR report result |
| `dr_qualitative_result` | VARCHAR | DR qualitative result |
| `glaucoma_result` | VARCHAR | Glaucoma result |
| `glaucoma_qualitative_result` | VARCHAR | Glaucoma qualitative result |
| `glaucoma_vcdr_right_num` | NUMERIC | Right eye VCDR value |
| `glaucoma_vcdr_left_num` | NUMERIC | Left eye VCDR value |

---

## 🔍 Query Examples

### Basic Analytics

```sql
-- 1. Find encounters with specific disease combinations
SELECT
    encounter_id,
    capture_date,
    dr_task_count,
    glaucoma_task_count,
    total_images
FROM mvw_encounter_pivot
WHERE dr_task_count > 0
    AND glaucoma_task_count > 0
    AND total_images > 0
ORDER BY capture_date DESC;

-- 2. Hospital workload analysis
SELECT
    hospital_name,
    COUNT(*) as encounter_count,
    SUM(dr_task_count) as dr_workload,
    SUM(glaucoma_task_count) as glaucoma_workload,
    SUM(total_task_count) as total_workload,
    AVG(total_images) as avg_images_per_encounter
FROM mvw_encounter_pivot
GROUP BY hospital_name
ORDER BY total_workload DESC;

-- 3. Verification status completeness
SELECT
    COUNT(*) as total_encounters,
    COUNT(CASE WHEN dr_verified_status = 'verified' THEN 1 END) as dr_verified,
    COUNT(CASE WHEN glaucoma_verified_status = 'verified' THEN 1 END) as glaucoma_verified,
    COUNT(CASE WHEN encounter_verified_status = 'verified' THEN 1 END) as fully_verified
FROM mvw_encounter_pivot;
```

### Advanced Research Queries

```sql
-- 4. Find encounters with AI vs human grade disagreements
SELECT
    encounter_id,
    patient_identifier,
    dr_image_grades,
    glaucoma_image_grades
FROM mvw_encounter_pivot
WHERE dr_image_grades::jsonb @> '[{"ai_grade": "Severe NPDR", "consensus_grade": "Mild NPDR"}]'
   OR glaucoma_image_grades::jsonb @> '[{"ai_grade": "Glaucoma", "consensus_grade": "Normal"}]';

-- 5. VCDR analysis for glaucoma screening
SELECT
    encounter_id,
    glaucoma_vcdr_right_num,
    glaucoma_vcdr_left_num,
    glaucoma_result,
    glaucoma_qualitative_result
FROM mvw_encounter_pivot
WHERE glaucoma_vcdr_right_num IS NOT NULL
    OR glaucoma_vcdr_left_num IS NOT NULL
ORDER BY glaucoma_vcdr_right_num DESC;

-- 6. Cross-disease correlation analysis
SELECT
    COUNT(*) as encounter_count,
    AVG(CASE WHEN dr_task_count > 0 AND glaucoma_task_count > 0 THEN total_task_count ELSE 0 END) as avg_dual_disease_tasks,
    COUNT(CASE WHEN dr_task_count = glaucoma_task_count AND dr_task_count > 0 THEN 1 END) as matching_task_counts
FROM mvw_encounter_pivot
GROUP BY (CASE WHEN total_task_count > 0 THEN 'has_tasks' ELSE 'no_tasks' END);
```

### Time-Based Analysis

```sql
-- 7. Monthly workload trends
SELECT
    DATE_TRUNC('month', capture_date) as month,
    COUNT(*) as encounters_created,
    SUM(total_images) as total_images_processed,
    SUM(dr_task_count) as dr_tasks_created,
    SUM(glaucoma_task_count) as glaucoma_tasks_created
FROM mvw_encounter_pivot
WHERE capture_date >= NOW() - INTERVAL '6 months'
GROUP BY DATE_TRUNC('month', capture_date)
ORDER BY month DESC;

-- 8. Recent activity analysis
SELECT
    encounter_id,
    capture_date,
    total_task_count,
    last_task_activity_at
FROM mvw_encounter_pivot
WHERE last_task_activity_at >= NOW() - INTERVAL '7 days'
ORDER BY last_task_activity_at DESC;
```

---

## 🎯 Advanced JSON Queries

### Working with Disease-Specific JSON Arrays

```sql
-- Extract individual image grades from DR pivot
SELECT
    encounter_id,
    image_data->>'image_uuid' as image_uuid,
    image_data->>'eye_side' as eye_side,
    image_data->>'resident_grade' as dr_resident_grade,
    image_data->>'arbitrator_grade' as dr_arbitrator_grade,
    image_data->>'consensus_grade' as dr_consensus_grade
FROM mvw_encounter_pivot,
     jsonb_array_elements(dr_image_grades) as image_data
WHERE encounter_id = 46;

-- Count images with specific grade combinations
SELECT
    encounter_id,
    COUNT(*) as total_images,
    COUNT(CASE WHEN image_data->>'resident_grade' = image_data->>'consensus_grade' THEN 1 END) as matching_grades
FROM mvw_encounter_pivot,
     jsonb_array_elements(dr_image_grades) as image_data
WHERE encounter_id IN (46, 47, 48)
GROUP BY encounter_id;
```

### Complex Feature Analysis

```sql
-- Find encounters with incomplete grading
SELECT
    encounter_id,
    total_images,
    jsonb_array_length(dr_image_grades) as dr_image_count,
    jsonb_array_length(glaucoma_image_grades) as glaucoma_image_count,
    dr_task_count,
    glaucoma_task_count
FROM mvw_encounter_pivot
WHERE (dr_task_count > 0 AND jsonb_array_length(dr_image_grades) = 0)
    OR (glaucoma_task_count > 0 AND jsonb_array_length(glaucoma_image_grades) = 0);

-- Analyze grade severity distribution
SELECT
    image_data->>'resident_grade' as dr_grade,
    COUNT(*) as image_count
FROM mvw_encounter_pivot,
     jsonb_array_elements(dr_image_grades) as image_data
WHERE image_data->>'resident_grade' IS NOT NULL
GROUP BY image_data->>'resident_grade'
ORDER BY image_count DESC;
```

---

## ⚡ Performance Tips

### 1. Use Specific Indexes

The view includes optimized indexes. Always use indexed columns in WHERE clauses:

```sql
-- ✅ Fast - uses indexes
SELECT * FROM mvw_encounter_pivot
WHERE hospital_id = 1 AND dr_task_count > 0;

-- ❌ Slow - JSON operations can be expensive
SELECT * FROM mvw_encounter_pivot
WHERE dr_image_grades @> '[{"resident_grade": "Severe NPDR"}]';
```

### 2. Limit JSON Queries

```sql
-- ✅ Efficient - limits JSON operations first
SELECT encounter_id, dr_image_grades
FROM mvw_encounter_pivot
WHERE encounter_id = 46
LIMIT 1;

-- ❌ Less efficient - processes all encounters
SELECT encounter_id, dr_image_grades
FROM mvw_encounter_pivot;
```

### 3. Use GIN Indexes for JSON Queries

```sql
-- ✅ Uses GIN index for JSON containment
SELECT * FROM mvw_encounter_pivot
WHERE dr_image_grades::jsonb @> '[{"resident_grade": "Mild NPDR"}]';

-- ✅ Uses index for array length
SELECT * FROM mvw_encounter_pivot
WHERE jsonb_array_length(dr_image_grades) > 2;
```

---

## 🎨 Common Use Cases

### 1. Clinical Research

```sql
-- Find encounters with specific grade combinations
SELECT
    encounter_id,
    patient_identifier,
    dr_image_grades,
    glaucoma_image_grades,
    dr_result,
    glaucoma_vcdr_right_num
FROM mvw_encounter_pivot
WHERE dr_result = 'Refer'
    AND glaucoma_vcdr_right_num > 0.7
ORDER BY capture_date DESC;
```

### 2. Quality Assurance

```sql
-- Check grading completion status
SELECT
    hospital_name,
    COUNT(*) as total_encounters,
    COUNT(CASE WHEN dr_task_count = 0 AND total_images > 0 THEN 1 END) as missing_dr_tasks,
    COUNT(CASE WHEN glaucoma_task_count = 0 AND total_images > 0 THEN 1 END) as missing_glaucoma_tasks,
    AVG(CASE WHEN total_images > 0 THEN dr_task_count / CAST(total_images AS FLOAT) ELSE 0 END) as avg_dr_tasks_per_image
FROM mvw_encounter_pivot
GROUP BY hospital_name
ORDER BY missing_dr_tasks + missing_glaucoma_tasks DESC;
```

### 3. Operational Reporting

```sql
-- Daily workload summary
SELECT
    DATE(capture_date) as report_date,
    COUNT(*) as encounters,
    SUM(total_images) as images_processed,
    SUM(dr_task_count) as dr_tasks_completed,
    SUM(glaucoma_task_count) as glaucoma_tasks_completed,
    SUM(total_task_count) as total_tasks_completed
FROM mvw_encounter_pivot
WHERE capture_date >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY DATE(capture_date)
ORDER BY report_date DESC;
```

### 4. Performance Analysis

```sql
-- Grader efficiency analysis
SELECT
    hospital_name,
    AVG(dr_task_count) as avg_dr_tasks_per_encounter,
    AVG(glaucoma_task_count) as avg_glaucoma_tasks_per_encounter,
    COUNT(CASE WHEN dr_task_count > 0 THEN 1 END) as dr_active_encounters,
    COUNT(CASE WHEN glaucoma_task_count > 0 THEN 1 END) as glaucoma_active_encounters
FROM mvw_encounter_pivot
GROUP BY hospital_name
ORDER BY avg_dr_tasks_per_encounter DESC;
```

---

## 🔧 Maintenance

### Manual Refresh

```sql
-- Refresh the materialized view (admin only)
SELECT refresh_encounter_pivot();
```

### Refresh Schedule

The view automatically refreshes 4 times daily:
- **07:00 IST** (Morning)
- **13:30 IST** (Afternoon)
- **19:00 IST** (Evening)
- **01:30 IST** (Night)

### Monitoring

Check view status via admin interface at `/admin/materialized-view` or query the refresh log:

```sql
-- Check recent refresh history
SELECT
    refresh_type,
    refresh_started_at,
    refresh_completed_at,
    refresh_duration_seconds,
    success,
    error_message
FROM materialized_view_refresh_log
WHERE materialized_view_name = 'mvw_encounter_pivot'
ORDER BY refresh_started_at DESC
LIMIT 10;
```

### Troubleshooting

#### Common Issues:

1. **Stale Data**: The view refreshes automatically, but you can manually refresh if needed
2. **Query Performance**: Use indexed columns and limit JSON operations
3. **Missing Data**: Check that encounters have both images and grading tasks

#### Health Check Query:

```sql
-- Basic health check
SELECT
    COUNT(*) as total_encounters,
    COUNT(CASE WHEN dr_image_grades IS NOT NULL THEN 1 END) as has_dr_data,
    COUNT(CASE WHEN glaucoma_image_grades IS NOT NULL THEN 1 END) as has_glaucoma_data,
    COUNT(CASE WHEN amd_image_grades IS NOT NULL THEN 1 END) as has_amd_data,
    MAX(capture_date) as latest_encounter,
    MIN(capture_date) as earliest_encounter
FROM mvw_encounter_pivot;
```

---

## 📞 Support

For technical support or questions about the encounter pivot view:

1. Check this user guide for common solutions
2. Use the admin interface at `/admin/materialized-view` for monitoring
3. Review the refresh log for any errors
4. Contact the database team for complex query optimization

---

**Last Updated**: November 11, 2025
**Version**: 1.0 - Production Ready