# Materialized Views - Technical Reference

## Overview

The fundus image management system uses six PostgreSQL materialized views to optimize analytics and reporting performance. These views pre-compute complex aggregations across images, grading tasks, and patient encounters, enabling fast query responses for dashboards, KPIs, and data exports.

## Materialized Views Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Materialized Views Layer                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    mvw_encounter_pivot                              │    │
│  │  Encounter-centric analytics with individual image grade pivots     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                   ↓                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    mvw_image_listing_all                            │    │
│  │  Comprehensive image catalog with upload types and verification     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                   ↓                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │         Disease-Specific Grading Pivot Views                        │    │
│  │  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────┐    │    │
│  │  │ DR Grading      │ │ Glaucoma        │ │ AMD Grading         │    │    │
│  │  │ Pivot           │ │ Grading Pivot   │ │ Pivot               │    │    │
│  │  └─────────────────┘ └─────────────────┘ └─────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                   ↓                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    mvw_grading_data_all                             │    │
│  │  General grading data analytics (all diseases, all roles)           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                         Refresh Scheduler                                   │
│  • Configurable schedule (default: every 30 minutes)                        │
│  • Automatic refresh in dependency order                                    │
│  • Manual refresh via admin interface                                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

## View Descriptions

### 1. mvw_encounter_pivot
**Purpose:** Encounter-centric analytics with individual image grade pivots

**Key Features:**
- Aggregates all images and tasks per patient encounter
- Provides JSON arrays of image UUIDs, eye sides, and types
- Contains individual image-grade pivots for all three diseases
- Tracks task counts and status by disease type
- Includes DR and Glaucoma report results

**Use Cases:**
- Encounter-level analytics and reporting
- Multi-disease cohort analysis
- Task workflow monitoring by encounter
- Report generation dashboards

**Migration:** `/migrations/versions/1ea459b0d658_create_encounter_pivot_materialized_.py`

**Documentation:** `Encounter_Pivot_Materialized_View.md`

---

### 2. mvw_image_listing_all
**Purpose:** Comprehensive image catalog with upload types and verification status

**Key Features:**
- Unified view of Direct Upload and ZIP-based images
- Upload type classification (Direct/Pregraded/ZIP)
- Verification status tracking for both upload types
- Task and grading statistics per image
- JSON-formatted grading details for all diseases

**Use Cases:**
- Image inventory management
- Verification workflow tracking
- Cross-upload-type analytics
- Image search and filtering

**Migration:** `/migrations/versions/819e7a97ca1f_create_image_listing_materialized_view.py`

**Documentation:** `Image_Listing_Materialized_View.md`

---

### 3. mvw_diabetic_retinopathy_grading_pivot
**Purpose:** DR-specific grading with pivoted grader columns

**Key Features:**
- Pivoted grade columns (resident, resident2, arbitrator, review)
- Support for up to 3 AI model grades
- Consensus grade with method and decider
- JSONB-indexed feature arrays for analysis

**Use Cases:**
- DR-specific analytics and KPIs
- Grader performance analysis
- AI vs human comparison
- Consensus tracking

**Migration:** `/migrations/versions/cee197bc69ef_create_diabetic_retinopathy_grading_.py`

**Documentation:** `DR_Grading_Pivot_Materialized_View.md`

---

### 4. mvw_glaucoma_grading_pivot
**Purpose:** Glaucoma-specific grading with pivoted grader columns

**Key Features:**
- Same schema as DR pivot (consistent pattern)
- Glaucoma-specific grade references
- VCDR values available via encounter pivot
- Pivoted grader columns for analysis

**Use Cases:**
- Glaucoma grading analytics
- VCDR distribution analysis
- Grader consistency tracking
- Glaucoma report validation

**Migration:** `/migrations/versions/6c48c37fc19a_create_glaucoma_grading_pivot_view.py`

**Documentation:** `Glaucoma_Grading_Pivot_Materialized_View.md`

---

### 5. mvw_amd_grading_pivot
**Purpose:** AMD-specific grading with pivoted grader columns

**Key Features:**
- Same schema as DR/Glaucoma pivots (consistent pattern)
- AMD-specific grade references
- Supports ad-hoc AMD grading tasks
- Pivoted grader columns for analysis

