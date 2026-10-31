# Analytics & Reporting System - Comprehensive Guide

## Overview

The Fundus Image Manager implements an advanced analytics and reporting system centered around materialized views for high-performance data analysis. The system provides real-time insights into grading workflows, performance metrics, and quality assurance across all diseases and organizational units.

## Core Architecture

### Materialized Views System

**Four Specialized Materialized Views:**

1. **`mvw_grading_data_all`** - General grading data for all diseases
2. **`mvw_diabetic_retinopathy_grading_pivot`** - DR-specific pivoted analysis
3. **`mvw_glaucoma_grading_pivot`** - Glaucoma-specific pivoted analysis
4. **`mvw_amd_grading_pivot`** - AMD-specific pivoted analysis

**Automated Refresh Schedule:**
- **4x daily refreshes** at 07:00, 13:30, 19:00, 01:30 IST
- **Manual refresh capability** via admin interface
- **Comprehensive logging** of all refresh operations
- **Performance optimization** with 25+ indexes per view

### Materialized View Details

#### 1. General Grading Data View (`mvw_grading_data_all`)

**Purpose:** Comprehensive grading analytics across all diseases

**Key Features:**
- Complete task and grade information
- Grader performance metrics
- Task completion statistics
- Cross-disease analytics

**Schema Highlights:**
```sql
-- Key columns include:
- task_id, disease_name, lab_unit_name
- resident_grade_id, resident2_grade_id, arbitrator_grade_id
- task_state, created_at, updated_at
- grader information and timing data
- Feature selections (JSON with GIN indexing)
```

#### 2. Disease-Specific Pivot Views

**DR Pivot View (`mvw_diabetic_retinopathy_grading_pivot`):**
- Pivoted format with separate columns for each grader type
- DR-specific grade distributions
- Referral and treatment recommendations
- Image quality metrics

**Glaucoma Pivot View (`mvw_glaucoma_grading_pivot`):**
- VCDR (Vertical Cup-to-Disc Ratio) analysis
- Glaucoma severity grading
- Clinical decision patterns
- Risk assessment metrics

**AMD Pivot View (`mvw_amd_grading_pivot`):**
- AMD severity staging
- Treatment planning data
- Progression tracking
- Clinical outcome analysis

## Implementation Details

### Materialized View Scheduler

**Location:** `/utils/materialized_view_scheduler.py`

**Core Functions:**

```python
def refresh_materialized_view(app, schedule_time="manual"):
    # Refresh all views in dependency order
    # Log IST and UTC timestamps
    # Track performance metrics
    # Handle errors gracefully
    # Update refresh log table

def start_scheduler(app):
    # APS scheduler integration
    # Configurable refresh times
    # Background thread management
    # Automatic restart on failure
```

**Refresh Schedule:**
```python
# Daily schedule (IST)
SCHEDULED_TIMES = ["07:00", "13:30", "19:00", "01:30"]

# Each refresh includes:
1. mvw_grading_data_all (base view)
2. mvw_diabetic_retinopathy_grading_pivot
3. mvw_glaucoma_grading_pivot
4. mvw_amd_grading_pivot
```

### Database Schema for Analytics

**Refresh Log Table:**
```sql
CREATE TABLE materialized_view_refresh_log (
    id SERIAL PRIMARY KEY,
    materialized_view_name VARCHAR(100),
    refresh_type VARCHAR(50),  -- 'scheduled', 'manual'
    refresh_started_at TIMESTAMP WITH TIME ZONE,
    refresh_completed_at TIMESTAMP WITH TIME ZONE,
    refresh_duration_seconds INTEGER,
    success BOOLEAN,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**Performance Optimization:**
- 25+ indexes per view for fast querying
- GIN indexes on JSON feature data
- Composite indexes for common query patterns
- Partitioning strategies for large datasets

## Analytics Interface

### Admin Materialized View Status

**Route:** `/admin/materialized-view`

**Features:**
- Real-time status of all materialized views
- Manual refresh capabilities
- Refresh history and performance metrics
- Error tracking and troubleshooting

**Functionality:**
```python
@roles_required("admin")
def materialized_view_status():
    # Display current scheduler status
    # Show last refresh information
    # List refresh history with errors
    # Manual refresh trigger
    # Performance metrics dashboard
