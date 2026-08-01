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
from db_transaction_manager import transaction_scope
from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger("materialized_view")


def _create_refresh_log_entry(app, schedule_time, start_time):
    with app.app_context():
        with transaction_scope() as db:
            result = db.execute(
                text(
                    """
                    INSERT INTO materialized_view_refresh_log
                    (refresh_type, refresh_started_at, success)
                    VALUES (:refresh_type, :started_at, FALSE)
                    RETURNING id
                """
                ),
                {
                    "refresh_type": schedule_time,
                    "started_at": start_time,
                },
            )
            return result.scalar()


def _update_refresh_log_entry(app, log_id, completed_at, duration, success, error_message):
    with app.app_context():
        with transaction_scope() as db:
            db.execute(
                text(
                    """
                    UPDATE materialized_view_refresh_log
                    SET refresh_completed_at = :completed_at,
                        refresh_duration_seconds = :duration,
                        success = :success,
                        error_message = :error_message,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :log_id
                """
                ),
                {
                    "completed_at": completed_at,
                    "duration": duration,
                    "success": success,
                    "error_message": error_message,
                    "log_id": log_id,
                },
            )


def _load_per_disease_views(app):
    with app.app_context():
        with transaction_scope() as db:
            return db.execute(
                text(
                    """
                    SELECT matviewname
                    FROM pg_matviews
                    WHERE schemaname = 'public'
                      AND matviewname LIKE 'mvw_image_listing_%_v2'
                    ORDER BY matviewname
                    """
                )
            ).scalars().all()


def _refresh_single_view(app, view_name):
    with app.app_context():
        with transaction_scope() as db:
            db.execute(text(f"REFRESH MATERIALIZED VIEW {view_name}"))


def refresh_ai_inference_runs_materialized_view() -> bool:
    """Refresh the WAI/API inference runs view after async inference writes."""
    try:
        with transaction_scope() as db:
            db.execute(text("REFRESH MATERIALIZED VIEW ai_inference_runs_mv"))
        return True
    except Exception:
        logger.exception("Failed to refresh ai_inference_runs_mv")
        return False


def refresh_materialized_view(app, schedule_time="manual"):
    """Execute all materialized view refreshes with proper timezone logging and timestamp tracking.

    Refreshes the following views in order:
    1. mvw_grading_data_all (general grading data)
    2. mvw_diabetic_retinopathy_grading_pivot (DR-specific pivoted data)
    3. mvw_glaucoma_grading_pivot (glaucoma-specific pivoted data)
    4. mvw_amd_grading_pivot (AMD-specific pivoted data)
    5. mvw_encounter_pivot (comprehensive encounter-centric analytics with individual image grade pivots)
    6. mvw_image_listing_all (comprehensive image catalog with upload types and verification status)
    7. ai_inference_runs_mv (normalized AI inference run analytics)

    Args:
        app: Flask application instance
        schedule_time: String identifier for the scheduled refresh time

    Returns:
        bool: True if all refreshes successful, False otherwise
    """
    timezone_str = app.config.get("MATERIALIZED_VIEW_TIMEZONE", app.config.get("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata"))
    tz = pytz.timezone(timezone_str)
    start_time = datetime.now(pytz.UTC)
    ist_time = datetime.now(tz)

    log_id = None
    try:
        logger.info(
            "Starting materialized view refresh - Schedule: %s",
            sanitize_log_value(schedule_time),
        )
        logger.info(
            "IST Time: %s",
            sanitize_log_value(ist_time.strftime('%Y-%m-%d %H:%M:%S %Z')),
        )
        logger.info(
            "UTC Time: %s",
            sanitize_log_value(start_time.strftime('%Y-%m-%d %H:%M:%S UTC')),
        )

        log_id = _create_refresh_log_entry(app, schedule_time, start_time)

        views_to_refresh = [
            ("mvw_grading_data_all", "General Grading Data"),
            ("mvw_diabetic_retinopathy_grading_pivot", "Diabetic Retinopathy Pivot"),
            ("mvw_glaucoma_grading_pivot", "Glaucoma Pivot"),
            ("mvw_amd_grading_pivot", "AMD Pivot"),
            ("mvw_encounter_pivot", "Encounter Pivot"),
            ("mvw_image_listing_all", "Image Listing All"),
            ("ai_inference_runs_mv", "AI Inference Runs"),
        ]
        per_disease_views = _load_per_disease_views(app)

        total_duration = 0
        successful_refreshes = 0

        for view_name, view_description in views_to_refresh:
            view_start_time = datetime.now(pytz.UTC)
            try:
                logger.info(
                    "Refreshing %s (%s)",
                    sanitize_log_value(view_description),
                    sanitize_log_value(view_name),
                )
                _refresh_single_view(app, view_name)
                view_duration = (datetime.now(pytz.UTC) - view_start_time).total_seconds()
                total_duration += view_duration
                successful_refreshes += 1
                logger.info(
                    "Successfully refreshed %s in %s seconds",
                    sanitize_log_value(view_description),
                    sanitize_log_value(f"{view_duration:.2f}"),
                )
            except Exception:
                logger.exception("Failed to refresh %s (%s)", view_description, view_name)

        for view_name in per_disease_views:
            view_start_time = datetime.now(pytz.UTC)
            try:
                logger.info(
                    "Refreshing Per-Disease Image Listing (%s)",
                    sanitize_log_value(view_name),
                )
                _refresh_single_view(app, view_name)
                view_duration = (datetime.now(pytz.UTC) - view_start_time).total_seconds()
                total_duration += view_duration
                successful_refreshes += 1
                logger.info(
                    "Successfully refreshed %s in %s seconds",
                    sanitize_log_value(view_name),
                    sanitize_log_value(f"{view_duration:.2f}"),
                )
            except Exception:
                logger.exception(
                    "Failed to refresh per-disease MV %s",
                    sanitize_log_value(view_name),
                )

        overall_duration = (datetime.now(pytz.UTC) - start_time).total_seconds()
        total_views = len(views_to_refresh) + len(per_disease_views)
        failed_refreshes = total_views - successful_refreshes
        success = failed_refreshes == 0
        _update_refresh_log_entry(
            app,
            log_id,
            datetime.now(pytz.UTC),
            overall_duration,
            success,
            None if success else f"Failed {failed_refreshes}/{total_views} views",
        )

        logger.info(
            "Materialized view refresh completed: %s/%s views successful in %s seconds - Schedule: %s",
            sanitize_log_value(successful_refreshes),
            sanitize_log_value(total_views),
            sanitize_log_value(f"{overall_duration:.2f}"),
            sanitize_log_value(schedule_time),
        )
        return success

    except Exception as e:
        logger.exception("Failed to refresh materialized views - Schedule: %s", schedule_time)

        # Update log entry with failure if we have a log_id
        if log_id:
            try:
                _update_refresh_log_entry(
                    app,
                    log_id,
                    datetime.now(pytz.UTC),
                    (datetime.now(pytz.UTC) - start_time).total_seconds(),
                    False,
                    str(e),
                )
            except Exception as log_error:
                logger.exception("Failed to update refresh log")

        return False