**Use Cases:**
- AMD grading analytics
- AMD cohort analysis
- Grader training assessment
- AMD research dataset curation

**Migration:** `/migrations/versions/cd23f993eaf2_create_amd_grading_pivot_view.py`

**Documentation:** `AMD_Grading_Pivot_Materialized_View.md`

---

### 6. mvw_grading_data_all
**Purpose:** General grading data analytics (all diseases, all roles)

**Key Features:**
- Unified view of all grading data across diseases
- One row per grade (non-pivoted)
- Includes all role slots (resident, resident2, arbitrator, review, ai)
- Complete consensus information
- Image and encounter metadata

**Use Cases:**
- Cross-disease analytics
- Grading workflow analysis
- Export and reporting
- Historical grade tracking

**Migration:** `/migrations/versions/ef304c5f8dd9_create_grading_data_materialized_view.py`

**Documentation:** `Grading_Data_All_Materialized_View.md`

---

## Refresh Mechanism

### Automatic Refresh Scheduler

**File:** `/utils/materialized_view_scheduler.py`

**Default Schedule:** Every 30 minutes (configurable via `MATERIALIZED_VIEW_SCHEDULE_TIMES`)

**Refresh Order (dependency-respecting):**
1. `mvw_grading_data_all` (base grading data)
2. `mvw_diabetic_retinopathy_grading_pivot`
3. `mvw_glaucoma_grading_pivot`
4. `mvw_amd_grading_pivot`
5. `mvw_encounter_pivot`
6. `mvw_image_listing_all`

**Configuration:**
```python
# Environment variables
MATERIALIZED_VIEW_SCHEDULE_ENABLED=True
MATERIALIZED_VIEW_SCHEDULE_TIMES=07:00,13:30,19:00,01:30
MATERIALIZED_VIEW_TIMEZONE=Asia/Kolkata
MATERIALIZED_VIEW_RETRY_ATTEMPTS=3
MATERIALIZED_VIEW_RETRY_DELAY_SECONDS=60
```

### Manual Refresh

**Admin Interface:** `/admin/materialized-view-status`

**Python API:**
```python
from utils.materialized_view_scheduler import manual_refresh_now

result = manual_refresh_now(app)
# Returns: {"success": True/False, "message": "..."}
```

**Individual View Refresh:**
```sql
-- Refresh specific view
REFRESH MATERIALIZED VIEW mvw_encounter_pivot;

-- Concurrent refresh (allows queries during refresh)
REFRESH MATERIALIZED VIEW CONCURRENTLY mvw_encounter_pivot;

-- Via function
SELECT refresh_encounter_pivot();
```

### Refresh Log Table

**Table:** `materialized_view_refresh_log`

**Columns:**
- `id` - Primary key
- `materialized_view_name` - Name of view refreshed
- `refresh_type` - Schedule identifier or 'manual'
- `refresh_started_at` - Start timestamp (UTC)
- `refresh_completed_at` - Completion timestamp (UTC)
- `refresh_duration_seconds` - Total duration
- `success` - Boolean success flag
- `error_message` - Error details if failed
- `created_at` - Record creation
- `updated_at` - Last update

**Migration:** `/migrations/versions/b3ab758d04e3_create_materialized_view_refresh_.py`

---

## Performance Characteristics

### Index Strategy

Each materialized view includes optimized indexes for common query patterns:

1. **Primary Key Indexes** - Unique identifiers
2. **B-tree Indexes** - Equality and range queries
3. **GIN Indexes** - JSON/JSONB column queries
4. **Composite Indexes** - Multi-column query optimization

### Query Performance

Typical query performance (with proper indexes):
- Simple lookups: < 10ms
- Aggregation queries: 50-200ms
- JSON queries: 100-500ms
- Complex joins: 200-1000ms

### Storage Requirements

Approximate storage (varies by data volume):
- `mvw_grading_data_all`: ~100 bytes per grade
- `mvw_encounter_pivot`: ~500 bytes per encounter
- Disease pivot views: ~300 bytes per task
- `mvw_image_listing_all`: ~400 bytes per image

---

## Integration Points

