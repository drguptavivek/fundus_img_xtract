# TODO: Create Age-related Macular Degeneration (AMD) Grading Pivot Materialized View

## Overview
Create a specialized PostgreSQL **materialized view** that pivots Age-related Macular Degeneration grading data into columns for each grader type, with comprehensive feature tracking and grade IDs for advanced analytics, following the same pattern as the DR and glaucoma materialized views.

## Implementation Steps

### 1. Create Alembic Migration File
- [x] Generate new migration using `uv run alembic revision -m "create_amd_grading_pivot_view"`
- [x] Created migration file skeleton in `migrations/versions/cd23f993eaf2_create_amd_grading_pivot_view.py`

### 2. Update Migration File with SQL Code
- [x] **In the `upgrade()` function:**
  - [x] Create materialized view `mvw_amd_grading_pivot`
  - [x] JOIN both image sources (DirectImageUpload & EncounterFile)
  - [x] Filter specifically for Age-related Macular Degeneration diseases
  - [x] Pivoted grade columns for each role slot
  - [x] Include grade primary keys for direct access
  - [x] Include selected features JSON for each grader
  - [x] Add comprehensive metadata and context
  - [x] Create performance indexes including GIN for JSON

- [x] **In the `downgrade()` function:**
  - [x] Drop all indexes in proper order
  - [x] Drop refresh function
  - [x] Drop materialized view

### 3. Materialized View Structure (✅ COMPLETED)
**Pivoted column format for AMD-specific analysis:**

#### **Image Identification & Context**
- `image_source`, `image_id`, `image_uuid`, `filename`, `eye_side`
- `patient_encounter_id`, `patient_encounter_name`, `patient_identifier`
- `hospital_name`, `lab_unit_name`, `camera_name`
- `capture_date`, `disease_name`

#### **Pivoted Grade Data with IDs and Features**
- **Resident Grade:** `resident_grade_id`, `resident_grade`, `resident_grader`, `resident_grade_time`, `resident_comment`, `resident_features`
- **Resident2 Grade:** `resident2_grade_id`, `resident2_grade`, `resident2_grader`, `resident2_grade_time`, `resident2_comment`, `resident2_features`
- **Arbitrator Grade:** `arbitrator_grade_id`, `arbitrator_grade`, `arbitrator_grader`, `arbitrator_grade_time`, `arbitrator_comment`, `arbitrator_features`
- **Review Grade:** `review_grade_id`, `review_grade`, `reviewer_name`, `review_grade_time`, `review_comment`, `review_features`
- **AI Model Grades:** `aimodel_1_grade_id`, `aimodel_1_grade`, `aimodel_1_name`, `aimodel_1_time`, `aimodel_1_features` (plus aimodel_2, aimodel_3)
- **Consensus:** `consensus_grade`, `consensus_method`, `consensus_decider`, `consensus_time`

#### **Task Metadata**
- `task_id`, `task_uuid`, `task_state`, `task_created_at`, `last_updated`

### 4. Features Structure (✅ IMPLEMENTED)
**JSON format for selected features:**
```json
[
  {
    "id": 1,
    "label": "Drusen",
    "sr_no": 1
  },
  {
    "id": 2,
    "label": "Geographic Atrophy",
    "sr_no": 2
  },
  {
    "id": 3,
    "label": "Neovascular AMD",
    "sr_no": 3
  }
]
```

**Features included for each grader:**
- `resident_features` - Features selected by resident ophthalmologist
- `resident2_features` - Features selected by resident2 ophthalmologist
- `arbitrator_features` - Features selected by arbitrator
- `review_features` - Features selected by reviewer
- `aimodel_1_features`, `aimodel_2_features`, `aimodel_3_features` - AI model feature selections

### 5. Performance Indexes (✅ COMPLETED)
- [x] **Grade ID Indexes:** Direct access by primary keys (resident_grade_id, resident2_grade_id, etc.)
- [x] **Grade Value Indexes:** Analysis by grading outcomes (resident_grade, consensus_grade, etc.)
- [x] **Feature JSON Indexes:** GIN indexes for efficient feature querying
- [x] **Time-based Indexes:** Trending analysis (task_created_at, consensus_time)
- [x] **Grader Analysis Indexes:** By grader username and roles
- [x] **Context Indexes:** Hospital, lab unit, disease filtering

### 6. Refresh Strategy (✅ COMPLETED)
- [x] Create refresh function: `refresh_amd_grading_pivot()`
- [x] Manual refresh capability: `SELECT refresh_amd_grading_pivot();`

### 7. Apply Migration (✅ COMPLETED)
- [x] Run migration: `docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run alembic upgrade head`
- [x] Validate creation and refresh functionality

### 8. Update APS Scheduler (✅ COMPLETED)
- [x] Added AMD view to materialized view scheduler refresh sequence
- [x] Updated scheduler documentation to include AMD view
- [x] Tested multi-view refresh with all four views

## Key Features Implemented

### **Wide-Format Analysis Ready**
- Each row represents one image with all grading data in columns
- Perfect for statistical analysis, machine learning, and reporting
- Direct comparison between different grader types

### **Comprehensive Feature Tracking**
- Complete JSON feature selections preserved per grader
- Enables feature correlation studies and grader pattern analysis
- Historical tracking of feature-based decision making

### **Direct Grade Access**
- Grade primary keys included for precise record access
- Enables linking back to original grade records
- Supports detailed audit trails and data validation

### **AMD-Specific Filtering**
- Filters for both "amd" and "macular degeneration" disease names
- Optimized for AMD workflow analysis and research
- Clean separation from other disease categories

