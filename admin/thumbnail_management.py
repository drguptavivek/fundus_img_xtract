"""Thumbnail Management Admin Routes

Admin routes for monitoring and managing the thumbnail system including:
- Thumbnail generation status
- Maintenance task scheduling and execution
- Storage usage and optimization
- Integrity validation and reporting
- Manual cleanup and regeneration operations
"""

from flask import jsonify, request, current_app, render_template
from auth.roles import roles_required
from flask_login import login_required, current_user
from datetime import datetime, timedelta

from utils.thumbnail_maintenance_scheduler import (
    cleanup_orphaned_thumbnails,
    regenerate_missing_thumbnails,
    validate_thumbnail_integrity,
    run_maintenance_tasks,
    trigger_manual_maintenance,
    get_maintenance_status
)
import pytz
from db_transaction_manager import transaction_scope
from models import DirectImageUpload, EncounterFile
from sqlalchemy import text, func


@login_required
@roles_required("admin", "data_manager")
def thumbnail_management():
    """Display thumbnail management dashboard with status and controls."""
    from utils.datetime_filters import format_user_datetime

    # Get current maintenance status
    maintenance_status = get_maintenance_status()

    # Get thumbnail statistics
    stats = get_thumbnail_statistics()

    # Get recent maintenance history (mock data for now - would be stored in DB)
    recent_history = get_recent_maintenance_history()

    # Check scheduler status
    scheduler_enabled = current_app.config.get("THUMBNAIL_MAINTENANCE_ENABLED", False)

    return render_template(
        "admin/thumbnail_management.html",
        maintenance_status=maintenance_status,
        thumbnail_stats=stats,
        recent_history=recent_history,
        scheduler_enabled=scheduler_enabled,
        format_user_datetime=format_user_datetime,
    )


def get_thumbnail_statistics():
    """Get comprehensive thumbnail statistics."""
    stats = {
        'direct_uploads': {
            'total': 0,
            'with_original_thumbnails': 0,
            'with_edited_thumbnails': 0,
            'missing_thumbnails': 0
        },
        'encounter_files': {
            'total': 0,
            'with_thumbnails': 0,
            'missing_thumbnails': 0
        },
        'storage': {
            'estimated_thumbnail_size_mb': 0,
            'potential_space_saving_mb': 0
        }
    }

    try:
        # Direct Upload statistics
        with transaction_scope() as db:
            direct_total = db.query(DirectImageUpload).count()
            direct_with_original = db.query(DirectImageUpload).filter(
                DirectImageUpload.thumbnail_filename.isnot(None)
            ).count()
            direct_with_edited = db.query(DirectImageUpload).filter(
                DirectImageUpload.edited_thumbnail_filename.isnot(None)
            ).count()

            stats['direct_uploads'] = {
                'total': direct_total,
                'with_original_thumbnails': direct_with_original,
                'with_edited_thumbnails': direct_with_edited,
                'missing_thumbnails': direct_total - direct_with_original
            }

        # Encounter File statistics
        with transaction_scope() as db:
            encounter_total = db.query(EncounterFile).count()
            encounter_with_thumbnails = db.query(EncounterFile).filter(
                EncounterFile.thumbnail_filename.isnot(None)
            ).count()

            stats['encounter_files'] = {
                'total': encounter_total,
                'with_thumbnails': encounter_with_thumbnails,
                'missing_thumbnails': encounter_total - encounter_with_thumbnails
            }

        # Storage estimation (rough calculation)
        # Assuming average thumbnail size is ~5KB
        total_thumbnails = direct_with_original + direct_with_edited + encounter_with_thumbnails
        stats['storage']['estimated_thumbnail_size_mb'] = round(total_thumbnails * 5 / 1024, 2)

        # Potential space saving from orphaned cleanup
        stats['storage']['potential_space_saving_mb'] = round(
            stats['storage']['estimated_thumbnail_size_mb'] * 0.1, 2  # Assume 10% might be orphaned
        )

    except Exception as e:
        current_app.logger.error(f"Error calculating thumbnail statistics: {str(e)}")

    return stats


def get_recent_maintenance_history(limit=20):
    """Get recent maintenance operation history.

    Returns list of mock maintenance records (would normally come from database)
    """
    # This would normally query a maintenance log table
    # For now, return mock data
    mock_history = [
        {
            'timestamp': datetime.now(pytz.utc) - timedelta(hours=2),
            'task_type': 'cleanup',
            'status': 'success',
            'details': 'Removed 5 orphaned thumbnails',
            'duration_seconds': 12.5
        },
        {
            'timestamp': datetime.now(pytz.utc) - timedelta(hours=6),
            'task_type': 'regeneration',
            'status': 'success',
            'details': 'Generated 15 missing thumbnails',
            'duration_seconds': 45.2
        },
        {
            'timestamp': datetime.now(pytz.utc) - timedelta(hours=12),
            'task_type': 'validation',
            'status': 'success',
            'details': 'Validated 100 thumbnails, 98% consistent',
            'duration_seconds': 8.3
        },
        {
            'timestamp': datetime.now(pytz.utc) - timedelta(days=1),
            'task_type': 'full_cycle',
            'status': 'success',
            'details': 'Completed full maintenance cycle',
            'duration_seconds': 67.8
        }
    ]

    return mock_history[:limit]


