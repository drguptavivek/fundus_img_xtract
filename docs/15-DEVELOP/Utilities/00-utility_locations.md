# Utility Function Locations

This document provides a simple listing of each utility function file present in the codebase and a markdown table of utility functions in that file.

## Auth Utilities

### auth/utils.py

For detailed documentation, see [auth_utils.md](auth_utils.md).

| Function | Description |
| -------- | ----------- |
| `utcnow()` | Returns the current datetime in UTC timezone |
| `get_client_ip()` | Retrieves the client's IP address from the request |

## Analytics Utilities

### analytics/encounterUtils.py

For detailed documentation, see [analytics_encounterUtils.md](analytics_encounterUtils.md).

| Function | Description |
| -------- | ----------- |
| `get_encounter_summary(encounter_id: int, with_encounter_object: bool = False)` | Fetches a comprehensive summary for a given encounter |
| `get_encounters_summary_list(filters=None)` | Fetches a summary list of encounters with basic information |
| `get_encounters_with_non_pending_tasks(user_lab_unit_ids=None, is_admin_like=False)` | Fetches encounters that have images with associated non-pending tasks |
| `get_direct_image_summary(uuid_str: str)` | Fetches a comprehensive summary for a direct image upload |

### analytics/utils.py

For detailed documentation, see [analytics_utils.md](analytics_utils.md).

| Function | Description |
| -------- | ----------- |
| _summarize_grade(grade: Grade  None) | Converts a Grade object to a presentation-friendly GradeSummary object |
| `_summarize_consensus(consensus: Consensus  None)` | Converts a Consensus object to a presentation-friendly ConsensusSummary object |
| `fetch_image_task_details(db: SASession, tasks: Sequence[GradingTask])` | Collect enriched details for the provided grading tasks |
| `_latest_glaucoma_cleaned(glaucoma_rows: Sequence[GlaucomaResultsCleaned])` | Retrieves the most recent glaucoma results from a sequence of glaucoma results |
| `_latest_dr_report(dr_rows: Sequence[DiabeticRetinopathyReport])` | Retrieves the most recent diabetic retinopathy report from a sequence of reports |
| `group_task_details_by_image(task_details: Sequence[Dict[str, Any]])` | Groups task details by image ID for organized display |
| `build_encounter_result_payload(encounters: Sequence[PatientEncounters], task_details: Sequence[Dict[str, Any]])` | Builds a complete payload for encounter results display |

## API Utilities

### api/userUtils.py

For detailed documentation, see [api_userUtils.md](api_userUtils.md).

| Function | Description |
| -------- | ----------- |
| `get_eligible_lab_units()` | API endpoint to get eligible lab units for the current user or a specified user ID |

## Utility Modules

### utils/dualGradingFetchDetailUtils.py

For detailed documentation, see [utils_dualGradingFetchDetailUtils.md](utils_dualGradingFetchDetailUtils.md).

| Function | Description |
| -------- | ----------- |
| `fetch_task_with_related_data(db, task_id: int)` | Fetch a grading task with all related data |
| `fetch_grade_with_related_data(db, grade_id: int)` | Fetch a grade with all related data |
| `fetch_existing_grade_for_user(db, task_id: int, user_id: int, slot_type: str)` | Fetch existing grade for this user and slot (for review purposes) |
| `get_user_gradings(db, user_id: int, page: int = 1, per_page: int = 20, role_slot: Optional[str] = None)` | Retrieve a paginated list of gradings done by a user |
| `get_user_gradings_with_details(db, user_id: int, page: int = 1, per_page: int = 20, role_slot: Optional[str] = None, filter_date: Optional[str] = None)` | Retrieve a paginated list of gradings done by a user with related details |

### utils/dualGradingEligibility.py

For detailed documentation, see [utils_dualGradingEligibility.md](utils_dualGradingEligibility.md).

