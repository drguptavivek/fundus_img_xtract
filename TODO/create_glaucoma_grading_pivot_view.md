# TODO: Create Glaucoma Grading Pivot Materialized View

## Overview
Create a specialized PostgreSQL **materialized view** that pivots Glaucoma grading data into columns for each grader type, with comprehensive feature tracking and grade IDs for advanced analytics, following the same pattern as the DR materialized view.

## Implementation Steps

### 1. Create Alembic Migration File
- [ ] Generate new migration using `uv run alembic revision -m "create_glaucoma_grading_pivot_view"`
- [ ] This will create the migration file skeleton in `migrations/versions/`

### 2. Update Migration File with SQL Code
- [ ] **In the `upgrade()` function:**
  - [ ] Create materialized view `mvw_glaucoma_grading_pivot`
  - [ ] JOIN both image sources (DirectImageUpload & EncounterFile)
  - [ ] Filter specifically for Glaucoma diseases
  - [ ] Pivoted grade columns for each role slot
  - [ ] Include grade primary keys for direct access
  - [ ] Include selected features JSON for each grader
  - [ ] Add comprehensive metadata and context
  - [ ] Create performance indexes including GIN for JSON

- [ ] **In the `downgrade()` function:**
  - [ ] Drop all indexes in proper order
  - [ ] Drop refresh function
  - [ ] Drop materialized view

### 3. Materialized View Structure (🔄 TO BE IMPLEMENTED)
**Pivoted column format for Glaucoma-specific analysis:**

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

### 4. Features Structure (📋 PLANNED)
**JSON format for selected features:**
```json
[
  {
    "id": 1,
    "label": "Optic Disc Cupping",
    "sr_no": 1
  },
  {
    "id": 2,
    "label": "Retinal Nerve Fiber Layer Loss",
    "sr_no": 2
  }
]
```

**Features to include for each grader:**
- `resident_features` - Features selected by resident ophthalmologist
- `resident2_features` - Features selected by resident2 ophthalmologist
- `arbitrator_features` - Features selected by arbitrator
- `review_features` - Features selected by reviewer
- `aimodel_1_features`, `aimodel_2_features`, `aimodel_3_features` - AI model feature selections

### 5. Performance Indexes (📋 PLANNED)
- [ ] **Grade ID Indexes:** Direct access by primary keys (resident_grade_id, resident2_grade_id, etc.)
- [ ] **Grade Value Indexes:** Analysis by grading outcomes (resident_grade, consensus_grade, etc.)
- [ ] **Feature JSON Indexes:** GIN indexes for efficient feature querying
- [ ] **Time-based Indexes:** Trending analysis (task_created_at, consensus_time)
- [ ] **Grader Analysis Indexes:** By grader username and roles
- [ ] **Context Indexes:** Hospital, lab unit, disease filtering

### 6. Refresh Strategy (📋 PLANNED)
- [ ] Create refresh function: `refresh_glaucoma_grading_pivot()`
- [ ] Manual refresh capability: `SELECT refresh_glaucoma_grading_pivot();`

### 7. Apply Migration (📋 PLANNED)
- [ ] Run migration: `docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run alembic upgrade head`
- [ ] Validate creation and refresh functionality

## Key Features to Implement

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

### **Glaucoma-Specific Filtering**
- Only includes Glaucoma related grading tasks
- Optimized for glaucoma workflow analysis and research
- Clean separation from other disease categories

### **High Performance Design**
- 25+ specialized indexes for different query patterns
- JSON GIN indexes for efficient feature searching
- Optimized for both OLAP and analytical workloads

## Planned Usage Examples

### **Feature Analysis Queries**
```sql
-- Find images where resident selected "Optic Disc Cupping"
SELECT image_uuid, resident_grade, resident_features
FROM mvw_glaucoma_grading_pivot
WHERE resident_features @> '[{"label": "Optic Disc Cupping"}]';

-- Compare feature selections between resident and arbitrator
SELECT image_uuid, resident_grade, arbitrator_grade,
       resident_features, arbitrator_features
FROM mvw_glaucoma_grading_pivot
WHERE resident_features != arbitrator_features;
```

### **Grader Comparison Analysis**
```sql
-- Analyze agreement between resident and resident2
SELECT resident_grade, resident2_grade, COUNT(*) as count
FROM mvw_glaucoma_grading_pivot
WHERE resident_grade IS NOT NULL AND resident2_grade IS NOT NULL
GROUP BY resident_grade, resident2_grade;

-- Find cases requiring arbitration
SELECT image_uuid, resident_grade, resident2_grade, arbitrator_grade
FROM mvw_glaucoma_grading_pivot
WHERE resident_grade != resident2_grade AND arbitrator_grade IS NOT NULL;
```

### **Time-Based Trending**
```sql
-- Daily grading volume trends
SELECT DATE(task_created_at) as date, COUNT(*) as gradings
FROM mvw_glaucoma_grading_pivot
GROUP BY DATE(task_created_at)
ORDER BY date;
```

## Integration Points

### **Admin Dashboard Integration**
- Can be used for glaucoma-specific analytics and reporting
- Feature selection analysis dashboard
- Grader performance monitoring for glaucoma workflows

### **Research and Analysis**
- Perfect dataset for glaucoma research studies
- Feature correlation with glaucoma severity levels
- Grader consistency and reliability studies

### **Quality Assurance**
- Identify grading patterns requiring review
- Monitor feature selection consistency
- Track arbitration rates and outcomes

## Reference Implementation

### **Pattern Based on DR Materialized View**
This implementation should follow the exact same pattern as `mvw_diabetic_retinopathy_grading_pivot` with these modifications:

1. **Disease Filter:**
   ```sql
   -- Change from:
   JOIN diseases d ON gt.disease_id = d.id AND d.name ILIKE '%retinopathy%'
   -- To:
   JOIN diseases d ON gt.disease_id = d.id AND d.name ILIKE '%glaucoma%'
   ```

2. **View Name:**
   - `mvw_glaucoma_grading_pivot` instead of `mvw_diabetic_retinopathy_grading_pivot`

3. **Function Name:**
   - `refresh_glaucoma_grading_pivot()` instead of `refresh_diabetic_retinopathy_grading_pivot()`

4. **Index Names:**
   - Use `idx_mvw_glaucoma_*` prefix instead of `idx_mvw_dr_*`

### 6. Apply Migration (✅ COMPLETED)
- [x] Run migration: `docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run alembic upgrade head`
- [x] Validate creation and refresh functionality

### 7. Test Functionality (✅ COMPLETED)
- [x] Materialized view created successfully
- [x] Refresh function working: `SELECT refresh_glaucoma_grading_pivot();`
- [x] 0 rows as expected (no glaucoma data yet)

## Current Status: ✅ COMPLETE IMPLEMENTATION

### **🎉 Glaucoma Grading Pivot Materialized View Fully Implemented**

### **Dependencies:**
- ✅ DR materialized view implementation complete (provides reference pattern)
- ✅ Database structure analysis complete
- ✅ Feature storage format understood
- [ ] Glaucoma disease data availability in database

### **Expected Timeline:**
- Migration creation: 30 minutes
- Implementation and testing: 1 hour
- Documentation and validation: 30 minutes

## Final Status: 📋 READY FOR IMPLEMENTATION

The glaucoma grading pivot materialized view is planned for implementation following the exact same architectural pattern as the successful DR materialized view, with disease-specific filtering and comprehensive feature tracking capabilities.