### **High Performance Design**
- 25+ specialized indexes for different query patterns
- JSON GIN indexes for efficient feature searching
- Optimized for both OLAP and analytical workloads

## Usage Examples

### **Feature Analysis Queries**
```sql
-- Find images where resident selected "Drusen"
SELECT image_uuid, resident_grade, resident_features
FROM mvw_amd_grading_pivot
WHERE resident_features::jsonb @> '[{"label": "Drusen"}]';

-- Compare feature selections between resident and arbitrator
SELECT image_uuid, resident_grade, arbitrator_grade,
       resident_features, arbitrator_features
FROM mvw_amd_grading_pivot
WHERE resident_features != arbitrator_features;
```

### **Grader Comparison Analysis**
```sql
-- Analyze agreement between resident and resident2
SELECT resident_grade, resident2_grade, COUNT(*) as count
FROM mvw_amd_grading_pivot
WHERE resident_grade IS NOT NULL AND resident2_grade IS NOT NULL
GROUP BY resident_grade, resident2_grade;

-- Find cases requiring arbitration
SELECT image_uuid, resident_grade, resident2_grade, arbitrator_grade
FROM mvw_amd_grading_pivot
WHERE resident_grade != resident2_grade AND arbitrator_grade IS NOT NULL;
```

### **Time-Based Trending**
```sql
-- Daily grading volume trends
SELECT DATE(task_created_at) as date, COUNT(*) as gradings
FROM mvw_amd_grading_pivot
GROUP BY DATE(task_created_at)
ORDER BY date;
```

## Integration Points

### **Admin Dashboard Integration**
- Can be used for AMD-specific analytics and reporting
- Feature selection analysis dashboard
- Grader performance monitoring for AMD workflows

### **Research and Analysis**
- Perfect dataset for AMD research studies
- Feature correlation with AMD severity levels
- Grader consistency and reliability studies

### **Quality Assurance**
- Identify grading patterns requiring review
- Monitor feature selection consistency
- Track arbitration rates and outcomes

## Reference Implementation

### **Pattern Based on DR and Glaucoma Materialized Views**
This implementation follows the exact same pattern as `mvw_diabetic_retinopathy_grading_pivot` and `mvw_glaucoma_grading_pivot` with these modifications:

1. **Disease Filter:**
   ```sql
   -- AMD-specific filtering
   JOIN diseases d ON gt.disease_id = d.id AND (d.name ILIKE '%amd%' OR d.name ILIKE '%macular degeneration%')
   ```

2. **View Name:**
   - `mvw_amd_grading_pivot` instead of disease-specific names

3. **Function Name:**
   - `refresh_amd_grading_pivot()` instead of disease-specific functions

4. **Index Names:**
   - Use `idx_mvw_amd_*` prefix instead of disease-specific prefixes

## Current Status: ✅ COMPLETE IMPLEMENTATION

### **🎉 AMD Grading Pivot Materialized View Fully Implemented**

#### **Core Features**
- ✅ **Pivoted Column Format:** Each grader type in separate columns
- ✅ **Grade ID Tracking:** Primary keys for direct record access
- ✅ **Feature JSON Storage:** Complete feature selections per grader
- ✅ **AMD-Specific Filtering:** Multiple disease name patterns for comprehensive AMD coverage
- ✅ **High Performance:** 25+ specialized indexes including GIN for JSON

#### **Advanced Capabilities**
- ✅ **Feature Analysis:** Query and analyze selected features per grader
- ✅ **Grader Comparison:** Direct comparison between different grading roles
- ✅ **Temporal Analysis:** Time-based trending and pattern analysis
- ✅ **Audit Trail:** Complete traceability with grade IDs and timestamps

#### **Data Structure**
- ✅ **Wide Format:** Ready for statistical analysis and ML pipelines
- ✅ **Context Rich:** Complete patient, hospital, and encounter metadata
- ✅ **Historical:** Preserves exact state of grading decisions and features
- ✅ **Extensible:** Supports up to 3 AI models with grade tracking

#### **Performance Features**
- ✅ **Optimized Queries:** Specialized indexes for all access patterns
- ✅ **JSON GIN Indexes:** Efficient feature searching and filtering
- ✅ **Refresh Capability:** Integrated with automated scheduler
- ✅ **Scalable:** Designed for large dataset analysis

#### **Scheduler Integration**
- ✅ **Multi-View Support:** Integrated into existing APS scheduler
- ✅ **Automated Refresh:** 4x daily refresh with comprehensive logging
- ✅ **Fault Tolerance:** Continues if individual views fail
- ✅ **Performance Monitoring:** Per-view timing and success tracking

## Enhanced Materialized View Ecosystem

### **Complete Disease-Specific Coverage:**
1. ✅ **General View:** `mvw_grading_data_all` - All disease grading data
2. ✅ **DR Pivot:** `mvw_diabetic_retinopathy_grading_pivot` - DR-specific pivoted analysis
3. ✅ **Glaucoma Pivot:** `mvw_glaucoma_grading_pivot` - Glaucoma-specific pivoted analysis
4. ✅ **AMD Pivot:** `mvw_amd_grading_pivot` - AMD-specific pivoted analysis

### **Unified Scheduler Management:**
- **Single APS Scheduler:** Handles all four views in sequence
- **Comprehensive Logging:** Per-view timing and success tracking
- **Robust Error Handling:** Continues on individual view failures
- **Automated Monitoring:** 4x daily refresh with detailed status reporting

The AMD pivot materialized view provides a comprehensive foundation for Age-related Macular Degeneration grading analytics, research, and quality assurance workflows, completing the disease-specific materialized view ecosystem!