| Function | Description |
| -------- | ----------- |
| `get_user_grading_eligibility_details(db, user_id: int)` | Get detailed grading eligibility information for a user with lab unit and disease names |
| `_get_user_eligible_lab_unit_ids(db, user_id: int, disease_id: int, role_slot: str)` | Get the list of lab unit IDs that a user is eligible for a specific role and disease |
| `check_arbitration_eligibility(db, user_id: int, disease_id: int, lab_unit_id: int)` | Check if a user is eligible to arbitrate for a specific disease and lab unit |
| `get_user_eligibility_for_task(db, user_id: int, task_id: int, role_slot: str)` | Check if a user is eligible for a specific role slot for a task |
| `_has_user_graded_task_2weeks(db, user_id: int, task_id: int)` | Check if a user has graded a task in the past 2 weeks |

### utils/dualGradingConsensusUtils.py

For detailed documentation, see [utils_dualGradingConsensusUtils.md](utils_dualGradingConsensusUtils.md).

| Function | Description |
| -------- | ----------- |
| `create_or_update_consensus(task_id: int, db=None)` | Create or update consensus for a task based on grades |
| `get_task_consensus_status(task_id: int, db=None)` | Get the consensus status for a task |
| `update_task_state_based_on_grades(task_id: int, db=None)` | Update the task state based on the current grades |
| `has_consensus(task_id: int, db=None)` | Check if a task has reached consensus |
| `get_consensus_method(task_id: int, db=None)` | Get the consensus method for a task (match or adjudication) |

### utils/dualGradingGetNextTasks.py

For detailed documentation, see [utils_dualGradingGetNextTasks.md](utils_dualGradingGetNextTasks.md).

| Function | Description |
| -------- | ----------- |
| `_has_user_graded_task_6hr(db, user_id: int, task_id: int)` | Check if a user has graded a task in the last 6 hours (or configured timeframe) |
| `_get_filtered_tasks(db, user_id: int, disease_id: int, role_slot: str, eligible_lab_unit_ids: list)` | Get filtered tasks based on role slot and other criteria |
| `get_next_eligible_resident_task(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None)` | Get the next eligible task for a resident user |
| `get_next_eligible_resident2_task(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None)` | Get the next eligible task for a resident2 user |
| `get_next_eligible_arbitrator_task(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None)` | Get the next eligible task for an arbitrator user |
| `_atomically_get_and_lock_task(db, user_id: int, disease_id: int, role_slot: str, eligible_lab_unit_ids: list)` | Atomically get and lock a task for a user to prevent race conditions |
| `get_next_eligible_resident_task_atomic(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None)` | Get the next eligible task for a resident user with atomic locking to prevent race conditions |
| `get_next_eligible_resident2_task_atomic(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None)` | Get the next eligible task for a resident2 user with atomic locking to prevent race conditions |
| `get_next_eligible_arbitrator_task_atomic(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None)` | Get the next eligible task for an arbitrator user with atomic locking to prevent race conditions |

### utils/dualGradingKPIs.py

For detailed documentation, see [utils_dualGradingKPIs.md](utils_dualGradingKPIs.md).

| Function | Description |
| -------- | ----------- |
| `get_user_kpi_pending_task_count_data(db, user_id: int)` | Get KPI data for each core disease for pending tasks across all mapped lab units for each slot of a user |
| `get_user_kpi_completed_task_count_data(db, user_id: int)` | Get KPI data for each core disease for completed tasks across all mapped lab units for each slot of a user |

### utils/dualGradingRevisionUtils.py

For detailed documentation, see [utils_dualGradingRevisionUtils.md](utils_dualGradingRevisionUtils.md).

| Function | Description |
| -------- | ----------- |
| `is_user_eligible_for_revision(db: Session, user_id: int, task_id: int, slot_type: str, grade: Grade = None)` | Check if a user is eligible to revise their grade for a specific task and slot |
| `is_arbitrator_eligible_for_revision(db: Session, user_id: int, task_id: int, task: Optional[GradingTask] = None)` | Specific check for arbitrator revision eligibility |
| `check_arbitrator_revision_eligibility(db: Session, user_id: int, task: GradingTask)` | Check if an arbitrator is eligible to revise a grade based on the task state and other conditions |
| `is_arbitrator_revision_allowed(db: Session, user_id: int, task_id: int, slot: str)` | Check if an arbitrator is allowed to revise their grade |
| `check_revision_eligibility_by_task_state(task_state: str, role_slot: str, grade_created_at: Optional[datetime] = None)` | Check if a user is eligible to revise a grade based on the task state and other conditions |

### utils/dualGradingStuckTaskCleanup.py