@login_required
@roles_required("admin", "data_manager")
def api_thumbnail_stats():
    """API endpoint for thumbnail statistics."""
    try:
        stats = get_thumbnail_statistics()
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        current_app.logger.error(f"Error getting thumbnail stats: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@login_required
@roles_required("admin", "data_manager")
def api_maintenance_status():
    """API endpoint for current maintenance status."""
    try:
        status = get_maintenance_status()
        return jsonify({
            'success': True,
            'status': status
        })
    except Exception as e:
        current_app.logger.error(f"Error getting maintenance status: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@login_required
@roles_required("admin", "data_manager")
def api_manual_maintenance():
    """API endpoint to trigger manual maintenance tasks."""
    data = request.get_json() or {}
    task_type = data.get('task_type', 'all')

    try:
        result = trigger_manual_maintenance(task_type)
        return jsonify({
            'success': result.get('success', False),
            'task_type': task_type,
            'result': result
        })
    except Exception as e:
        current_app.logger.error(f"Error triggering manual maintenance: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'task_type': task_type
        }), 500


@login_required
@roles_required("admin", "data_manager")
def api_cleanup_orphaned():
    """API endpoint to run orphaned thumbnail cleanup."""
    try:
        result = cleanup_orphaned_thumbnails(current_app, "manual")
        return jsonify({
            'success': result.get('success', False),
            'result': result
        })
    except Exception as e:
        current_app.logger.error(f"Error running orphaned cleanup: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@login_required
@roles_required("admin", "data_manager")
def api_regenerate_missing():
    """API endpoint to regenerate missing thumbnails."""
    data = request.get_json() or {}
    limit = min(int(data.get('limit', 50)), 200)  # Cap at 200

    try:
        result = regenerate_missing_thumbnails(current_app, "manual", limit=limit)
        return jsonify({
            'success': result.get('success', False),
            'result': result
        })
    except Exception as e:
        current_app.logger.error(f"Error regenerating missing thumbnails: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@login_required
@roles_required("admin", "data_manager")
def api_validate_integrity():
    """API endpoint to validate thumbnail integrity."""
    data = request.get_json() or {}
    sample_size = min(int(data.get('sample_size', 100)), 500)  # Cap at 500

    try:
        result = validate_thumbnail_integrity(current_app, "manual", sample_size=sample_size)
        return jsonify({
            'success': result.get('success', False),
            'result': result
        })
    except Exception as e:
        current_app.logger.error(f"Error validating thumbnail integrity: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@login_required
@roles_required("admin", "data_manager")
def api_full_maintenance():
    """API endpoint to run full maintenance cycle."""
    try:
        result = run_maintenance_tasks(current_app)
        return jsonify({
            'success': result.get('overall_success', False),
            'result': result
        })
    except Exception as e:
        current_app.logger.error(f"Error running full maintenance: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def get_system_health():
    """Get comprehensive system health status for admin dashboard."""
    try:
        health_status = {
            'status': 'healthy',
            'issues': [],
            'recommendations': [],
            'performance_metrics': {}
        }

        # Check database connectivity
        with transaction_scope() as db:
            try:
                db.execute(text("SELECT 1")).fetchone()
            except Exception as e:
                health_status['status'] = 'error'
                health_status['issues'].append(f"Database connectivity error: {str(e)}")

        # Check scheduler status
        scheduler_enabled = current_app.config.get("THUMBNAIL_MAINTENANCE_ENABLED", False)
        if not scheduler_enabled:
            if health_status['status'] == 'healthy':
                health_status['status'] = 'warning'
            health_status['issues'].append("Thumbnail maintenance scheduler is disabled")
            health_status['recommendations'].append("Enable THUMBNAIL_MAINTENANCE_ENABLED in configuration")

        # Check for large number of missing thumbnails
        stats = get_thumbnail_statistics()
        total_missing = (
            stats['direct_uploads']['missing_thumbnails'] +
            stats['encounter_files']['missing_thumbnails']
        )

        if total_missing > 1000:
            if health_status['status'] == 'healthy':
                health_status['status'] = 'warning'
            health_status['issues'].append(f"High number of missing thumbnails: {total_missing}")
            health_status['recommendations'].append("Run manual thumbnail regeneration")

        # Check storage usage for orphaned thumbnails
        if total_missing > 100:
            health_status['recommendations'].append("Consider running orphaned cleanup to free up space")

        # Add performance metrics
        health_status['performance_metrics'] = {
            'missing_thumbnail_ratio': total_missing / max(1, stats['direct_uploads']['total'] + stats['encounter_files']['total']),
            'scheduler_enabled': scheduler_enabled,
            'total_images_processed': stats['direct_uploads']['total'] + stats['encounter_files']['total']
        }

        return health_status

    except Exception as e:
        current_app.logger.error(f"Error getting system health: {str(e)}")
        return {
            'status': 'error',
            'issues': [f"Health check failed: {str(e)}"],
            'recommendations': ['Check application logs', 'Verify system configuration'],
            'performance_metrics': {}
        }


@login_required
@roles_required("admin", "data_manager")
def api_thumbnail_health_check():
    """API endpoint for thumbnail system health check."""
    try:
        health_status = {
            'overall_health': 'healthy',
            'issues': [],
            'recommendations': []
        }

        # Check database connectivity
        with transaction_scope() as db:
            try:
                db.execute(text("SELECT 1")).fetchone()
            except Exception as e:
                health_status['overall_health'] = 'unhealthy'
                health_status['issues'].append(f"Database connectivity error: {str(e)}")

        # Check scheduler status
        scheduler_enabled = current_app.config.get("THUMBNAIL_MAINTENANCE_ENABLED", False)
        if not scheduler_enabled:
            health_status['overall_health'] = 'warning'
            health_status['issues'].append("Thumbnail maintenance scheduler is disabled")
            health_status['recommendations'].append("Enable THUMBNAIL_MAINTENANCE_ENABLED in configuration")

        # Check for large number of missing thumbnails
        stats = get_thumbnail_statistics()
        total_missing = (
            stats['direct_uploads']['missing_thumbnails'] +
            stats['encounter_files']['missing_thumbnails']
        )

        if total_missing > 1000:
            health_status['overall_health'] = 'warning'
            health_status['issues'].append(f"High number of missing thumbnails: {total_missing}")
            health_status['recommendations'].append("Run manual thumbnail regeneration")

        # Check storage usage
        if stats['storage']['estimated_thumbnail_size_mb'] > 1000:  # > 1GB
            health_status['recommendations'].append("Consider running orphaned cleanup to free up space")

        # Check log file rotation (basic check)
        import os
        log_dir = current_app.config.get('LOG_DIR', '/app/logs')
        log_file = os.path.join(log_dir, 'thumbnail_maintenance.log')
        if os.path.exists(log_file):
            file_size = os.path.getsize(log_file)
            if file_size > 50 * 1024 * 1024:  # > 50MB
                health_status['recommendations'].append("Consider log file rotation for thumbnail maintenance logs")

        return jsonify({
            'success': True,
            'health_status': health_status,
            'timestamp': datetime.now(pytz.utc).isoformat()
        })

    except Exception as e:
        current_app.logger.error(f"Error in thumbnail health check: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'overall_health': 'error'
        }), 500


# Admin route registration helper
def register_thumbnail_admin_routes(bp):
    """Register thumbnail management routes with a Flask blueprint."""

    # Main dashboard
    bp.add_url_rule(
        '/admin/thumbnail_management',
        'thumbnail_management',
        thumbnail_management,
        methods=['GET']
    )

    # API endpoints
    bp.add_url_rule(
        '/api/thumbnail_stats',
        'api_thumbnail_stats',
        api_thumbnail_stats,
        methods=['GET']
    )

    bp.add_url_rule(
        '/api/maintenance_status',
        'api_maintenance_status',
        api_maintenance_status,
        methods=['GET']
    )

    bp.add_url_rule(
        '/api/thumbnail/manual_maintenance',
        'api_manual_maintenance',
        api_manual_maintenance,
        methods=['POST']
    )

    bp.add_url_rule(
        '/api/thumbnail/cleanup_orphaned',
        'api_cleanup_orphaned',
        api_cleanup_orphaned,
        methods=['POST']
    )

    bp.add_url_rule(
        '/api/thumbnail/regenerate_missing',
        'api_regenerate_missing',
        api_regenerate_missing,
        methods=['POST']
    )

    bp.add_url_rule(
        '/api/thumbnail/validate_integrity',
        'api_validate_integrity',
        api_validate_integrity,
        methods=['POST']
    )

    bp.add_url_rule(
        '/api/thumbnail/full_maintenance',
        'api_full_maintenance',
        api_full_maintenance,
        methods=['POST']
    )

    bp.add_url_rule(
        '/api/thumbnail/health_check',
        'api_thumbnail_health_check',
        api_thumbnail_health_check,
        methods=['GET']
    )