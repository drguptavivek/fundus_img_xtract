# TODO: Create Diabetic Retinopathy Grading Pivot Materialized View

## Overview
Create a specialized PostgreSQL **materialized view** that pivots Diabetic Retinopathy grading data into columns for each grader type, with comprehensive feature tracking and grade IDs for advanced analytics.

## Implementation Steps

### 1. Create Alembic Migration File
- [x] Generate new migration using `uv run alembic revision -m "create_diabetic_retinopathy_grading_pivot_view"`
- [x] Created migration file skeleton in `migrations/versions/cee197bc69ef_create_diabetic_retinopathy_grading_.py`

### 2. Update Migration File with SQL Code
- [x] **In the `upgrade()` function:**
  - [x] Create materialized view `mvw_diabetic_retinopathy_grading_pivot`
  - [x] JOIN both image sources (DirectImageUpload & EncounterFile)
  - [x] Filter specifically for Diabetic Retinopathy diseases
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
**Pivoted column format for DR-specific analysis:**

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
    "label": "Hard Exudates",
    "sr_no": 1
  },
  {
    "id": 2,
    "label": "Cotton Wool Spots",
    "sr_no": 2
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
- [x] Create refresh function: `refresh_diabetic_retinopathy_grading_pivot()`
- [x] Manual refresh capability: `SELECT refresh_diabetic_retinopathy_grading_pivot();`

### 7. Apply Migration (✅ COMPLETED)
- [x] Run migration: `docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run alembic upgrade head`
- [x] Validate creation and refresh functionality

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

### **DR-Specific Filtering**
- Only includes Diabetic Retinopathy related grading tasks
- Optimized for DR workflow analysis and research
- Clean separation from other disease categories

### **High Performance Design**
- 25+ specialized indexes for different query patterns
- JSON GIN indexes for efficient feature searching
- Optimized for both OLAP and analytical workloads

## Usage Examples

### **Feature Analysis Queries**
```sql
-- Find images where resident selected "Hard Exudates"
SELECT image_uuid, resident_grade, resident_features
FROM mvw_diabetic_retinopathy_grading_pivot
WHERE resident_features @> '[{"label": "Hard Exudates"}]';

-- Compare feature selections between resident and arbitrator
SELECT image_uuid, resident_grade, arbitrator_grade,
       resident_features, arbitrator_features
FROM mvw_diabetic_retinopathy_grading_pivot
WHERE resident_features != arbitrator_features;
```

### **Grader Comparison Analysis**
```sql
-- Analyze agreement between resident and resident2
SELECT resident_grade, resident2_grade, COUNT(*) as count
FROM mvw_diabetic_retinopathy_grading_pivot
WHERE resident_grade IS NOT NULL AND resident2_grade IS NOT NULL
GROUP BY resident_grade, resident2_grade;

-- Find cases requiring arbitration
SELECT image_uuid, resident_grade, resident2_grade, arbitrator_grade
FROM mvw_diabetic_retinopathy_grading_pivot
WHERE resident_grade != resident2_grade AND arbitrator_grade IS NOT NULL;
```

### **Time-Based Trending**
```sql
-- Daily grading volume trends
SELECT DATE(task_created_at) as date, COUNT(*) as gradings
FROM mvw_diabetic_retinopathy_grading_pivot
GROUP BY DATE(task_created_at)
ORDER BY date;
```

## Integration Points

### **Admin Dashboard Integration**
- Can be used for DR-specific analytics and reporting
- Feature selection analysis dashboard
- Grader performance monitoring for DR workflows

### **Research and Analysis**
- Perfect dataset for DR research studies
- Feature correlation with DR severity levels
- Grader consistency and reliability studies

### **Quality Assurance**
- Identify grading patterns requiring review
- Monitor feature selection consistency
- Track arbitration rates and outcomes

## Final Status: ✅ COMPLETE IMPLEMENTATION

### **🎉 Diabetic Retinopathy Pivot Materialized View Fully Implemented**

#### **Core Features**
- ✅ **Pivoted Column Format:** Each grader type in separate columns
- ✅ **Grade ID Tracking:** Primary keys for direct record access
- ✅ **Feature JSON Storage:** Complete feature selections per grader
- ✅ **DR-Specific Filtering:** Only Diabetic Retinopathy data
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
- ✅ **Refresh Capability:** Manual and automated refresh support
- ✅ **Scalable:** Designed for large dataset analysis

The DR pivot materialized view provides a comprehensive foundation for Diabetic Retinopathy grading analytics, research, and quality assurance workflows.