```

### Analytics Routes

**Main Analytics Dashboard:** `/analytics/`

**Available Views:**
- `/` - Main analytics dashboard
- `/direct/view/<uuid_str>` - Direct upload details
- `/encounter/view/<uuid_str>` - Encounter file details
- `/images` - Direct image analytics
- `/encounterFiles` - Encounter file analytics
- `/image/results` - Image results analysis
- `/encounter/results` - Encounter results analysis
- `/imagesWithoutTasks` - Unprocessed images
- `/directFilesKpi` - Direct files KPI dashboard
- `/encounterFilesKpi` - Encounter files KPI dashboard
- `/simpleRoutes` - Simple analytics routes

**Access Control:**
- Restricted to `admin` and `data_manager` roles
- Lab unit-based data scoping
- User permission validation

## KPI and Metrics System

### Key Performance Indicators

**Upload Metrics:**
- ZIP file processing success rates
- Direct upload statistics
- File type distribution
- Processing time analytics

**Grading Metrics:**
- Task completion rates
- Consensus building statistics
- Arbitration frequency
- Grader performance analysis

**Quality Metrics:**
- Verification success rates
- Error frequency analysis
- Data quality scores
- User compliance metrics

### KPI Data Collection

**Real-time Data Sources:**
- Materialized view queries
- Live database statistics
- Task completion tracking
- System performance metrics

**Aggregation Strategies:**
- Time-based rollups (daily, weekly, monthly)
- Disease-specific aggregations
- Lab unit performance comparisons
- Grader efficiency analysis

## User Interface Components

### Analytics Dashboard

**Main Features:**
- Interactive charts and graphs
- Real-time data updates
- Filterable data displays
- Export capabilities

**Chart Types:**
- Time series analysis
- Distribution charts
- Performance comparisons
- Trend analysis

**Filtering Options:**
- Date range selection
- Disease filtering
- Lab unit selection
- Grader-specific views

### Reporting Tools

**Standard Reports:**
- Grading activity reports
- Performance summaries
- Quality assurance reports
- Compliance documentation

**Custom Reports:**
- Flexible date ranges
- Multiple data dimensions
- Export formats (CSV, Excel, PDF)
- Scheduled report generation

## Data Processing Pipelines

### Real-time Analytics

**Data Flow:**
```
User Action → Database Update → Materialized View Refresh → Analytics Update → UI Display
```

**Update Triggers:**
- Grade submissions
- Task completions
- Verification actions
- Administrative changes

### Batch Processing

**Scheduled Processes:**
- Daily KPI calculations
- Weekly performance reports
- Monthly trend analysis
- Quarterly compliance reviews

**Optimization Strategies:**
- Incremental updates
- Caching mechanisms
- Parallel processing
- Resource management

## Integration Points

### with Grading System

**Real-time Integration:**
- Grade submission tracking
- Consensus building analytics
- Task completion metrics
- Grader performance monitoring

**Data Population:**
- Automatic materialized view updates
- KPI calculation triggers
- Performance metric updates
- Quality assurance data

### with Verification System

**Verification Analytics:**
- Verification success rates
- Processing time metrics
- Error categorization
- Quality assessment scores

### with Upload Systems

**Upload Analytics:**
- Processing success rates
- File type distribution
- Processing time analysis
- Error frequency tracking

## Performance Optimization

### Database Optimization

**Indexing Strategy:**
```sql
-- Performance indexes for materialized views
CREATE INDEX idx_mvw_grading_data_disease_date ON mvw_grading_data_all(disease_id, created_at);
CREATE INDEX idx_mvw_grading_data_grader_date ON mvw_grading_data_all(grader_user_id, updated_at);
CREATE INDEX idx_mvw_grading_data_state ON mvw_grading_data_all(task_state);

