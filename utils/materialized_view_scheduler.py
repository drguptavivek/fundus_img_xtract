"""Materialized View Refresh Scheduler

Timezone-aware scheduler for automatic refresh of mvw_grading_data_all materialized view.
Integrates with existing Flask application infrastructure including logging,
database sessions, and background task patterns.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta

import pytz
from sqlalchemy import text

logger = logging.getLogger("materialized_view")


def refresh_materialized_view(app, schedule_time="manual"):
    """Execute materialized view refresh with proper timezone logging.

    Args:
        app: Flask application instance
        schedule_time: String identifier for the scheduled refresh time

    Returns:
        bool: True if refresh successful, False otherwise
    """
    try:
        from db_transaction_manager import transaction_scope

        timezone_str = app.config.get("MATERIALIZED_VIEW_TIMEZONE", app.config.get("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata"))
        tz = pytz.timezone(timezone_str)

        with app.app_context():
            with transaction_scope() as db:
                start_time = datetime.now(pytz.UTC)
                ist_time = datetime.now(tz)

                logger.info(f"Starting materialized view refresh - Schedule: {schedule_time}")
                logger.info(f"IST Time: {ist_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                logger.info(f"UTC Time: {start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")

                # Execute the refresh using non-concurrent approach (CONCURRENTLY requires unique index)
                db.execute(text("REFRESH MATERIALIZED VIEW mvw_grading_data_all"))

                duration = (datetime.now(pytz.UTC) - start_time).total_seconds()
                logger.info(f"Materialized view refreshed successfully in {duration:.2f} seconds - Schedule: {schedule_time}")
                return True

    except Exception as e:
        logger.error(f"Failed to refresh materialized view - Schedule: {schedule_time}, Error: {str(e)}")
        return False


def run_scheduler_thread(app):
    """Main scheduler daemon thread following existing stuck task cleanup pattern.

    Args:
        app: Flask application instance
    """
    timezone_str = app.config.get("MATERIALIZED_VIEW_TIMEZONE", app.config.get("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata"))
    tz = pytz.timezone(timezone_str)
    schedule_times = app.config.get("MATERIALIZED_VIEW_SCHEDULE_TIMES", ["07:00", "13:30", "19:00", "01:30"])

    # Handle both string and list inputs
    if isinstance(schedule_times, str):
        schedule_times = schedule_times.split(",")

    retry_attempts = app.config.get("MATERIALIZED_VIEW_RETRY_ATTEMPTS", 3)
    retry_delay = app.config.get("MATERIALIZED_VIEW_RETRY_DELAY_SECONDS", 60)

    logger.info(f"Materialized view scheduler started - Times: {schedule_times}, Timezone: {timezone_str}")

    while True:
        try:
            current_ist = datetime.now(tz)
            current_time_str = current_ist.strftime("%H:%M")
            current_minute = current_ist.minute

            # Check if current time matches any scheduled time (on the hour)
            if current_time_str in schedule_times and current_minute == 0:
                logger.info(f"Scheduled refresh time reached: {current_time_str} IST")

                # Retry logic with exponential backoff
                for attempt in range(retry_attempts):
                    if refresh_materialized_view(app, current_time_str):
                        break
                    elif attempt < retry_attempts - 1:
                        wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                        logger.warning(f"Refresh attempt {attempt + 1} failed, retrying in {wait_time} seconds...")
                        time.sleep(wait_time)

            # Check every 30 seconds to catch schedule changes
            time.sleep(30)

        except Exception as e:
            logger.error(f"Scheduler thread error: {str(e)}")
            time.sleep(60)  # Wait longer on error


def initialize_scheduler(app):
    """Initialize and return scheduler thread for app.py integration.

    Args:
        app: Flask application instance

    Returns:
        threading.Thread: Configured scheduler daemon thread
    """
    if not app.config.get("MATERIALIZED_VIEW_SCHEDULE_ENABLED", False):
        logger.info("Materialized view scheduler disabled")
        return None

    scheduler_thread = threading.Thread(
        target=run_scheduler_thread,
        args=(app,),
        daemon=True,
        name="MaterializedViewScheduler"
    )
    return scheduler_thread


def manual_refresh_now(app):
    """Manual refresh trigger for admin interface.

    Args:
        app: Flask application instance

    Returns:
        dict: Result with success status and message
    """
    tz = pytz.timezone(app.config.get("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata"))
    current_ist = datetime.now(tz)

    result = refresh_materialized_view(app, "manual")

    if result:
        return {
            "success": True,
            "message": f"Materialized view refreshed successfully at {current_ist.strftime('%Y-%m-%d %H:%M:%S IST')}"
        }
    else:
        return {
            "success": False,
            "message": f"Materialized view refresh failed at {current_ist.strftime('%Y-%m-%d %H:%M:%S IST')}. Check logs for details."
        }


def get_scheduler_status(app):
    """Get current scheduler status and next refresh times.

    Args:
        app: Flask application instance

    Returns:
        dict: Scheduler status information
    """
    timezone_str = app.config.get("MATERIALIZED_VIEW_TIMEZONE", app.config.get("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata"))
    tz = pytz.timezone(timezone_str)
    schedule_times = app.config.get("MATERIALIZED_VIEW_SCHEDULE_TIMES", ["07:00", "13:30", "19:00", "01:30"])

    # Handle both string and list inputs
    if isinstance(schedule_times, str):
        schedule_times = schedule_times.split(",")

    current_ist = datetime.now(tz)
    current_utc = datetime.utcnow()

    # Calculate next run times for all schedules
    next_runs = []
    for time_str in schedule_times:
        hour, minute = time_str.split(":")

        # Create next occurrence of this time
        next_run_ist = current_ist.replace(
            hour=int(hour),
            minute=int(minute),
            second=0,
            microsecond=0
        )

        # If time has passed today, schedule for tomorrow
        if next_run_ist <= current_ist:
            next_run_ist += timedelta(days=1)

        next_run_utc = next_run_ist.astimezone(pytz.UTC)
        hours_from_now = (next_run_ist - current_ist).total_seconds() / 3600

        next_runs.append({
            'time_ist': time_str,
            'next_run_ist': next_run_ist.strftime('%Y-%m-%d %H:%M:%S IST'),
            'next_run_utc': next_run_utc.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'hours_from_now': round(hours_from_now, 1)
        })

    # Sort by next run time
    next_runs.sort(key=lambda x: x['hours_from_now'])

    return {
        'current_ist': current_ist.strftime('%Y-%m-%d %H:%M:%S IST'),
        'current_utc': current_utc.strftime('%Y-%m-%d %H:%M:%S UTC'),
        'timezone': timezone_str,
        'enabled': app.config.get("MATERIALIZED_VIEW_SCHEDULE_ENABLED", False),
        'schedule_times': schedule_times,
        'next_runs': next_runs,
        'frequency': '4 times daily, 7 days a week'
    }