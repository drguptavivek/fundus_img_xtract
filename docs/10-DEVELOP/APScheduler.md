# APScheduler Technical Guidance

## 📋 Table of Contents

1. [Overview](#overview)
2. [Current Implementation Architecture](#current-implementation-architecture)
3. [Scheduler Patterns](#scheduler-patterns)
4. [Configuration](#configuration)
5. [Timezone Handling](#timezone-handling)
6. [Error Handling and Recovery](#error-handling-and-recovery)
7. [Monitoring and Logging](#monitoring-and-logging)
8. [Best Practices](#best-practices)
9. [Migration to APScheduler](#migration-to-apscheduler)
10. [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

The Fundus Image Manager currently implements **custom thread-based schedulers** for background tasks rather than using the full APScheduler library. While APScheduler is listed in dependencies (>=3.11.1), the application uses a lightweight, custom implementation that provides better control over medical imaging workflows.

### Current Schedulers

1. **Materialized View Scheduler** - Refreshes analytics materialized views 4x daily
2. **Thumbnail Maintenance Scheduler** - Manages thumbnail cleanup and regeneration

### Why Custom Implementation?

- **Medical Data Compliance**: Better control over execution timing and error handling
- **Database Transaction Safety**: Direct integration with existing transaction patterns
- **Audit Trail Requirements**: Comprehensive logging for regulatory compliance
- **Resource Management**: Controlled threading prevents database connection exhaustion

---

## 🏗️ Current Implementation Architecture

### Thread-Based Design

```python
# Pattern used across both schedulers
def run_scheduler_thread(app):
    """Main scheduler daemon thread following existing stuck task cleanup pattern."""
    timezone_str = app.config.get("SCHEDULER_TIMEZONE", "Asia/Kolkata")
    tz = pytz.timezone(timezone_str)
    schedule_times = app.config.get("SCHEDULE_TIMES", ["07:00", "13:30", "19:00", "01:30"])

    while True:
        try:
            current_time = datetime.now(tz)
            current_time_str = current_time.strftime("%H:%M")

            # Check if current time matches any scheduled time
            if current_time_str in schedule_times and current_time.minute == 0:
                execute_scheduled_task(app, current_time_str)

            # Check every 30 seconds
            time.sleep(30)

        except Exception as e:
            logger.error(f"Scheduler thread error: {str(e)}")
            time.sleep(60)  # Wait longer on error
```

### Key Components

1. **Daemon Threads**: Run in background, don't prevent app shutdown
2. **Timezone-Aware**: All scheduling uses configured timezone
3. **Retry Logic**: Exponential backoff for failed tasks
4. **Database Integration**: Uses existing transaction patterns
5. **Comprehensive Logging**: Structured logging with timestamps

---

## 🔧 Scheduler Patterns

### 1. Materialized View Scheduler

**Location**: `utils/materialized_view_scheduler.py`

**Schedule**: 4 times daily (07:00, 13:30, 19:00, 01:30 IST)

**Tasks**:
- Refresh `mvw_grading_data_all`
- Refresh `mvw_diabetic_retinopathy_grading_pivot`
- Refresh `mvw_glaucoma_grading_pivot`
- Refresh `mvw_amd_grading_pivot`
- Refresh `mvw_encounter_pivot`

```python
# Initialization in app.py
if app.config.get("MATERIALIZED_VIEW_SCHEDULE_ENABLED", False):
    from utils.materialized_view_scheduler import initialize_scheduler
    scheduler_thread = initialize_scheduler(app)
    if scheduler_thread:
        scheduler_thread.start()
```

### 2. Thumbnail Maintenance Scheduler

**Location**: `utils/thumbnail_maintenance_scheduler.py`

**Schedule**: Daily tasks at different times

**Tasks**:
- **07:00 IST**: Orphaned thumbnail cleanup
- **13:30 IST**: Missing thumbnail regeneration (limit=50)
- **19:00 IST**: Thumbnail integrity validation
- **01:30 IST**: Full maintenance cycle

```python
# Maintenance cycle order
def run_maintenance_tasks(app):
    """Run all maintenance tasks in sequence."""
    # 1. Cleanup orphaned thumbnails
    results['cleanup'] = cleanup_orphaned_thumbnails(app, "maintenance_cycle")

    # 2. Regenerate missing thumbnails
    results['regeneration'] = regenerate_missing_thumbnails(app, "maintenance_cycle", limit=50)

    # 3. Validate thumbnail integrity
    results['validation'] = validate_thumbnail_integrity(app, "maintenance_cycle", sample_size=50)
```

---

## ⚙️ Configuration

### Environment Variables

```bash
# Materialized View Scheduler
MATERIALIZED_VIEW_SCHEDULE_ENABLED=true
MATERIALIZED_VIEW_TIMEZONE=Asia/Kolkata
MATERIALIZED_VIEW_SCHEDULE_TIMES=07:00,13:30,19:00,01:30
MATERIALIZED_VIEW_RETRY_ATTEMPTS=3
MATERIALIZED_VIEW_RETRY_DELAY_SECONDS=60

# Thumbnail Maintenance Scheduler
THUMBNAIL_MAINTENANCE_ENABLED=true
THUMBNAIL_MAINTENANCE_TIMEZONE=Asia/Kolkata

# Common Timezone Settings
DEFAULT_DISPLAY_TIMEZONE=Asia/Kolkata
```

### Configuration in app.py

```python
# Load timezone configuration
default_timezone = get_env("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata")
tz = pytz.timezone(default_timezone)

# Configure scheduler-specific settings
app.config["MATERIALIZED_VIEW_SCHEDULE_ENABLED"] = str(get_env("MATERIALIZED_VIEW_SCHEDULE_ENABLED", "false")).lower() in ("1", "true", "yes")
app.config["MATERIALIZED_VIEW_TIMEZONE"] = get_env("MATERIALIZED_VIEW_TIMEZONE", default_timezone)
app.config["MATERIALIZED_VIEW_SCHEDULE_TIMES"] = get_env("MATERIALIZED_VIEW_SCHEDULE_TIMES", "07:00,13:30,19:00,01:30").split(",")
```

---

## 🌍 Timezone Handling

### Best Practices

1. **Store in UTC**: All database timestamps in UTC
2. **Display in Local**: Convert to user's timezone for display
3. **Schedule in Local**: All scheduling uses configured local timezone
4. **Log Both**: Log both UTC and local times for debugging

### Timezone Conversion Pattern

```python
import pytz
from datetime import datetime

def get_timezone_aware_times(app):
    """Get timezone-aware current times for logging."""
    timezone_str = app.config.get("SCHEDULER_TIMEZONE", "Asia/Kolkata")
    tz = pytz.timezone(timezone_str)

    # Current times
    utc_now = datetime.utcnow()
    local_now = datetime.now(tz)

    return {
        'utc_time': utc_now.strftime('%Y-%m-%d %H:%M:%S UTC'),
        'local_time': local_now.strftime('%Y-%m-%d %H:%M:%S %Z'),
        'timezone': timezone_str
    }
```

### Schedule Time Calculation

```python
def calculate_next_run_time(schedule_time_str, timezone_str="Asia/Kolkata"):
    """Calculate next run time for a given schedule."""
    tz = pytz.timezone(timezone_str)
    current_local = datetime.now(tz)

    hour, minute = schedule_time_str.split(":")
    next_run = current_local.replace(
        hour=int(hour),
        minute=int(minute),
        second=0,
        microsecond=0
    )

    # If time has passed today, schedule for tomorrow
    if next_run <= current_local:
        next_run += timedelta(days=1)

    return next_run
```

---

## 🛡️ Error Handling and Recovery

### Retry Logic with Exponential Backoff

```python
def execute_with_retry(task_func, app, schedule_time, max_attempts=3, base_delay=60):
    """Execute task with exponential backoff retry logic."""
    for attempt in range(max_attempts):
        try:
            result = task_func(app, schedule_time)
            if result.get('success', False):
                return result

        except Exception as e:
            logger.error(f"Task execution failed (attempt {attempt + 1}): {str(e)}")

            if attempt < max_attempts - 1:
                wait_time = base_delay * (2 ** attempt)  # Exponential backoff
                logger.warning(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)

    return {'success': False, 'error': 'Max retry attempts exceeded'}
```

### Error Recovery Patterns

1. **Database Connection Errors**: Close and reopen connections
2. **File System Errors**: Check permissions and disk space
3. **Memory Issues**: Reduce batch sizes in next run
4. **Network Timeouts**: Increase timeout values

### Graceful Shutdown

```python
class SchedulerManager:
    def __init__(self, app):
        self.app = app
        self.schedulers = {}
        self.running = False

    def shutdown(self):
        """Gracefully shutdown all schedulers."""
        self.running = False

        for name, scheduler in self.schedulers.items():
            try:
                scheduler.stop()
                logger.info(f"Scheduler {name} stopped successfully")
            except Exception as e:
                logger.error(f"Error stopping scheduler {name}: {str(e)}")
```

---

## 📊 Monitoring and Logging

### Structured Logging Pattern

```python
import logging

# Create specialized loggers
materialized_view_logger = logging.getLogger("materialized_view")
thumbnail_maintenance_logger = logging.getLogger("thumbnail_maintenance")
scheduler_logger = logging.getLogger("scheduler")

def log_task_execution(task_name, schedule_time, result, duration):
    """Log task execution with structured data."""
    if result.get('success', False):
        logger.info(
            f"Task {task_name} completed successfully - "
            f"Schedule: {schedule_time}, "
            f"Duration: {duration:.2f}s, "
            f"Result: {result}"
        )
    else:
        logger.error(
            f"Task {task_name} failed - "
            f"Schedule: {schedule_time}, "
            f"Duration: {duration:.2f}s, "
            f"Error: {result.get('error', 'Unknown error')}"
        )
```

### Performance Monitoring

```python
def track_scheduler_performance():
    """Track scheduler performance metrics."""
    return {
        'task_execution_times': [],
        'success_rate': 0.0,
        'error_count': 0,
        'last_execution': None,
        'next_scheduled': None,
        'memory_usage': 0,
        'thread_status': 'running'
    }
```

### Health Check Endpoints

```python
@bp.route("/admin/scheduler/health")
@roles_required("admin")
def scheduler_health():
    """Health check for all schedulers."""
    status = {
        'materialized_view': get_materialized_view_status(),
        'thumbnail_maintenance': get_thumbnail_maintenance_status(),
        'overall_health': 'healthy'
    }

    # Check if any scheduler has issues
    for scheduler_name, scheduler_status in status.items():
        if scheduler_name != 'overall_health' and scheduler_status.get('has_errors', False):
            status['overall_health'] = 'degraded'
            break

    return jsonify(status)
```

---

## 🎯 Best Practices

### 1. Task Design

```python
# ✅ Good: Atomic tasks with clear boundaries
def refresh_single_view(view_name, app):
    """Refresh a single materialized view."""
    start_time = datetime.utcnow()
    try:
        with transaction_scope() as db:
            db.execute(text(f"REFRESH MATERIALIZED VIEW {view_name}"))
            return {'success': True, 'duration': (datetime.utcnow() - start_time).total_seconds()}
    except Exception as e:
        return {'success': False, 'error': str(e)}

# ❌ Bad: Monolithic tasks that do too much
def refresh_all_views_do_everything(app):
    """Anti-pattern: Too much responsibility."""
    # Multiple database operations, file operations, etc.
```

### 2. Configuration Management

```python
# ✅ Good: Environment-specific configuration
def get_scheduler_config(app, scheduler_name):
    """Get scheduler configuration with defaults."""
    prefix = f"{scheduler_name.upper()}_"
    return {
        'enabled': app.config.get(f"{prefix}ENABLED", False),
        'timezone': app.config.get(f"{prefix}TIMEZONE", app.config.get("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata")),
        'schedule_times': app.config.get(f"{prefix}SCHEDULE_TIMES", ["07:00"]),
        'retry_attempts': app.config.get(f"{prefix}RETRY_ATTEMPTS", 3),
        'retry_delay': app.config.get(f"{prefix}RETRY_DELAY", 60)
    }
```

### 3. Resource Management

```python
# ✅ Good: Proper resource cleanup
def execute_with_resources(task_func, app, schedule_time):
    """Execute task with proper resource management."""
    resources_acquired = []

    try:
        # Acquire resources
        db = get_database_connection()
        resources_acquired.append(db)

        # Execute task
        result = task_func(app, schedule_time, db)
        return result

    finally:
        # Cleanup resources
        for resource in resources_acquired:
            try:
                resource.close()
            except Exception as e:
                logger.warning(f"Error cleaning up resource: {str(e)}")
```

### 4. Testing Scheduler Code

```python
# ✅ Good: Testable scheduler functions
def test_scheduler_time_matching():
    """Test schedule time matching logic."""
    with app.app_context():
        # Mock current time
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2024, 1, 1, 7, 0, 0)

            # Test schedule matching
            assert is_schedule_time("07:00", ["07:00", "13:30"]) == True
            assert is_schedule_time("08:00", ["07:00", "13:30"]) == False
```

---

## 🔄 Migration to APScheduler

While the current custom implementation works well, here's guidance for migrating to APScheduler if needed:

### Migration Benefits

1. **Feature Rich**: Cron-like scheduling, job persistence, distributed execution
2. **Battle Tested**: Widely used in production systems
3. **Integration**: Ready-made integrations with Flask, Django, etc.
4. **Monitoring**: Built-in job monitoring and management

### Migration Strategy

```python
# Step 1: Install APScheduler (already in dependencies)
# pip install apscheduler>=3.11.1

# Step 2: Replace custom scheduler with APScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

def initialize_apscheduler(app):
    """Initialize APScheduler with existing jobs."""
    scheduler = BackgroundScheduler(timezone=app.config.get('DEFAULT_DISPLAY_TIMEZONE', 'Asia/Kolkata'))

    # Materialized view refreshes
    scheduler.add_job(
        func=refresh_materialized_views,
        trigger=CronTrigger(hour='7,13,19,1', minute='0,30'),
        id='materialized_view_refresh',
        name='Refresh Materialized Views',
        replace_existing=True
    )

    # Thumbnail maintenance
    scheduler.add_job(
        func=cleanup_thumbnails,
        trigger=CronTrigger(hour='7', minute='0'),
        id='thumbnail_cleanup',
        name='Thumbnail Cleanup'
    )

    return scheduler

# Step 3: Update app.py
def create_app():
    app = Flask(__name__)

    # ... existing setup ...

    # Initialize APScheduler
    if app.config.get("SCHEDULER_ENABLED", False):
        scheduler = initialize_apscheduler(app)
        scheduler.start()
        app.scheduler = scheduler

    return app
```

### Hybrid Approach

```python
# Gradual migration: Keep custom for critical tasks, use APScheduler for new ones
class HybridScheduler:
    def __init__(self, app):
        self.app = app
        self.custom_schedulers = {}  # Existing custom schedulers
        self.apscheduler = None      # New APScheduler instance

    def initialize(self):
        """Initialize both custom and APScheduler."""
        # Keep critical medical data workflows on custom schedulers
        self.custom_schedulers['materialized_view'] = initialize_custom_scheduler(self.app)

        # Use APScheduler for new, non-critical tasks
        self.apscheduler = BackgroundScheduler()
        self.apscheduler.add_job(
            func=generate_reports,
            trigger=CronTrigger(hour='8', minute='0'),
            id='daily_reports'
        )
        self.apscheduler.start()
```

---

## 🔧 Troubleshooting

### Common Issues and Solutions

#### 1. Scheduler Not Starting

**Symptoms**: No scheduled tasks executing, no error messages

**Causes**:
- Configuration disabled
- Thread creation failure
- Missing dependencies

**Solutions**:
```python
# Check configuration
if not app.config.get("SCHEDULER_ENABLED", False):
    logger.info("Scheduler disabled by configuration")

# Check thread creation
try:
    scheduler_thread = threading.Thread(target=scheduler_function, daemon=True)
    scheduler_thread.start()
    logger.info(f"Scheduler thread started: {scheduler_thread.name}")
except Exception as e:
    logger.error(f"Failed to start scheduler thread: {str(e)}")
```

#### 2. Tasks Missing Schedule

**Symptoms**: Tasks execute at wrong times or not at all

**Causes**:
- Timezone mismatch
- System time drift
- Schedule format errors

**Solutions**:
```python
# Debug schedule matching
def debug_schedule_matching():
    """Debug schedule time matching logic."""
    tz = pytz.timezone("Asia/Kolkata")
    current_time = datetime.now(tz)

    for schedule_time in ["07:00", "13:30", "19:00", "01:30"]:
        hour, minute = schedule_time.split(":")
        is_match = (
            current_time.hour == int(hour) and
            current_time.minute == int(minute)
        )
        logger.info(f"Schedule {schedule_time}: Match={is_match}, Current={current_time.strftime('%H:%M')}")
```

#### 3. Memory Leaks

**Symptoms**: Memory usage increases over time

**Causes**:
- Thread accumulation
- Database connection leaks
- Large object retention

**Solutions**:
```python
# Monitor thread count
import threading

def monitor_threads():
    """Monitor thread count for leaks."""
    thread_count = threading.active_count()
    logger.info(f"Active threads: {thread_count}")

    if thread_count > EXPECTED_THREAD_COUNT:
        logger.warning(f"High thread count detected: {thread_count}")

        # List all threads
        for thread in threading.enumerate():
            logger.info(f"Thread: {thread.name} (alive: {thread.is_alive()})")
```

#### 4. Database Connection Issues

**Symptoms**: Database connection errors, timeouts

**Causes**:
- Connection pool exhaustion
- Long-running transactions
- Connection timeouts

**Solutions**:
```python
# Use connection pooling
from sqlalchemy.pool import QueuePool

def create_engine_with_pooling():
    """Create database engine with proper pooling."""
    return create_engine(
        DATABASE_URL,
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=3600  # Recycle connections every hour
    )
```

### Debug Mode Scheduler

```python
class DebugScheduler:
    """Debug version of scheduler with extra logging."""

    def __init__(self, app):
        self.app = app
        self.debug_mode = app.config.get("SCHEDULER_DEBUG", False)

    def debug_log(self, message):
        """Enhanced debug logging."""
        if self.debug_mode:
            import traceback
            logger.info(f"[SCHEDULER-DEBUG] {message}")
            logger.info(f"Call stack: {traceback.format_stack()[-3]}")

    def run_with_debug(self):
        """Run scheduler with debug information."""
        while True:
            try:
                current_time = datetime.now()
                self.debug_log(f"Checking schedule at {current_time}")

                # ... existing logic ...

            except Exception as e:
                self.debug_log(f"Error in scheduler: {str(e)}")
                self.debug_log(f"Full traceback: {traceback.format_exc()}")
```

---

## 📝 Conclusion

The Fundus Image Manager's custom scheduler implementation provides:

### ✅ Strengths
- **Medical Compliance**: Full control over execution and error handling
- **Integration**: Seamless integration with existing patterns
- **Reliability**: Proven in production with medical data workflows
- **Audit Trail**: Comprehensive logging for regulatory requirements

### 🔄 Future Considerations
- **APSchedul Integration**: Consider for non-critical tasks
- **Distributed Scheduling**: For multi-instance deployments
- **Job Persistence**: For crash recovery
- **Monitoring**: Enhanced metrics and alerting

### 🛡️ Production Safety
- Always test scheduler changes in non-production environments
- Monitor scheduler health and performance
- Keep detailed logs for audit trails
- Implement graceful shutdown procedures

This custom approach provides the reliability and control needed for medical imaging workflows while maintaining simplicity and debuggability.

---

**Last Updated**: November 11, 2025
**Version**: 1.0 - Production Ready
**Maintainer**: Fundus Image Manager Development Team