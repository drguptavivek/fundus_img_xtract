# TODO: Create PostgreSQL Materialized View for Grading Data Analytics

## Overview
Create a comprehensive PostgreSQL **materialized view** with proper Alembic migration and indexes to consolidate all grade-related data including consensus grades for both direct and encounter file images.

## Implementation Steps

### 1. Create Alembic Migration File
- [x] Generate new migration using `uv run alembic revision -autogenerate -m "create_grading_data_materialized_view"`
- [x] This will create the migration file skeleton in `migrations/versions/`

### 2. Update Migration File with SQL Code
- [x] **In the `upgrade()` function:**
  - [x] Create materialized view `mvw_grading_data_all`
  - [x] Include all JOINs for both image sources (DirectImageUpload & EncounterFile)
  - [x] Add individual grades (resident, resident2, AI, arbitrator)
  - [x] Add complete consensus grade information
  - [x] Use COALESCE/CASE statements to handle dual image sources
  - [x] Create indexes on the materialized view
  - [x] Include comprehensive metadata (patient encounters, verification status, etc.)

- [x] **In the `downgrade()` function:**
  - [x] Drop the materialized view: `DROP MATERIALIZED VIEW IF EXISTS mvw_grading_data_all`

### 3. Materialized View Structure (✅ COMPLETED)
**Created with enhanced metadata including:**
- Image source unification (direct upload vs encounter file)
- Complete grading workflow data (grades, consensus, AI models)
- Patient encounter metadata (capture dates, verification status)
- Direct image verification information
- Comprehensive indexing for performance
- Uses denormalized data from Grade and Consensus models

**Key features implemented:**
- ✅ 25+ performance indexes
- ✅ Both image sources (DirectImageUpload & EncounterFile)
- ✅ All role slots (resident, resident2, AI, arbitrator)
- ✅ Complete consensus data with method tracking
- ✅ Timezone-aware fields and proper data relationships
- ✅ Refresh function: `refresh_grading_data_view()`

### 4. Create Performance Indexes on Materialized View (✅ COMPLETED)
- [x] Image-related indexes: image_uuid, image_source, image_id
- [x] Grade-related indexes: task_id, grade_id, grader_user, role_slot, disease
- [x] Time-based indexes: task_created_at, grade_created_at, consensus_date
- [x] Consensus-specific indexes: consensus_id, consensus_method
- [x] Enhanced metadata indexes: patient_encounter_id, verification_id, encounter dates

### 5. Refresh Strategy (✅ COMPLETED)
- [x] Add refresh function for automated updates:
  ```sql
  CREATE OR REPLACE FUNCTION refresh_grading_data_view()
  RETURNS void AS $$
  BEGIN
      REFRESH MATERIALIZED VIEW CONCURRENTLY mvw_grading_data_all;
  END;
  $$ LANGUAGE plpgsql;
  ```

### 6. Test & Validate (✅ COMPLETED)
- [x] Run the migration: `uv run alembic upgrade head` (in Docker container)
- [x] Fix JOIN relationship errors during development
- [x] Verify materialized view creation and functionality
- [x] Test refresh functionality: `SELECT refresh_grading_data_view();`
- [x] Commit changes to version control

## Phase 2: Implement Automated Refresh Scheduler

### 7. Add Refresh Scheduler Configuration
- [ ] Add environment variables to `deploy.config.env`:
  ```env
  MATERIALIZED_VIEW_SCHEDULE_ENABLED=true
  MATERIALIZED_VIEW_SCHEDULE_TIMES=07:00,13:30,19:00,01:30
  MATERIALIZED_VIEW_TIMEZONE=Asia/Kolkata
  MATERIALIZED_VIEW_RETRY_ATTEMPTS=3
  MATERIALIZED_VIEW_RETRY_DELAY_SECONDS=60
  ```

### 8. Create Scheduler Service Module
- [ ] Create `utils/materialized_view_scheduler.py`:
  - [ ] Timezone-aware refresh function using existing `get_env()` pattern
  - [ ] Background daemon thread following `run_stuck_task_cleanup()` pattern
  - [ ] Integration with existing logging infrastructure in `app.py`
  - [ ] Proper database session handling using `transaction_scope()`
  - [ ] Retry logic with exponential backoff

### 9. Integrate with Flask Application
- [ ] Add materialized_view logger to `app.py` logging section
- [ ] Load scheduler configuration using existing `get_env()` functions
- [ ] Initialize scheduler daemon thread in `app.py` after stuck task cleanup
- [ ] Use `DEFAULT_DISPLAY_TIMEZONE` environment variable
- [ ] Add graceful shutdown handling

### 10. Admin Interface (Optional)
- [ ] Create manual refresh endpoint in admin routes
- [ ] Add scheduler status monitoring
- [ ] Include timezone-aware schedule display

## Files Created/Modified (Phase 1 ✅ COMPLETED)
- [x] **Migration files**:
  - [x] `migrations/versions/ef304c5f8dd9_create_grading_data_materialized_view.py` (initial)
  - [x] `migrations/versions/c99df7413504_enhance_grading_data_materialized_view_.py` (enhanced)

## Files to Create/Modify (Phase 2 🔄 IN PROGRESS)
- [ ] **Scheduler module**: `utils/materialized_view_scheduler.py`
- [ ] **Environment config**: Add to `deploy.config.env`
- [ ] **Flask integration**: Update `app.py` (logging, config, thread)
- [ ] **Admin routes**: Optional manual refresh endpoints

## Phase 1 Status: ✅ COMPLETED

### Advantages of Materialized View (Implemented)
- ✅ **Better Performance**: Pre-computed complex JOINs with 25+ indexes
- ✅ **Faster Analytics**: Optimized for reporting and data analysis
- ✅ **Reduced Load**: Less strain on database during complex queries
- ✅ **Concurrent Refreshes**: Can refresh without blocking reads
- ✅ **Comprehensive Data**: All grades, consensus, metadata unified

### Expected Outcome (Phase 1 ✅ COMPLETED)
- ✅ High-performance materialized view with all grade and consensus data
- ✅ Optimized for analytics and reporting workloads
- ✅ Properly indexed for fast query performance
- ✅ Manual refresh capability (`refresh_grading_data_view()` function)
- ✅ Comprehensive metadata from multiple tables
- ✅ Both image sources (direct uploads and encounter files)

## Phase 2 Status: 🔄 SCHEDULER IMPLEMENTATION NEEDED

### Next Steps: Automated Refresh Scheduler
**Requirements**: 4x daily refresh at 7:00 AM, 1:30 PM, 7:00 PM, 1:30 AM Asia/Kolkata (all 7 days)

**Key Integration Points**:
- Leverage existing `DEFAULT_DISPLAY_TIMEZONE` environment variable
- Use existing `get_env()` pattern from `utils.env_loader`
- Follow `run_stuck_task_cleanup()` daemon thread pattern
- Integrate with existing logging infrastructure in `app.py`
- Use `transaction_scope()` for proper database session handling

## Dependencies (All ✅ Available)
- ✅ Database models: Grade, GradingTask, Consensus, DirectImageUpload, EncounterFile
- ✅ Reference tables: diseases, users, ai_models, hospitals, cameras, lab_units
- ✅ Existing infrastructure: timezone handling, logging, background tasks, DB sessions

## Current Refresh Frequency
**Status**: Manual only - requires scheduling implementation
**Function**: `refresh_grading_data_view()` available and tested
**Performance**: Non-blocking concurrent refresh implemented