For detailed documentation, see [utils_dualGradingStuckTaskCleanup.md](utils_dualGradingStuckTaskCleanup.md).

| Function | Description |
| -------- | ----------- |
| `cleanup_stuck_tasks(time_limit_minutes: int = 60, db=None)` | Identifies and cleans up tasks that have been started but not completed within the specified time limit |
| `mark_task_started(task_id: int, user_id: int, role_slot: str, db=None)` | Marks that a user has started working on a task by creating a TaskTracker record |
| `cleanup_task_tracker(task_id: int, user_id: int, role_slot: str, db=None)` | Immediately cleanup the TaskTracker record when a task for a specific slot is completed |
| `reset_stuck_tasks(time_limit_minutes: int = 60, db=None)` | Identifies and resets tasks that have been started but not completed within the time limit |

### utils/emails.py

For detailed documentation, see [utils_emails.md](utils_emails.md).

| Function | Description |
| -------- | ----------- |
| `send_email_sync(to_email: str, subject: str, body: str)` | Synchronous function to send an email to the specified recipient |
| `send_email(to_email: str, subject: str, body: str, callback: Optional[Callable[[bool], None]] = None)` | Asynchronously send an email to the specified recipient |
| `send_otp_email(to_email: str, username: str, otp: str, callback: Optional[Callable[[bool], None]] = None)` | Asynchronously send an OTP email to the specified recipient |
| `send_otp_email_sync(to_email: str, username: str, otp: str)` | Synchronously send an OTP email to the specified recipient |

### utils/rate_limiter.py

For detailed documentation, see [utils_rateLimiter.md](utils_rateLimiter.md).

| Function/Decorator | Description |
| ------------------- | ----------- |
| `init_rate_limit(app: Flask)` | Initialize rate limiting for the Flask application |
| `rate_limit(limit_string: str, key_func: Callable = None)` | Generic rate limit decorator with custom limit and key function |
| `auth_rate_limit(limit: str = None)` | Decorator for authentication endpoints with strict rate limiting |
| `upload_rate_limit(limit: str = None)` | Decorator for upload endpoints with moderate rate limiting |
| `api_rate_limit(limit: str = None)` | Decorator for API endpoints with standard rate limiting |
| `admin_rate_limit(limit: str = None)` | Decorator for admin endpoints with high rate limiting |
| `get_rate_limit_key()` | Custom key function for rate limiting that uses user ID or IP address |
| `get_rate_limit_for_user_role(user_roles: List[str])` | Determine rate limit based on user roles |
| `get_rate_limit_for_endpoint(endpoint_type: str, user_roles: List[str] = None)` | Get rate limit for specific endpoint types |
| `rate_limit_handler(e: RateLimitExceeded)` | Custom error handler for rate limit exceeded errors |

### utils/upload_eligibility.py

For detailed documentation, see [utils_upload_eligibility.md](utils_upload_eligibility.md).

| Function | Description |
| -------- | ----------- |
| `get_user_uploadVerify_eligibility(user_id: int)` | Return upload eligibility details for the given user |
| `get_user_lab_unit_ids(user_id: int)` | Return the set of lab unit IDs the user is allowed to access |

### utils/masterUtils.py

For detailed documentation, see [utils_masterUtils.md](utils_masterUtils.md).

| Function | Description |
| -------- | ----------- |
| `get_all_diseases()` | Get all diseases in the system |
| `get_disease_gradings(disease_id: int)` | Get all active gradings for a specific disease |
| `fetch_active_disease_gradings(db, disease_id: int)` | Fetch all active disease gradings for a disease, ordered by display order |
| `get_all_hospitals()` | Get all hospitals in the system |
| `get_all_lab_units()` | Get all lab units in the system |
| `get_hosp_lab_units(hospital_id: int)` | Get all lab units for a specific hospital |
| `get_all_areas()` | Get all areas in the system |
| `get_all_cameras()` | Get all cameras in the system |

### utils/fileUtils.py

For detailed documentation, see [utils_fileUtils.md](utils_fileUtils.md).