### Routes Using Materialized Views

| Route/File | Views Used | Purpose |
|------------|------------|---------|
| `/public/analytics.py` | All | Dashboard analytics |
| `/analytics/route_model_performance.py` | Pivot views | AI model performance |
| `/api/kpis/direct_files_kpis.py` | Image listing | Direct upload KPIs |
| `/utils/mvw_all_img_search.py` | Image listing | Image search |
| `/review/route_discrepancy_review.py` | All | Discrepancy detection |
| `/review/discrepancy_export.py` | All | Data export |
| `/utils/review_navigation.py` | All | Review workflow |
| `/home.py` | Encounter pivot | Home dashboard |

### Admin Interface

**Route:** `/admin/materialized-view-status`

**Template:** `/templates/admin/materialized_view_status.html`

**JavaScript:** `/static/js/mv-refresh.js`

**Component:** `/templates/components/mv_refresh_button.html`

**File:** `/admin/materialized_view_status.py`

---

## Migration History

### View Creation Timeline

| Date | Migration | View |
|------|-----------|------|
| 2025-11-10 | `ef304c5f8dd9` | mvw_grading_data_all |
| 2025-11-10 | `cee197bc69ef` | mvw_diabetic_retinopathy_grading_pivot |
| 2025-11-09 | `6c48c37fc19a` | mvw_glaucoma_grading_pivot |
| 2025-11-09 | `cd23f993eaf2` | mvw_amd_grading_pivot |
| 2025-11-11 | `1ea459b0d658` | mvw_encounter_pivot |
| 2025-11-12 | `819e7a97ca1f` | mvw_image_listing_all |

### Enhancements

| Date | Migration | Description |
|------|-----------|-------------|
| - | `c99df7413504` | Enhanced grading data view |
| - | `d4d599d7f252` | Fix encounter pivot split image handling |
| - | `bd1d20ea7d83` | Fix disease names in encounter pivot |

---

## Best Practices

### Querying Materialized Views

1. **Always filter on indexed columns** for optimal performance
2. **Use JSON operators** carefully - prefer `@>` for contains
3. **Be aware of data freshness** - check `refresh_completed_at`
4. **Use concurrent refresh** for production to avoid locks

### Monitoring

1. **Check refresh log** for failed refreshes
2. **Monitor query performance** via PostgreSQL `EXPLAIN ANALYZE`
3. **Track view size** - consider partitioning for very large datasets
4. **Review scheduler status** in admin interface

### Maintenance

1. **Regular vacuuming** - Materialized views need VACUUM after updates
2. **Index maintenance** - REINDEX if performance degrades
3. **Schema updates** - Create new migration for view changes
4. **Testing** - Always test refresh in staging first

---

## Troubleshooting

### Common Issues

**Issue:** View returns stale data
- **Solution:** Manual refresh via admin interface or SQL

**Issue:** Refresh takes too long
- **Solution:** Check for long-running queries, use concurrent refresh

**Issue:** Out of memory during refresh
- **Solution:** Increase work_mem in PostgreSQL configuration

**Issue:** Query is slow despite indexes
- **Solution:** Run `EXPLAIN ANALYZE`, check index usage

### Monitoring Queries

```sql
-- Check last refresh time
SELECT * FROM materialized_view_refresh_log
ORDER BY refresh_started_at DESC LIMIT 5;

-- Check view sizes
SELECT schemaname, matviewname, pg_size_pretty(pg_total_relation_size(schemaname||'.'||matviewname))
FROM pg_matviews
WHERE matviewname LIKE 'mvw_%';

-- Check for long-running queries
SELECT pid, now() - query_start as duration, query
FROM pg_stat_activity
WHERE state = 'active'
ORDER BY duration DESC;
```

---

## Related Documentation

- **Dataset Curation:** `Dataset_Curation_Technical_Reference.md`
- **Analytics System:** `../11-KPI and DFs/comprehensive_analytics_reporting_system.md`
- **Scheduler:** `../10-DEVELOP/APScheduler.md`
- **Migrations:** `../alembic-migrations.md`

---

**Last Updated:** January 16, 2026
**Version:** 1.0
**Author:** Technical Documentation Team