def refresh_image_listing_views(
    app,
    disease_id: int | None = None,
    schedule_time: str = "manual_image_listing",
    include_all: bool = True,
) -> bool:
    """Refresh only image-listing materialized views used by review/search pages."""
    start_time = datetime.now(pytz.UTC)
    view_names = ["mvw_image_listing_all"] if include_all else []
    with app.app_context():
        if disease_id:
            with transaction_scope() as db:
                from utils.mvw_image_listing_v2 import get_mv_name_for_disease

                view_names.append(get_mv_name_for_disease(db, int(disease_id)))
        else:
            view_names.extend(_load_per_disease_views(app))

    seen = set()
    ordered_view_names = []
    for view_name in view_names:
        if view_name not in seen:
            ordered_view_names.append(view_name)
            seen.add(view_name)

    successful_refreshes = 0
    for view_name in ordered_view_names:
        view_start_time = datetime.now(pytz.UTC)
        try:
            logger.info(
                "Refreshing Image Listing MV (%s) - Schedule: %s",
                sanitize_log_value(view_name),
                sanitize_log_value(schedule_time),
            )
            _refresh_single_view(app, view_name)
            successful_refreshes += 1
            logger.info(
                "Successfully refreshed %s in %s seconds",
                sanitize_log_value(view_name),
                sanitize_log_value(f"{(datetime.now(pytz.UTC) - view_start_time).total_seconds():.2f}"),
            )
        except Exception:
            logger.exception(
                "Failed to refresh image-listing MV %s",
                sanitize_log_value(view_name),
            )

    success = successful_refreshes == len(ordered_view_names)
    logger.info(
        "Image-listing MV refresh completed: %s/%s views successful in %s seconds - Schedule: %s",
        sanitize_log_value(successful_refreshes),
        sanitize_log_value(len(ordered_view_names)),
        sanitize_log_value(f"{(datetime.now(pytz.UTC) - start_time).total_seconds():.2f}"),
        sanitize_log_value(schedule_time),
    )
    return success


