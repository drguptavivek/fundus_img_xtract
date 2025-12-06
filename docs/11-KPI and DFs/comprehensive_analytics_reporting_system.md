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