| Function | Description |
| -------- | ----------- |
| `_safe_file(base_dir: Path, filename: str)` | Prevent path traversal & ensure file exists inside base_dir |
| `_ensure_under_root(abs_path: Path, root: Path)` | Ensure abs_path is inside root (prevents traversal / wrong volume) |
| `_send_file_with_headers(abs_path: Path, mimetype: str  None = None)` | Cross-platform safe file send with sensible headers |
| `ensure_root()` | Ensure the root directory exists |
| `_is_inside(child: Path, root: Path)` | Check if a path is inside another path |
| `relfolder(folder: Path)` | POSIX-style directory path relative to BASE_DIR for DB storage |
| `abs_from_parts(folder_rel: str, filename: str, kind: str = "orig")` | Resolve absolute path under DIRECT_UPLOAD_DIR |
| `get_upload_dirs(user_id: int, when: Optional[datetime] = None)` | Create/return directories for this user/day |

### utils/imageSearchUtil.py

For detailed documentation, see [utils_imageSearchUtil.md](utils_imageSearchUtil.md).

| Function | Description |
| -------- | ----------- |
| `search_images_strict(db_session: Session, page: int = 1, per_page: int = 50, hospital_id: Optional[int] = None, lab_unit_ids: Optional[List[int]] = None, upload_start: Optional[_date] = None, upload_end: Optional[_date] = None, camera_ids: Optional[List[int]] = None, disease_ids: Optional[List[int]] = None, area_ids: Optional[List[int]] = None, is_mydriatic: Optional[bool] = None, has_dr_report: Optional[bool] = None, has_glaucoma_report: Optional[bool] = None, capture_start: Optional[_date] = None, capture_end: Optional[_date] = None, search_query: Optional[str] = None, user_id: Optional[int] = None, image_type: Optional[str] = None)` | Search images with strict filter separation and UUID-based returns |

### utils/taskUtils.py

For detailed documentation, see [utils_taskUtils.md](utils_taskUtils.md).

| Function | Description |
| -------- | ----------- |
| `get_task_summary(db_session, page: int = 1, per_page: int = 50, lab_unit_ids: Optional[List[int]] = None, status_filter: Optional[str] = None, disease_filter: Optional[int] = None, search_query: Optional[str] = None, hospital_filter: Optional[int] = None, lab_unit_name_filter: Optional[str] = None, lab_unit_filter: Optional[int] = None)` | Get paginated list of tasks with key information |
| `get_task_detail(db_session, task_id: int)` | Get detailed information about a specific task including grades and consensus |
| `get_tasks_by_status(db_session, status: str, lab_unit_ids: Optional[List[int]] = None, page: int = 1, per_page: int = 50)` | Get tasks filtered by status |
| `get_task_stats(db_session, lab_unit_ids: Optional[List[int]] = None)` | Get task statistics for specified lab units |
| `get_tasks_for_user(db_session, user_id: int, page: int = 1, per_page: int = 50, status_filter: Optional[str] = None)` | Get tasks eligible for a specific user based on their permissions |

### utils/jobUtils.py

For detailed documentation, see [utils_jobUtils.md](utils_jobUtils.md).

| Function | Description |
| -------- | ----------- |
| `get_recent_zip_uploads(limit: int = 100, job_type: str = "zip upload")` | Get recent ZIP upload jobs with success/failure status |

### utils/notifications.py

| Function | Description |
| -------- | ----------- |
| `prepare_notification_payload(title: str, message: str)` | Prepare and validate notification payload |
| `send_notification_to_user(user_id: int, title: str, message: str, notification_type: Union[NotificationType, str] = NotificationType.INFO, *, sender_user_id: Optional[int] = None)` | Send a notification to a specific user |
| `send_notification_to_admins(title: str, message: str, notification_type: Union[NotificationType, str] = NotificationType.INFO, *, sender_user_id: Optional[int] = None)` | Send a notification to all admin users |
| `send_system_notification(title: str, message: str, notification_type: Union[NotificationType, str] = NotificationType.INFO, *, sender_user_id: Optional[int] = None)` | Send a system-wide notification |
| `get_user_notifications(user_id: int, unread_only: bool = False, limit: Optional[int] = None)` | Get notifications for a specific user |
| `mark_notification_as_read(notification_id: int, user_id: int)` | Mark a specific notification as read |
| `mark_all_user_notifications_as_read(user_id: int)` | Mark all notifications for a user as read |