-- GIN index for JSON feature data
CREATE INDEX idx_mvw_grading_data_features ON mvw_grading_data_all USING GIN((resident_features::jsonb));
```

**Query Optimization:**
- Partitioned views for large datasets
- Result caching for frequent queries
- Connection pooling
- Query plan optimization

### System Performance

**Caching Strategies:**
- Redis-based query caching
- Application-level result caching
- Browser caching for static content
- CDN integration for assets

**Resource Management:**
- Background processing queues
- Rate limiting for analytics queries
- Memory usage optimization
- CPU load balancing

## Security and Access Control

### Data Protection

**Access Control:**
- Role-based data access
- Lab unit data scoping
- User permission validation
- Audit trail maintenance

**Privacy Protection:**
- Patient data anonymization in analytics
- Aggregated data only for reports
- Secure data transmission
- Compliance with medical data standards

### Monitoring and Auditing

**Access Logging:**
- User access tracking
- Query execution logging
- Data export monitoring
- System access auditing

**Security Features:**
- SQL injection prevention
- Rate limiting on analytics endpoints
- Input validation and sanitization
- Comprehensive error handling

## Error Handling and Recovery

### System Monitoring

**Health Checks:**
- Materialized view refresh monitoring
- Database performance tracking
- System resource utilization
- Error rate monitoring

**Alerting System:**
- Refresh failure notifications
- Performance degradation alerts
- System capacity warnings
- Error threshold notifications

### Recovery Mechanisms

**Automatic Recovery:**
- Failed refresh retries
- Scheduler restart on failure
- Database connection recovery
- Materialized view rebuild

**Manual Recovery:**
- Administrative override tools
- Data validation scripts
- System diagnostic tools
- Performance tuning utilities

## Future Enhancements

### Advanced Analytics

**Planned Features:**
1. **Machine Learning Integration:**
   - Predictive analytics for grading patterns
   - Anomaly detection in grading behavior
   - Performance prediction models
   - Automated quality scoring

2. **Real-time Analytics:**
   - WebSocket-based live updates
   - Stream processing for immediate insights
   - Real-time KPI dashboards
   - Instant notification systems

3. **Advanced Visualization:**
   - Interactive 3D data visualization
   - Geographic mapping of data
   - Advanced chart types and graphs
   - Custom report builders

### Scalability Improvements

**Performance Enhancements:**
- Distributed analytics processing
- Cloud-based analytics services
- Advanced caching strategies
- Database sharding for large datasets

**System Expansion:**
- Multi-tenant analytics support
- Cross-institution data comparison
- Industry benchmarking integration
- Research data export capabilities

## Best Practices

### Analytics Development

**Data Quality:**
- Consistent data validation
- Regular quality checks
- Automated testing frameworks
- Performance benchmarking

**User Experience:**
- Intuitive interface design
- Responsive layout for mobile access
- Fast query response times
- Comprehensive help documentation

### System Maintenance

**Regular Maintenance:**
- Index optimization
- Statistics updates
- Performance tuning
- Security audits

**Monitoring Practices:**
- Comprehensive logging
- Performance metrics tracking
- User behavior analysis
- System health monitoring

## Troubleshooting

### Common Analytics Issues

1. **Materialized View Refresh Failures:**
   - Check database connectivity
   - Verify view dependencies
   - Review system resources
   - Examine error logs

2. **Performance Degradation:**
   - Analyze query execution plans
   - Check index effectiveness
   - Monitor system resources
   - Review data growth patterns

3. **Data Inconsistencies:**
   - Verify source data integrity
   - Check refresh completion status
   - Validate aggregation logic
   - Review data transformation rules

### Debug Tools

**Administrative Tools:**
- Materialized view status interface
- Performance monitoring dashboard
- Query analysis tools
- System diagnostic utilities

**Analytics Tools:**
- Database query analyzers
- Performance profilers
- Resource usage monitors
- Error tracking systems
### Per-disease listing join optimization (2026-10-31)

The listing SQL builder uses disjoint source-specific equality joins instead of
one four-way OR join. Later branches exclude earlier matching predicates with
`IS NOT TRUE`, preserving NULL handling, overlapping foreign keys, and row
multiplicity. `optimize_task_join=False` retains the original query for comparison.
Existing materialized views retain their stored definition until explicitly rebuilt.

A separate production candidate, `mvw_image_listing_glaucoma_1_v2_candidate`,
was created for evaluation; the scheduler does not select this candidate name.
It matched all 22,351 existing rows in both directions using `EXCEPT ALL`.
With the same 26 indexes, two candidate refreshes took 2.264 and 2.193 seconds,
compared with the earlier recorded 177.509-second refresh. These measurements
were taken at different times and do not isolate lock waits or cache effects.
The existing production view has not been replaced. Candidate promotion and
cleanup require an explicit follow-up deployment; changing the builder alone
only affects newly created views.

Further candidate-only benchmarks retained all 26 equivalent indexes. Concurrent
refresh of the first candidate took 1.412s and 1.352s (1.236s with session-local
`jit=off`, `work_mem=64MB`). A second isolated view,
`mvw_image_listing_glaucoma_1_v2_fast_candidate`, inlines the base-image and
disease-task CTEs with `NOT MATERIALIZED`: initial build 0.769s, indexed concurrent
refresh 1.316s and 1.239s, or 1.132s with the same session-local tuning. A full
bidirectional `EXCEPT ALL` comparison with the first candidate found zero differences.
The full-JSON GIN index alone took approximately 0.95s to build, explaining much
of ordinary refresh overhead. No production session defaults or application
view definitions were changed in this experiment. Sub-second indexed refresh
has not been demonstrated; an incremental projection is a separate design option.
Both candidates remain for evaluation and should be cleaned up after promotion.

### Incremental glaucoma projection experiment

An isolated table, `glaucoma_listing_incremental_candidate`, retains all 26 read
indexes and is maintained by `refresh_glaucoma_listing_incremental_candidate(integer[])`.
The function accepts at most 1,000 non-null affected task IDs. It serializes writers
with a transaction-scoped advisory lock and atomically deletes/recomputes only those
tasks from the live source query. Missing or moved tasks are removed; duplicate IDs
do not multiply rows. A guarded predicate rewrite fails before deleting anything
if the source view definition changes unexpectedly. The function uses invoker
permissions and parameterized task IDs. This is an internal SQL prototype, with
no application API, scheduler, source triggers, or reader changes.

Setup: `scripts/analytics/glaucoma_incremental_candidate.sql`; reproducible timing
and full row comparison: `scripts/analytics/benchmark_glaucoma_incremental_candidate.sql`.
Run through psql with `ON_ERROR_STOP=1`. Setup initially copies the full candidate;
it must not be treated as a safe online bootstrap with concurrent source writes.
Regression tests use a private schema on test-db and exercise updates, deletions,
disease moves, duplicate IDs, empty batches, and refusing unexpected definitions.

Observed update times on 2026-10-31: 1 task 87.115ms, 10 tasks 45.527ms,
100 tasks 55.108ms, 1,000 tasks 141.338ms. Full bidirectional `EXCEPT ALL` found
zero differences against the freshly refreshed full candidate across 22,351 rows.
These are individual warm-system samples, not a latency guarantee. The initial
full copy and full reconciliation still require whole-dataset work.

The caller must supply every affected task ID. Production use requires transactional
invalidation covering task/grade/consensus changes and deletes, disease reassignment,
image/encounter/verification changes and shared hospital/lab/camera/area/AI model
metadata, plus retries, reconciliation and a race-safe bootstrap. Until then this
table is manually refreshed and may become stale; it is not used by application
readers. Follow-up: `fundus_img_xtract-kqdn`.

### Configured disease listings: one-time optimized rebuild and five-minute refresh

Migration `e8f1a2b3c4d5` first optimized the application glaucoma listing.
Migration `f9a2b3c4d5e6` extends this to every configured disease: it reads IDs and
names from `diseases`, derives each existing naming convention with `_mv_name`,
and regenerates the per-disease listing SQL using disjoint equality joins and
inlined base/task CTEs. This includes DR and encounter-status diseases, without
hard-coding a disease list. New disease views continue to be created by the daily
ensure task with the optimized builder. Ordinary refreshes never replace stored
view definitions; pre-existing views require this one-time migration.

Each replacement is built and indexed before a transactional name swap, retaining
existing index names, owner, grants and comment. No CASCADE is used; dependency
or lock failures roll the migration back. Downgrade restores original OR joins
for other diseases while retaining the preceding glaucoma optimization, and
restores the preceding hourly/all-disease and minute/glaucoma schedules. A
production-size downgrade may take several minutes.

The shared DB-backed Beat entry `Image Listing V2 Refresh (5m)` runs
`celery_tasks.tasks.mv_tasks.refresh_image_listing_v2_task` on the maintenance
queue every 300 seconds. It replaces the hourly all-disease and dedicated minute
glaucoma schedules. The code fallback uses the same entry name to avoid a second
schedule when DB entries are merged. Daily missing-view creation stays enabled.
The separate glaucoma task remains available for rollback compatibility.

Existing forced paths remain functional: review submissions enqueue a targeted
refresh after commit with the existing 30-second debounce; general/manual refresh
now uses CONCURRENTLY for every per-disease listing MV. All paths target the same
regenerated application views. General pivots and the all-image MV retain their
existing refresh behavior. Normal periodic freshness is five minutes plus queue
and refresh time; explicit refreshes can update sooner. Web need not restart for
the stored MV definition swap. Worker/Beat code reload is required for the changed
fallback and general refresh behavior.

The earlier prototype candidate MVs and incremental table remain separate
experiments and are not application readers. Their cleanup is tracked separately.

Live rollout on 2026-10-31 reached head `f9a2b3c4d5e6`: all 19 configured
per-disease MVs have optimized stored definitions. Before/after counts and full
row-content fingerprints were identical for every view. Existing index
sets were retained. A forced all-disease refresh through the existing Celery task
completed in 3.73 seconds: 19 refreshed, zero errors. General worker and Beat
were reloaded; web remained healthy without restart. Thirteen focused tests
passed, including configured-name creation, migration round trips, scheduling,
manual refresh selection, OR-join row multiplicity, and review debounce retries.
