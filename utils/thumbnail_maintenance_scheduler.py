"""
Thumbnail Maintenance Scheduler

Timezone-aware scheduler for automatic thumbnail maintenance tasks including:
- Orphaned thumbnail cleanup
- Missing thumbnail regeneration
- Thumbnail integrity validation
- Storage optimization
- Health monitoring and alerting

Integrates with existing Flask application infrastructure including logging,
database sessions, and background task patterns.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

import pytz
from sqlalchemy import text
from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger("thumbnail_maintenance")


def cleanup_orphaned_thumbnails(app, schedule_time="manual"):
    """Execute orphaned thumbnail cleanup with proper timezone logging and statistics tracking.

    This function removes thumbnail files that no longer have corresponding
    parent images in the database or on disk.

    Args:
        app: Flask application instance
        schedule_time: String identifier for the scheduled cleanup time

    Returns:
        dict: Cleanup statistics and status
    """
    from utils.thumbnail_cleanup import cleanup_all_thumbnails_for_missing_images

    timezone_str = app.config.get("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata")
    tz = pytz.timezone(timezone_str)
    start_time = datetime.now(pytz.UTC)
    local_time = datetime.now(tz)

    logger.info(
        "Starting orphaned thumbnail cleanup - IST: %s, UTC: %s, Schedule: %s",
        sanitize_log_value(local_time.strftime('%Y-%m-%d %H:%M:%S')),
        sanitize_log_value(start_time.strftime('%Y-%m-%d %H:%M:%S')),
        sanitize_log_value(schedule_time),
    )

    try:
        # Run comprehensive cleanup
        cleanup_results = cleanup_all_thumbnails_for_missing_images()

        duration = datetime.now(pytz.UTC) - start_time
        local_time_end = datetime.now(tz)

        # Log detailed results
        logger.info(
            "Orphaned thumbnail cleanup completed - Duration: %ss, End IST: %s",
            sanitize_log_value(f"{duration.total_seconds():.2f}"),
            sanitize_log_value(local_time_end.strftime('%Y-%m-%d %H:%M:%S')),
        )

        logger.info(
            "Cleanup Statistics - File orphans found: %s, File orphans removed: %s, "
            "Reference thumbnails checked: %s, Total errors: %s",
            sanitize_log_value(cleanup_results.get('file_orphans_found', 0)),
            sanitize_log_value(cleanup_results.get('file_orphans_removed', 0)),
            sanitize_log_value(cleanup_results.get('ref_thumbnails_checked', 0)),
            sanitize_log_value(len(cleanup_results.get('total_errors', []))),
        )

        # Log any errors
        errors = cleanup_results.get('total_errors', [])
        if errors:
            logger.warning(
                "Thumbnail cleanup had %s errors:",
                sanitize_log_value(len(errors)),
            )
            for error in errors:
                logger.warning(
                    "  - %s",
                    sanitize_log_value(error),
                )
        else:
            logger.info("Thumbnail cleanup completed successfully with no errors")

        return {
            'success': True,
            'schedule_time': schedule_time,
            'duration_seconds': duration.total_seconds(),
            'file_orphans_found': cleanup_results.get('file_orphans_found', 0),
            'file_orphans_removed': cleanup_results.get('file_orphans_removed', 0),
            'ref_thumbnails_checked': cleanup_results.get('ref_thumbnails_checked', 0),
            'errors': errors,
            'start_time_utc': start_time.isoformat(),
            'end_time_utc': datetime.now(pytz.UTC).isoformat()
        }

    except Exception as e:
        duration = datetime.now(pytz.UTC) - start_time
        logger.error(
            "Orphaned thumbnail cleanup failed after %ss: %s",
            sanitize_log_value(f"{duration.total_seconds():.2f}"),
            sanitize_log_value(e),
        )

        return {
            'success': False,
            'schedule_time': schedule_time,
            'duration_seconds': duration.total_seconds(),
            'error': str(e),
            'start_time_utc': start_time.isoformat(),
            'end_time_utc': datetime.now(pytz.UTC).isoformat()
        }


def regenerate_missing_thumbnails(app, schedule_time="manual", limit=100):
    """Regenerate thumbnails for images that are missing thumbnails.

    This function identifies images that should have thumbnails but don't,
    and creates them using the background job system.

    Args:
        app: Flask application instance
        schedule_time: String identifier for the scheduled run
        limit: Maximum number of thumbnails to generate per run

    Returns:
        dict: Regeneration statistics and status
    """
    from db_transaction_manager import transaction_scope
    from models import DirectImageUpload, EncounterFile
    from utils.thumbnail_integration import trigger_direct_upload_thumbnails, trigger_encounter_thumbnails

    timezone_str = app.config.get("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata")
    tz = pytz.timezone(timezone_str)
    start_time = datetime.now(pytz.UTC)
    local_time = datetime.now(tz)

    logger.info(
        f"Starting missing thumbnail regeneration - IST: {local_time.strftime('%Y-%m-%d %H:%M:%S')}, "
        f"UTC: {start_time.strftime('%Y-%m-%d %H:%M:%S')}, Schedule: {schedule_time}, Limit: {limit}"
    )

    stats = {
        'direct_uploads_processed': 0,
        'direct_uploads_triggered': 0,
        'encounter_files_processed': 0,
        'encounter_files_triggered': 0,
        'total_processed': 0,
        'total_triggered': 0,
        'errors': []
    }

    try:
        remaining_direct = max(limit, 0)

        # Process DirectImageUpload records missing thumbnails
        with transaction_scope() as db:
            # Prioritise originals, then edited, respecting the overall limit
            direct_missing_original = db.query(DirectImageUpload).filter(
                DirectImageUpload.thumbnail_filename.is_(None),
                DirectImageUpload.filename.isnot(None)
            ).limit(remaining_direct).all()
            remaining_direct -= len(direct_missing_original)

            direct_missing_edited = []
            if remaining_direct > 0:
                direct_missing_edited = db.query(DirectImageUpload).filter(
                    DirectImageUpload.edited_thumbnail_filename.is_(None),
                    DirectImageUpload.edited_filename.isnot(None)
                ).limit(remaining_direct).all()

            stats['direct_uploads_processed'] = len(direct_missing_original) + len(direct_missing_edited)

            # Trigger thumbnail generation for direct uploads
            system_ctx = {
                'user_id': None,
                'username': 'system',
                'ip': '127.0.0.1',
            }

            for direct_upload in direct_missing_original:
                try:
                    trigger_direct_upload_thumbnails(direct_upload.id, app, system_ctx)
                    stats['direct_uploads_triggered'] += 1
                except Exception as e:
                    stats['errors'].append(f"Direct upload {direct_upload.id}: {str(e)}")

            for direct_upload in direct_missing_edited:
                try:
                    trigger_direct_upload_thumbnails(direct_upload.id, app, system_ctx)
                    stats['direct_uploads_triggered'] += 1
                except Exception as e:
                    stats['errors'].append(f"Direct upload {direct_upload.id}: {str(e)}")

        # Process EncounterFile records missing thumbnails using remaining capacity
        remaining_for_encounters = max(limit - stats['direct_uploads_triggered'], 0)
        if remaining_for_encounters > 0:
            with transaction_scope() as db:
                encounter_missing = db.query(EncounterFile).filter(
                    EncounterFile.thumbnail_filename.is_(None),
                    EncounterFile.filename.isnot(None)
                ).limit(remaining_for_encounters).all()

                stats['encounter_files_processed'] = len(encounter_missing)

                # Trigger thumbnail generation for encounter files
                encounter_file_ids = [ef.id for ef in encounter_missing]
                if encounter_file_ids:
                    try:
                        trigger_encounter_thumbnails(
                            encounter_file_ids,
                            app,
                            user_context={
                                'user_id': None,
                                'username': 'system',
                                'ip': '127.0.0.1',
                            },
                        )
                        stats['encounter_files_triggered'] = len(encounter_file_ids)
                    except Exception as e:
                        stats['errors'].append(f"Encounter files batch: {str(e)}")

        stats['total_processed'] = stats['direct_uploads_processed'] + stats['encounter_files_processed']
        stats['total_triggered'] = stats['direct_uploads_triggered'] + stats['encounter_files_triggered']

        duration = datetime.now(pytz.UTC) - start_time
        local_time_end = datetime.now(tz)

        logger.info(
            "Missing thumbnail regeneration completed - Duration: %ss, End IST: %s",
            sanitize_log_value(f"{duration.total_seconds():.2f}"),
            sanitize_log_value(local_time_end.strftime('%Y-%m-%d %H:%M:%S')),
        )

        logger.info(
            "Regeneration Statistics - Direct uploads processed: %s, Direct uploads triggered: %s, "
            "Encounter files processed: %s, Encounter files triggered: %s, Total triggered: %s, Errors: %s",
            sanitize_log_value(stats['direct_uploads_processed']),
            sanitize_log_value(stats['direct_uploads_triggered']),
            sanitize_log_value(stats['encounter_files_processed']),
            sanitize_log_value(stats['encounter_files_triggered']),
            sanitize_log_value(stats['total_triggered']),
            sanitize_log_value(len(stats['errors'])),
        )

        # Log any errors
        if stats['errors']:
            logger.warning(
                "Thumbnail regeneration had %s errors:",
                sanitize_log_value(len(stats['errors'])),
            )
            for error in stats['errors']:
                logger.warning(
                    "  - %s",
                    sanitize_log_value(error),
                )
        else:
            logger.info("Thumbnail regeneration completed successfully with no errors")

        return {
            'success': True,
            'schedule_time': schedule_time,
            'limit': limit,
            'duration_seconds': duration.total_seconds(),
            **stats,
            'start_time_utc': start_time.isoformat(),
            'end_time_utc': datetime.now(pytz.UTC).isoformat()
        }

    except Exception as e:
        duration = datetime.now(pytz.UTC) - start_time
        logger.error(
            "Missing thumbnail regeneration failed after %ss: %s",
            sanitize_log_value(f"{duration.total_seconds():.2f}"),
            sanitize_log_value(e),
        )

        return {
            'success': False,
            'schedule_time': schedule_time,
            'limit': limit,
            'duration_seconds': duration.total_seconds(),
            'error': str(e),
            'start_time_utc': start_time.isoformat(),
            'end_time_utc': datetime.now(pytz.UTC).isoformat()
        }


def validate_thumbnail_integrity(app, schedule_time="manual", sample_size=100):
    """Validate thumbnail integrity by checking consistency between database and files.

    Args:
        app: Flask application instance
        schedule_time: String identifier for the scheduled run
        sample_size: Maximum number of records to validate per run

    Returns:
        dict: Validation statistics and status
    """
    from db_transaction_manager import transaction_scope
    from models import DirectImageUpload, EncounterFile
    from utils.fileUtils import (
        thumbnail_exists_direct, thumbnail_exists_encounter,
        get_thumbnail_path_direct, get_thumbnail_path_encounter
    )

    timezone_str = app.config.get("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata")
    tz = pytz.timezone(timezone_str)
    start_time = datetime.now(pytz.UTC)
    local_time = datetime.now(tz)

    logger.info(
        f"Starting thumbnail integrity validation - IST: {local_time.strftime('%Y-%m-%d %H:%M:%S')}, "
        f"UTC: {start_time.strftime('%Y-%m-%d %H:%M:%S')}, Schedule: {schedule_time}, Sample size: {sample_size}"
    )

    stats = {
        'direct_uploads_checked': 0,
        'direct_uploads_consistent': 0,
        'direct_uploads_inconsistent': 0,
        'encounter_files_checked': 0,
        'encounter_files_consistent': 0,
        'encounter_files_inconsistent': 0,
        'total_checked': 0,
        'total_consistent': 0,
        'total_inconsistent': 0,
        'inconsistencies': []
    }

    try:
        # Validate DirectImageUpload records
        with transaction_scope() as db:
            direct_uploads = db.query(DirectImageUpload).limit(sample_size // 2).all()

            for direct_upload in direct_uploads:
                stats['direct_uploads_checked'] += 1
                consistent = True

                # Check original thumbnail consistency
                if direct_upload.thumbnail_filename:
                    file_exists = thumbnail_exists_direct(
                        direct_upload.folder_rel, direct_upload.filename, "orig"
                    )
                    if not file_exists:
                        consistent = False
                        stats['inconsistencies'].append({
                            'type': 'direct_upload_original',
                            'id': direct_upload.id,
                            'issue': 'Database references thumbnail but file missing',
                            'filename': direct_upload.thumbnail_filename
                        })

                # Check edited thumbnail consistency
                if direct_upload.edited_thumbnail_filename and direct_upload.edited_filename:
                    file_exists = thumbnail_exists_direct(
                        direct_upload.folder_rel, direct_upload.edited_filename, "edited"
                    )
                    if not file_exists:
                        consistent = False
                        stats['inconsistencies'].append({
                            'type': 'direct_upload_edited',
                            'id': direct_upload.id,
                            'issue': 'Database references edited thumbnail but file missing',
                            'filename': direct_upload.edited_thumbnail_filename
                        })

                # Check if thumbnail exists but database doesn't reference it
                if direct_upload.filename:
                    thumbnail_path = get_thumbnail_path_direct(direct_upload.folder_rel, direct_upload.filename, "orig")
                    if thumbnail_path.exists() and not direct_upload.thumbnail_filename:
                        consistent = False
                        stats['inconsistencies'].append({
                            'type': 'direct_upload_original_file_only',
                            'id': direct_upload.id,
                            'issue': 'Thumbnail file exists but database doesn\'t reference it',
                            'filename': thumbnail_path.name
                        })

                if direct_upload.edited_filename:
                    thumbnail_path = get_thumbnail_path_direct(direct_upload.folder_rel, direct_upload.edited_filename, "edited")
                    if thumbnail_path.exists() and not direct_upload.edited_thumbnail_filename:
                        consistent = False
                        stats['inconsistencies'].append({
                            'type': 'direct_upload_edited_file_only',
                            'id': direct_upload.id,
                            'issue': 'Edited thumbnail file exists but database doesn\'t reference it',
                            'filename': thumbnail_path.name
                        })

                if consistent:
                    stats['direct_uploads_consistent'] += 1
                else:
                    stats['direct_uploads_inconsistent'] += 1

        # Validate EncounterFile records
        with transaction_scope() as db:
            from models import IMAGE_DIR, ZipFile, PatientEncounters

            encounter_files = db.query(EncounterFile).limit(sample_size // 2).all()

            for encounter_file in encounter_files:
                stats['encounter_files_checked'] += 1
                consistent = True

                # Get the original image path
                result = (db.query(EncounterFile, PatientEncounters, ZipFile)
                         .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
                         .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
                         .filter(EncounterFile.id == encounter_file.id).first())

                if result:
                    encounter_file_obj, patient_encounter, zip_file = result
                    upload_date_str = zip_file.upload_date.strftime("%Y_%m_%d") if zip_file.upload_date else ""
                    original_image_path = IMAGE_DIR / upload_date_str / encounter_file.filename

                    # Check thumbnail consistency
                    if encounter_file.thumbnail_filename:
                        file_exists = thumbnail_exists_encounter(original_image_path)
                        if not file_exists:
                            consistent = False
                            stats['inconsistencies'].append({
                                'type': 'encounter_file',
                                'id': encounter_file.id,
                                'issue': 'Database references thumbnail but file missing',
                                'filename': encounter_file.thumbnail_filename
                            })

                    # Check if thumbnail exists but database doesn't reference it
                    thumbnail_path = get_thumbnail_path_encounter(original_image_path)
                    if thumbnail_path.exists() and not encounter_file.thumbnail_filename:
                        consistent = False
                        stats['inconsistencies'].append({
                            'type': 'encounter_file_file_only',
                            'id': encounter_file.id,
                            'issue': 'Thumbnail file exists but database doesn\'t reference it',
                            'filename': thumbnail_path.name
                        })

                    if consistent:
                        stats['encounter_files_consistent'] += 1
                    else:
                        stats['encounter_files_inconsistent'] += 1

        # Calculate totals
        stats['total_checked'] = stats['direct_uploads_checked'] + stats['encounter_files_checked']
        stats['total_consistent'] = stats['direct_uploads_consistent'] + stats['encounter_files_consistent']
        stats['total_inconsistent'] = stats['direct_uploads_inconsistent'] + stats['encounter_files_inconsistent']

        duration = datetime.now(pytz.UTC) - start_time
        local_time_end = datetime.now(tz)

        logger.info(
            "Thumbnail integrity validation completed - Duration: %ss, End IST: %s",
            sanitize_log_value(f"{duration.total_seconds():.2f}"),
            sanitize_log_value(local_time_end.strftime('%Y-%m-%d %H:%M:%S')),
        )

        logger.info(
            "Validation Statistics - Direct uploads: %s checked, %s consistent, %s inconsistent; "
            "Encounter files: %s checked, %s consistent, %s inconsistent; "
            "Total: %s checked, %s consistent, %s inconsistent",
            sanitize_log_value(stats['direct_uploads_checked']),
            sanitize_log_value(stats['direct_uploads_consistent']),
            sanitize_log_value(stats['direct_uploads_inconsistent']),
            sanitize_log_value(stats['encounter_files_checked']),
            sanitize_log_value(stats['encounter_files_consistent']),
            sanitize_log_value(stats['encounter_files_inconsistent']),
            sanitize_log_value(stats['total_checked']),
            sanitize_log_value(stats['total_consistent']),
            sanitize_log_value(stats['total_inconsistent']),
        )

        # Log inconsistencies
        if stats['total_inconsistent'] > 0:
            logger.warning(
                "Found %s thumbnail inconsistencies:",
                sanitize_log_value(stats['total_inconsistent']),
            )
            for inconsistency in stats['inconsistencies'][:10]:  # Limit to first 10 for readability
                logger.warning(
                    "  - %s",
                    sanitize_log_value(inconsistency),
                )
            if len(stats['inconsistencies']) > 10:
                logger.warning(
                    "  ... and %s more",
                    sanitize_log_value(len(stats['inconsistencies']) - 10),
                )
        else:
            logger.info("Thumbnail validation completed successfully - all thumbnails are consistent")

        consistency_rate = (stats['total_consistent'] / stats['total_checked'] * 100) if stats['total_checked'] > 0 else 100

        return {
            'success': True,
            'schedule_time': schedule_time,
            'sample_size': sample_size,
            'duration_seconds': duration.total_seconds(),
            'consistency_rate_percent': round(consistency_rate, 2),
            **stats,
            'start_time_utc': start_time.isoformat(),
            'end_time_utc': datetime.now(pytz.UTC).isoformat()
        }

    except Exception as e:
        duration = datetime.now(pytz.UTC) - start_time
        logger.error(
            "Thumbnail integrity validation failed after %ss: %s",
            sanitize_log_value(f"{duration.total_seconds():.2f}"),
            sanitize_log_value(e),
        )

        return {
            'success': False,
            'schedule_time': schedule_time,
            'sample_size': sample_size,
            'duration_seconds': duration.total_seconds(),
            'error': str(e),
            'start_time_utc': start_time.isoformat(),
            'end_time_utc': datetime.now(pytz.UTC).isoformat()
        }


def run_maintenance_tasks(app):
    """Run all maintenance tasks in sequence.

    This is a convenience function that runs all thumbnail maintenance tasks
    in the recommended order: cleanup -> regeneration -> validation.

    Args:
        app: Flask application instance

    Returns:
        dict: Combined results from all maintenance tasks
    """
    logger.info("Starting comprehensive thumbnail maintenance cycle")

    results = {
        'cleanup': {},
        'regeneration': {},
        'validation': {},
        'overall_success': True,
        'start_time_utc': datetime.now(pytz.UTC).isoformat()
    }

    try:
        # Step 1: Cleanup orphaned thumbnails
        results['cleanup'] = cleanup_orphaned_thumbnails(app, "maintenance_cycle")

        # Step 2: Regenerate missing thumbnails
        results['regeneration'] = regenerate_missing_thumbnails(app, "maintenance_cycle", limit=50)

        # Step 3: Validate thumbnail integrity
        results['validation'] = validate_thumbnail_integrity(app, "maintenance_cycle", sample_size=50)

        # Check overall success
        results['overall_success'] = (
            results['cleanup'].get('success', False) and
            results['regeneration'].get('success', False) and
            results['validation'].get('success', False)
        )

        results['end_time_utc'] = datetime.now(pytz.UTC).isoformat()

        if results['overall_success']:
            logger.info("Comprehensive thumbnail maintenance cycle completed successfully")
        else:
            logger.warning("Comprehensive thumbnail maintenance cycle completed with some failures")

            # Log which tasks failed
            if not results['cleanup'].get('success', False):
                logger.warning(
                    "Cleanup task failed: %s",
                    sanitize_log_value(results['cleanup'].get('error', 'Unknown error')),
                )
            if not results['regeneration'].get('success', False):
                logger.warning(
                    "Regeneration task failed: %s",
                    sanitize_log_value(results['regeneration'].get('error', 'Unknown error')),
                )
            if not results['validation'].get('success', False):
                logger.warning(
                    "Validation task failed: %s",
                    sanitize_log_value(results['validation'].get('error', 'Unknown error')),
                )

        return results

    except Exception as e:
        logger.error(
            "Comprehensive thumbnail maintenance cycle failed: %s",
            sanitize_log_value(e),
        )
        results['overall_success'] = False
        results['error'] = str(e)
        results['end_time_utc'] = datetime.now(pytz.UTC).isoformat()
        return results


class ThumbnailMaintenanceScheduler:
    """Background scheduler for thumbnail maintenance tasks."""

    def __init__(self, app):
        self.app = app
        self.running = False
        self.thread = None
        self.timezone = pytz.timezone(
            app.config.get("THUMBNAIL_MAINTENANCE_TIMEZONE",
            app.config.get("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata"))
        )

    def _schedule_task(self, task_func, schedule_time_str: str):
        """Execute a maintenance task at specified time."""
        try:
            current_time = datetime.now(self.timezone)
            logger.info(
                "Executing %s - IST: %s, Schedule: %s",
                sanitize_log_value(task_func.__name__),
                sanitize_log_value(current_time.strftime('%Y-%m-%d %H:%M:%S')),
                sanitize_log_value(schedule_time_str),
            )

            result = task_func(self.app, schedule_time_str)
            return result

        except Exception as e:
            logger.error(
                "Failed to execute %s: %s",
                sanitize_log_value(task_func.__name__),
                sanitize_log_value(e),
            )
            return {
                'success': False,
                'error': str(e),
                'schedule_time': schedule_time_str,
                'execution_time_utc': datetime.now(pytz.UTC).isoformat()
            }

    def _run_scheduled_tasks(self):
        """Run maintenance tasks according to schedule."""
        logger.info("Thumbnail maintenance scheduler started")

        while self.running:
            try:
                current_time = datetime.now(self.timezone)

                # Schedule 1: Orphaned cleanup at 07:00 IST
                if current_time.hour == 7 and current_time.minute == 0:
                    self._schedule_task(cleanup_orphaned_thumbnails, "07:00_daily")

                # Schedule 2: Missing thumbnail regeneration at 13:30 IST
                if current_time.hour == 13 and current_time.minute == 30:
                    self._schedule_task(regenerate_missing_thumbnails, "13:30_daily")

                # Schedule 2b: Additional regeneration at 20:00 IST
                if current_time.hour == 20 and current_time.minute == 0:
                    self._schedule_task(regenerate_missing_thumbnails, "20:00_daily")

                # Schedule 2c: Light-touch regeneration every 10 minutes
                if current_time.minute % 10 == 0:
                    self._schedule_task(lambda app, label: regenerate_missing_thumbnails(app, label, limit=200), "every_10_minutes")

                # Schedule 3: Integrity validation at 19:00 IST
                if current_time.hour == 19 and current_time.minute == 0:
                    self._schedule_task(validate_thumbnail_integrity, "19:00_daily")

                # Schedule 4: Full maintenance cycle at 01:30 IST
                if current_time.hour == 1 and current_time.minute == 30:
                    self._schedule_task(run_maintenance_tasks, "01:30_daily")

                # Sleep for 1 minute before checking again
                time.sleep(60)

            except Exception as e:
                logger.error(
                    "Error in maintenance scheduler loop: %s",
                    sanitize_log_value(e),
                )
                time.sleep(300)  # Wait 5 minutes before retrying

        logger.info("Thumbnail maintenance scheduler stopped")

    def start(self):
        """Start the maintenance scheduler."""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._run_scheduled_tasks, daemon=True)
            self.thread.start()
            logger.info("Thumbnail maintenance scheduler thread started")
            return self.thread
        else:
            logger.warning("Thumbnail maintenance scheduler is already running")
            return None

    def stop(self):
        """Stop the maintenance scheduler."""
        if self.running:
            self.running = False
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=30)
            logger.info("Thumbnail maintenance scheduler stopped")
        else:
            logger.warning("Thumbnail maintenance scheduler is not running")


def initialize_scheduler(app):
    """Initialize the thumbnail maintenance scheduler.

    Args:
        app: Flask application instance

    Returns:
        ThumbnailMaintenanceScheduler or None if disabled
    """
    if app.config.get("THUMBNAIL_MAINTENANCE_ENABLED", False):
        try:
            scheduler = ThumbnailMaintenanceScheduler(app)
            return scheduler
        except Exception as e:
            logger.error(
                "Failed to initialize thumbnail maintenance scheduler: %s",
                sanitize_log_value(e),
            )
            return None
    else:
        logger.info("Thumbnail maintenance scheduler disabled by configuration")
        return None


# Admin interface helpers
def get_maintenance_status():
    """Get current maintenance status and recent results.

    Returns:
        dict: Current status information
    """
    # This would typically query a database table or cache for recent results
    # For now, return a simple status with expected fields for JavaScript
    return {
        'overall_status': 'healthy',
        'scheduler_enabled': True,
        'last_cleanup': None,
        'last_regeneration': None,
        'last_validation': None,
        'last_run': None,
        'operations_today': 0,
        'currently_running': False,
        'next_scheduled': {
            'cleanup': None,
            'regeneration': None,
            'validation': None,
            'full_cycle': None
        }
    }


def trigger_manual_maintenance(task_type="all"):
    """Trigger manual execution of maintenance tasks.

    Args:
        task_type: Type of task to run ('cleanup', 'regeneration', 'validation', 'all')

    Returns:
        dict: Results of the manual execution
    """
    from flask import current_app

    try:
        if task_type == "cleanup":
            return cleanup_orphaned_thumbnails(current_app, "manual")
        elif task_type == "regeneration":
            return regenerate_missing_thumbnails(current_app, "manual", limit=100)
        elif task_type == "validation":
            return validate_thumbnail_integrity(current_app, "manual", sample_size=200)
        elif task_type == "all":
            return run_maintenance_tasks(current_app)
        else:
            raise ValueError(f"Invalid task type: {task_type}")

    except Exception as e:
        logger.error(
            "Manual maintenance task failed: %s",
            sanitize_log_value(e),
        )
        return {
            'success': False,
            'error': str(e),
            'task_type': task_type
        }


def queue_missing_thumbnail_regeneration(app, schedule_time: str = "post_upload", limit: int = 200):
    """
    Queue a missing-thumbnail regeneration run in the background.

    Args:
        app: Flask application instance
        schedule_time: Label for logging/metrics
        limit: Max thumbnails to trigger in this run
    """
    try:
        from utils.celery_helpers import enqueue_task, celery_enabled
        if celery_enabled():
            enqueue_task("celery_tasks.tasks.maintenance_tasks.regenerate_missing_thumbnails_task", limit)
            logger.info(
                "Queued thumbnail regeneration via Celery: schedule=%s limit=%s",
                sanitize_log_value(schedule_time),
                sanitize_log_value(limit),
            )
            return True
        # Import context wrapper from thumbnail_jobs
        from utils.thumbnail_jobs import with_app_context

        executor = app.config.get("EXECUTOR")
        if executor:
            # Use context wrapper to ensure Flask app context is available
            # in background threads, preventing "Working outside of application context" errors
            wrapped_regenerate_thumbnails = with_app_context(app, regenerate_missing_thumbnails)
            executor.submit(wrapped_regenerate_thumbnails, app, schedule_time, limit)
            logger.info(
                "Queued missing-thumbnail regeneration (limit %s) via executor, schedule=%s",
                sanitize_log_value(limit),
                sanitize_log_value(schedule_time),
            )
        else:
            # For threading fallback, use context wrapper as well
            wrapped_regenerate_thumbnails = with_app_context(app, regenerate_missing_thumbnails)
            threading.Thread(
                target=wrapped_regenerate_thumbnails,
                args=(app, schedule_time, limit),
                daemon=True,
            ).start()
            logger.info(
                "Started missing-thumbnail regeneration thread (limit %s), schedule=%s",
                sanitize_log_value(limit),
                sanitize_log_value(schedule_time),
            )
    except Exception as e:
        logger.error(
            "Failed to queue missing-thumbnail regeneration: %s",
            sanitize_log_value(e),
        )