### utils/utilsImgServe.py

For detailed documentation, see [utils_utilsImgServe.md](utils_utilsImgServe.md).

| Function | Description |
| -------- | ----------- |
| `encounterImageByUUID(uuid: str)` | Serve an encounter image by UUID |
| `encounterDrReportByUUID(uuid: str)` | Serve an encounter DR report by UUID |
| `encounterGlaucomaReportByUUID(uuid: str)` | Serve an encounter Glaucoma report by UUID |
| `directImgOrigByUUID(uuid: str)` | Serve a direct image original by UUID |
| `directImgEdByUUID(uuid: str)` | Serve a direct image edited version by UUID |
| `directImgFinalByUUID(uuid: str)` | Serve a direct image final version by UUID |
| `imgForGradingByUUID(uuid: str)` | Serve an image for grading purposes by UUID |

### utils/datetime_filters.py

For detailed documentation, see [utils_datetime_filters.md](utils_datetime_filters.md).

| Function | Description |
| -------- | ----------- |
| `_resolve_target_timezone()` | Resolve the preferred timezone for the active request |
| `_ensure_aware(value: datetime)` | Ensure the datetime is timezone-aware, assuming UTC when naive |
| `format_user_datetime(value: Optional[datetime  date], fmt: str = "%Y-%m-%d %H:%M")` | Format a UTC datetime for display in the user's timezone |

### utils/timezone_choices.py

For detailed documentation, see [utils_timezone_choices.md](utils_timezone_choices.md).

| Constant/Function | Description |
| ----------------- | ----------- |
| `_humanize_timezone(tz: str)` | Create a human-readable label from a timezone identifier |
| `_build_choices()` | Build the list of timezone choices by processing all available timezones |
| `DEFAULT_TIMEZONE` | Default timezone identifier (from environment or fallback to Asia/Kolkata) |
| `TIMEZONE_CHOICES` | List of tuples containing (timezone identifier, human-readable label) |
| `TIMEZONE_VALUES` | Set of valid timezone identifiers for validation |
| `TIMEZONE_LABELS` | Dictionary mapping timezone identifiers to their human-readable labels |

### utils/stack_trace_handler.py

For detailed documentation, see [utils_stack_trace_handler.md](utils_stack_trace_handler.md).

| Function | Description |
| -------- | ----------- |
| `get_runtime_error_logger()` | Get the runtime error logger instance |
| `log_stack_trace(message: Optional[str] = None, exception: Optional[Exception] = None, include_locals: bool = False)` | Log a stack trace to the runtime error log |
| `stack_trace_context(message: Optional[str] = None, include_locals: bool = False)` | Decorator to automatically log stack traces when exceptions occur |
| `StackTraceContextManager` | Context manager for capturing stack traces |
| `log_current_stack(message: Optional[str] = None)` | Log the current stack trace without an exception |

### utils/utils.py

For detailed documentation, see [utils_utils.md](utils_utils.md).

| Function | Description |
| -------- | ----------- |
| `with_session()` | Context manager for database sessions |
| `require_owner_or_roles(upload, *roles)` | Check if user owns the upload or has required roles |

### utils/utils2.py

For detailed documentation, see [utils_utils2.md](utils_utils2.md).

| Function | Description |
| -------- | ----------- |
| `calculate_file_hash(filepath: Union[str, Path])` | Calculate MD5 hash of a file |
| `format_file_size(size_bytes: int)` | Format file size in human-readable format |
| `sanitize_filename(filename: str)` | Sanitize filename to prevent path traversal and other issues |
| `uniquify(dest_dir: Path, filename: str)` | Create a unique filename by adding a numeric suffix if needed |
| `get_file_extension(filename: str)` | Get file extension in lowercase |
| `is_allowed_file_extension(filename: str, allowed_extensions: set)` | Check if file extension is in allowed extensions set |
| `get_current_timestamp()` | Get current timestamp in ISO format |
| `safe_int(value: Any, default: int = 0)` | Safely convert value to int |
| `safe_float(value: Any, default: float = 0.0)` | Safely convert value to float |
| `is_valid_uuid(uuid_string: str)` | Check if string is a valid UUID format |
| `get_directory_size(path: Union[str, Path])` | Calculate total size of directory in bytes |
