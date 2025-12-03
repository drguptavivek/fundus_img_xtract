"""Materialized View Status Admin Routes

Admin routes for monitoring and managing the materialized view refresh scheduler.
This handles ALL materialized views including:
- mvw_grading_data_all (general grading data)
- mvw_diabetic_retinopathy_grading_pivot (DR-specific pivoted data)
- mvw_glaucoma_grading_pivot (glaucoma-specific pivoted data)
- mvw_amd_grading_pivot (AMD-specific pivoted data)
"""

from flask import jsonify, request, current_app
from auth.roles import roles_required
from utils.materialized_view_scheduler import get_last_refresh_info, manual_refresh_now, get_scheduler_status
from flask_login import login_required, current_user


@login_required
@roles_required("admin")
def materialized_view_status():
    """Display status for all materialized view refreshes and information."""
    from flask import render_template, request
    from utils.datetime_filters import format_user_datetime

    # Get scheduler status
    scheduler_status = get_scheduler_status(current_app)

    # Get detailed refresh history
    try:
        from db_transaction_manager import transaction_scope
        from sqlalchemy import text

        with current_app.app_context():
            with transaction_scope() as db:
                # Get recent refresh history (last 50 entries)
                result = db.execute(text("""
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
                    LIMIT 50
                """)).fetchall()

                # Process the data for template display
                refresh_history = []
                for row in result:
                    # Convert UTC times to user's timezone
                    timezone_str = current_app.config.get("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata")

                    # Access row data by index (tuple format)
                    refresh_type, refresh_started_at, refresh_completed_at, refresh_duration_seconds, success, error_message, created_at, updated_at = row

                    if refresh_started_at:
                        started_at = format_user_datetime(refresh_started_at)
                    else:
                        started_at = None

                    if refresh_completed_at:
                        completed_at = format_user_datetime(refresh_completed_at)
                    else:
                        completed_at = None

                    # Calculate data freshness
                    data_freshness = None
                    if refresh_completed_at:
                        from datetime import datetime, timedelta
                        import pytz

                        # Create timezone-aware UTC now
                        utc_now = datetime.now(pytz.UTC)
                        completed_at_utc = refresh_completed_at

                        # Ensure completed_at_utc is timezone-aware
                        if completed_at_utc.tzinfo is None:
                            completed_at_utc = pytz.utc.localize(completed_at_utc)
                        else:
                            # Convert to UTC if it's in a different timezone
                            completed_at_utc = completed_at_utc.astimezone(pytz.UTC)

                        data_freshness = round((utc_now - completed_at_utc).total_seconds() / 60, 1)

                    refresh_history.append({
                        'refresh_type': refresh_type,
                        'started_at': started_at,
                        'completed_at': completed_at,
                        'duration_seconds': refresh_duration_seconds,
                        'success': success,
                        'error_message': error_message,
                        'data_freshness_minutes': data_freshness,
                        'created_at': format_user_datetime(created_at),
                        'updated_at': format_user_datetime(updated_at)
                    })

                # Get refresh statistics
                stats_result = db.execute(text("""
                    SELECT
                        COUNT(*) as total_refreshes,
                        COUNT(*) FILTER (WHERE success = TRUE) as successful_refreshes,
                        COUNT(*) FILTER (WHERE success = FALSE) as failed_refreshes,
                        AVG(refresh_duration_seconds) FILTER (WHERE success = TRUE) as avg_duration,
                        MAX(refresh_duration_seconds) as max_duration,
                        MIN(refresh_duration_seconds) as min_duration
                    FROM materialized_view_refresh_log
                    WHERE materialized_view_name = 'mvw_grading_data_all'
                """)).fetchone()

                # Access stats by index (tuple format)
                total_refreshes, successful_refreshes, failed_refreshes, avg_duration, max_duration, min_duration = stats_result

                refresh_stats = {
                    'total_refreshes': total_refreshes,
                    'successful_refreshes': successful_refreshes,
                    'failed_refreshes': failed_refreshes,
                    'avg_duration': round(avg_duration, 2) if avg_duration else 0,
                    'max_duration': max_duration,
                    'min_duration': min_duration,
                    'success_rate': round((successful_refreshes / total_refreshes * 100), 1) if total_refreshes > 0 else 0
                }

    except Exception as e:
        current_app.logger.error(f"Error fetching materialized view status: {str(e)}")
        refresh_history = []
        refresh_stats = {
            'total_refreshes': 0,
            'successful_refreshes': 0,
            'failed_refreshes': 0,
            'avg_duration': 0,
            'max_duration': 0,
            'min_duration': 0,
            'success_rate': 0
        }

    return render_template(
        "admin/materialized_view_status.html",
        scheduler_status=scheduler_status,
        last_refresh_info=scheduler_status.get('last_refresh', {}),
        refresh_history=refresh_history,
        refresh_stats=refresh_stats,
        current_user=current_user
    )


@login_required
@roles_required("admin")
def api_materialized_view_status():
    """API endpoint to get materialized view status information."""
    try:
        scheduler_status = get_scheduler_status(current_app)
        return jsonify({
            'success': True,
            'data': scheduler_status
        })
    except Exception as e:
        current_app.logger.error(f"Error in API materialized view status: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@login_required
@roles_required("admin")
def api_last_refresh():
    """API endpoint to get last refresh information."""
    try:
        last_refresh_info = get_last_refresh_info(current_app)
        return jsonify({
            'success': True,
            'data': last_refresh_info
        })
    except Exception as e:
        current_app.logger.error(f"Error in API last refresh: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@login_required
@roles_required("admin")
def manual_refresh():
    """Manual refresh trigger for all materialized views."""
    try:
        result = manual_refresh_now(current_app)
        return jsonify({
            'success': result['success'],
            'message': result['message']
        })
    except Exception as e:
        current_app.logger.exception("Error in manual refresh")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@login_required
@roles_required("admin")
def api_schedule_status():
    """API endpoint to get detailed schedule status."""
    try:
        scheduler_status = get_scheduler_status(current_app)
        return jsonify({
            'success': True,
            'data': {
                'current_time': {
                    'ist': scheduler_status.get('current_ist'),
                    'utc': scheduler_status.get('current_utc')
                },
                'timezone': scheduler_status.get('timezone'),
                'enabled': scheduler_status.get('enabled'),
                'schedule_times': scheduler_status.get('schedule_times'),
                'frequency': scheduler_status.get('frequency'),
                'next_refresh': scheduler_status.get('next_runs', [{}])[0] if scheduler_status.get('next_runs') else None
            }
        })
    except Exception as e:
        current_app.logger.error(f"Error in API schedule status: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