def run_scheduler_thread(app):
    """Main scheduler daemon thread following existing stuck task cleanup pattern.

    Args:
        app: Flask application instance
    """
    timezone_str = app.config.get("MATERIALIZED_VIEW_TIMEZONE", app.config.get("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata"))
    tz = pytz.timezone(timezone_str)
    schedule_times = app.config.get(
        "MATERIALIZED_VIEW_SCHEDULE_TIMES",
        [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)],
    )

    # Handle both string and list inputs
    if isinstance(schedule_times, str):
        schedule_times = schedule_times.split(",")

    retry_attempts = app.config.get("MATERIALIZED_VIEW_RETRY_ATTEMPTS", 3)
    retry_delay = app.config.get("MATERIALIZED_VIEW_RETRY_DELAY_SECONDS", 60)

    logger.info(
        "Materialized view scheduler started - Times: %s, Timezone: %s",
        sanitize_log_value(schedule_times),
        sanitize_log_value(timezone_str),
    )

    last_trigger_time = None
    last_trigger_date = None

    while True:
        try:
            current_ist = datetime.now(tz)
            current_time_str = current_ist.strftime("%H:%M")

            # Check if current time matches any scheduled time (on the hour)
            if (
                current_time_str in schedule_times
                and (last_trigger_time != current_time_str or last_trigger_date != current_ist.date())
            ):
                last_trigger_time = current_time_str
                last_trigger_date = current_ist.date()
                logger.info(
                    "Scheduled refresh time reached: %s IST",
                    sanitize_log_value(current_time_str),
                )

                # Retry logic with exponential backoff
                for attempt in range(retry_attempts):
                    if refresh_materialized_view(app, current_time_str):
                        break
                    elif attempt < retry_attempts - 1:
                        wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                        logger.warning(
                            "Refresh attempt %s failed, retrying in %s seconds...",
                            sanitize_log_value(attempt + 1),
                            sanitize_log_value(wait_time),
                        )
                        time.sleep(wait_time)

            # Check every 30 seconds to catch schedule changes
            time.sleep(30)

        except Exception as e:
            logger.error(
                "Scheduler thread error: %s",
                sanitize_log_value(e),
            )
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
                    mapping = result._mapping if hasattr(result, "_mapping") else None
                    def _get(key, fallback=None):
                        if mapping is not None:
                            return mapping.get(key, fallback)
                        try:
                            # fallback to tuple unpacking by index order
                            columns = [
                                "refresh_type",
                                "refresh_started_at",
                                "refresh_completed_at",
                                "refresh_duration_seconds",
                                "success",
                                "error_message",
                                "created_at",
                                "updated_at",
                            ]
                            idx = columns.index(key)
                            return result[idx]
                        except Exception:
                            return fallback

                    # Parse timestamps
                    timezone_str = app.config.get("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata")
                    tz = pytz.timezone(timezone_str)

                    refresh_started_utc = _get('refresh_started_at')
                    if refresh_started_utc:
                        if hasattr(refresh_started_utc, 'astimezone'):
                            refresh_started_utc = refresh_started_utc.astimezone(tz)
                        else:
                            refresh_started_utc = pytz.utc.localize(refresh_started_utc).astimezone(tz)

                    refresh_completed_utc = _get('refresh_completed_at')
                    if refresh_completed_utc:
                        if hasattr(refresh_completed_utc, 'astimezone'):
                            refresh_completed_utc = refresh_completed_utc.astimezone(tz)
                        else:
                            refresh_completed_utc = pytz.utc.localize(refresh_completed_utc).astimezone(tz)

                    return {
                        'has_data': True,
                        'refresh_type': _get('refresh_type'),
                        'refresh_started_at': refresh_started_utc.strftime('%Y-%m-%d %H:%M:%S %Z') if refresh_started_utc else None,
                        'refresh_completed_at': refresh_completed_utc.strftime('%Y-%m-%d %H:%M:%S %Z') if refresh_completed_utc else None,
                        'refresh_duration_seconds': _get('refresh_duration_seconds'),
                        'success': _get('success'),
                        'error_message': _get('error_message'),
                        'ist_time': refresh_completed_utc.strftime('%Y-%m-%d %H:%M:%S IST') if refresh_completed_utc else None,
                        'utc_time': _get('refresh_completed_at').strftime('%Y-%m-%d %H:%M:%S UTC') if _get('refresh_completed_at') else None,
                        'data_freshness_minutes': round((datetime.now(pytz.UTC) - _get('refresh_completed_at').astimezone(pytz.UTC)).total_seconds() / 60, 1) if _get('refresh_completed_at') else None
                    }
                else:
                    return {
                        'has_data': False,
                        'message': 'No refresh history found'
                    }

    except Exception as e:
        logger.error(
            "Failed to get last refresh info: %s",
            sanitize_log_value(e),
        )
        return {
            'has_data': False,
            'error': str(e)
        }
