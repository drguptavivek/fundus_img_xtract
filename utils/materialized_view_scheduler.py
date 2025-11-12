"""Materialized View Refresh Scheduler

Timezone-aware scheduler for automatic refresh of all materialized views including:
- mvw_grading_data_all (general grading data)
- mvw_diabetic_retinopathy_grading_pivot (DR-specific pivoted data)
- mvw_glaucoma_grading_pivot (glaucoma-specific pivoted data)
- mvw_amd_grading_pivot (AMD-specific pivoted data)
- mvw_encounter_pivot (comprehensive encounter-centric analytics with individual image grade pivots)
- mvw_image_listing_all (comprehensive image catalog with upload types, verification status, and disease configuration)

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
    """Execute all materialized view refreshes with proper timezone logging and timestamp tracking.

    Refreshes the following views in order:
    1. mvw_grading_data_all (general grading data)
    2. mvw_diabetic_retinopathy_grading_pivot (DR-specific pivoted data)
    3. mvw_glaucoma_grading_pivot (glaucoma-specific pivoted data)
    4. mvw_amd_grading_pivot (AMD-specific pivoted data)
    5. mvw_encounter_pivot (comprehensive encounter-centric analytics with individual image grade pivots)
    6. mvw_image_listing_all (comprehensive image catalog with upload types and verification status)

    Args:
        app: Flask application instance
        schedule_time: String identifier for the scheduled refresh time

    Returns:
        bool: True if all refreshes successful, False otherwise
    """
    from datetime import datetime as dt

    timezone_str = app.config.get("MATERIALIZED_VIEW_TIMEZONE", app.config.get("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata"))
    tz = pytz.timezone(timezone_str)
    start_time = datetime.now(pytz.UTC)
    ist_time = datetime.now(tz)

    # Create log entry for refresh start
    log_id = None
    try:
        from db_transaction_manager import transaction_scope

        with app.app_context():
            with transaction_scope() as db:
                logger.info(f"Starting materialized view refresh - Schedule: {schedule_time}")
                logger.info(f"IST Time: {ist_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                logger.info(f"UTC Time: {start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")

                # Insert log entry for refresh start
                result = db.execute(
                    text("""
                        INSERT INTO materialized_view_refresh_log
                        (refresh_type, refresh_started_at, success)
                        VALUES (:refresh_type, :started_at, FALSE)
                        RETURNING id
                    """),
                    {
                        "refresh_type": schedule_time,
                        "started_at": start_time
                    }
                )
                log_id = result.scalar()

                # Refresh all materialized views in order
                views_to_refresh = [
                    ("mvw_grading_data_all", "General Grading Data"),
                    ("mvw_diabetic_retinopathy_grading_pivot", "Diabetic Retinopathy Pivot"),
                    ("mvw_glaucoma_grading_pivot", "Glaucoma Pivot"),
                    ("mvw_amd_grading_pivot", "AMD Pivot"),
                    ("mvw_encounter_pivot", "Encounter Pivot"),
                    ("mvw_image_listing_all", "Image Listing All")
                ]

                total_duration = 0
                successful_refreshes = 0

                for view_name, view_description in views_to_refresh:
                    view_start_time = datetime.now(pytz.UTC)

                    try:
                        logger.info(f"Refreshing {view_description} ({view_name})")
                        db.execute(text(f"REFRESH MATERIALIZED VIEW {view_name}"))

                        view_duration = (datetime.now(pytz.UTC) - view_start_time).total_seconds()
                        total_duration += view_duration
                        successful_refreshes += 1

                        logger.info(f"Successfully refreshed {view_description} in {view_duration:.2f} seconds")

                    except Exception as view_error:
                        logger.error(f"Failed to refresh {view_description} ({view_name}): {str(view_error)}")
                        # Continue with other views even if one fails

                overall_duration = (datetime.now(pytz.UTC) - start_time).total_seconds()

                # Update log entry with overall success
                success = successful_refreshes == len(views_to_refresh)
                db.execute(
                    text("""
                        UPDATE materialized_view_refresh_log
                        SET refresh_completed_at = :completed_at,
                            refresh_duration_seconds = :duration,
                            success = :success,
                            error_message = :error_message,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :log_id
                    """),
                    {
                        "completed_at": datetime.now(pytz.UTC),
                        "duration": overall_duration,
                        "success": success,
                        "error_message": None if success else f"Failed {len(views_to_refresh) - successful_refreshes}/{len(views_to_refresh)} views",
                        "log_id": log_id
                    }
                )

                logger.info(f"Materialized view refresh completed: {successful_refreshes}/{len(views_to_refresh)} views successful in {overall_duration:.2f} seconds - Schedule: {schedule_time}")
                return success

    except Exception as e:
        logger.error(f"Failed to refresh materialized view - Schedule: {schedule_time}, Error: {str(e)}")

        # Update log entry with failure if we have a log_id
        if log_id:
            try:
                from db_transaction_manager import transaction_scope

                with app.app_context():
                    with transaction_scope() as db:
                        db.execute(
                            text("""
                                UPDATE materialized_view_refresh_log
                                SET refresh_completed_at = :completed_at,
                                    refresh_duration_seconds = :duration,
                                    success = FALSE,
                                    error_message = :error_message,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE id = :log_id
                            """),
                            {
                                "completed_at": datetime.now(pytz.UTC),
                                "duration": (datetime.now(pytz.UTC) - start_time).total_seconds(),
                                "error_message": str(e),
                                "log_id": log_id
                            }
                        )
            except Exception as log_error:
                logger.error(f"Failed to update refresh log: {str(log_error)}")

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
            "message": f"All materialized views refreshed successfully at {current_ist.strftime('%Y-%m-%d %H:%M:%S IST')}"
        }
    else:
        return {
            "success": False,
            "message": f"One or more materialized view refreshes failed at {current_ist.strftime('%Y-%m-%d %H:%M:%S IST')}. Check logs for details."
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

    # Get last refresh information
    last_refresh_info = get_last_refresh_info(app)

    return {
        'current_ist': current_ist.strftime('%Y-%m-%d %H:%M:%S IST'),
        'current_utc': current_utc.strftime('%Y-%m-%d %H:%M:%S UTC'),
        'timezone': timezone_str,
        'enabled': app.config.get("MATERIALIZED_VIEW_SCHEDULE_ENABLED", False),
        'schedule_times': schedule_times,
        'next_runs': next_runs,
        'frequency': '4 times daily, 7 days a week',
        'last_refresh': last_refresh_info
    }


def get_last_refresh_info(app):
    """Get the most recent refresh information.

    Args:
        app: Flask application instance

    Returns:
        dict: Last refresh information
    """
    try:
        from db_transaction_manager import transaction_scope

        with app.app_context():
            with transaction_scope() as db:
                # Query the most recent successful refresh
                result = db.execute(
                    text("""
                        SELECT
                            refresh_type,
                            refresh_started_at,
                            refresh_completed_at,
                            refresh_duration_seconds,
                            success,
                            error_message,
                            created_at,
                            updated_at
                        FROM materialized_view_refresh_log
                        WHERE materialized_view_name = 'mvw_grading_data_all'
                        ORDER BY refresh_started_at DESC
                        LIMIT 1
                    """)
                ).fetchone()

                if result:
                    # Parse timestamps
                    timezone_str = app.config.get("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata")
                    tz = pytz.timezone(timezone_str)

                    refresh_started_utc = result['refresh_started_at']
                    if refresh_started_utc:
                        if hasattr(refresh_started_utc, 'astimezone'):
                            refresh_started_utc = refresh_started_utc.astimezone(tz)
                        else:
                            refresh_started_utc = pytz.utc.localize(refresh_started_utc).astimezone(tz)

                    refresh_completed_utc = result['refresh_completed_at']
                    if refresh_completed_utc:
                        if hasattr(refresh_completed_utc, 'astimezone'):
                            refresh_completed_utc = refresh_completed_utc.astimezone(tz)
                        else:
                            refresh_completed_utc = pytz.utc.localize(refresh_completed_utc).astimezone(tz)

                    return {
                        'has_data': True,
                        'refresh_type': result['refresh_type'],
                        'refresh_started_at': refresh_started_utc.strftime('%Y-%m-%d %H:%M:%S %Z') if refresh_started_utc else None,
                        'refresh_completed_at': refresh_completed_utc.strftime('%Y-%m-%d %H:%M:%S %Z') if refresh_completed_utc else None,
                        'refresh_duration_seconds': result['refresh_duration_seconds'],
                        'success': result['success'],
                        'error_message': result['error_message'],
                        'ist_time': refresh_completed_utc.strftime('%Y-%m-%d %H:%M:%S IST') if refresh_completed_utc else None,
                        'utc_time': result['refresh_completed_at'].strftime('%Y-%m-%d %H:%M:%S UTC') if result['refresh_completed_at'] else None,
                        'data_freshness_minutes': round((datetime.now(pytz.UTC) - result['refresh_completed_at'].astimezone(pytz.UTC)).total_seconds() / 60, 1) if result['refresh_completed_at'] else None
                    }
                else:
                    return {
                        'has_data': False,
                        'message': 'No refresh history found'
                    }

    except Exception as e:
        logger.error(f"Failed to get last refresh info: {str(e)}")
        return {
            'has_data': False,
            'error': str(e)
        }