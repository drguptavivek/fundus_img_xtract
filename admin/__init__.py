from flask import Blueprint

# Import all route handlers
from .users import users_list, add_user, edit_user, users_update, user_created
from .security import change_password, manage_roles, role_usage, routes_by_role
from .lookups.hospital import list_hospitals, edit_hospital, delete_hospital
from .lookups.lab_unit import list_lab_units, edit_lab_unit, delete_lab_unit
from .lookups.camera import list_cameras, edit_camera, delete_camera
from .lookups.disease import list_diseases, edit_disease, delete_disease
from .lookups.area import list_areas, edit_area, delete_area
from .disease_gradings import list_disease_gradings, delete_disease_grading, get_grading_features
from .linked_grading import (
    linked_disease_gradings_list,
    edit_linked_disease_grading,
    delete_linked_disease_grading,
)
from .uploads import malicious_uploads
from .grading_eligibility import manage_eligibility_users, edit_eligibility
from .logs import log_viewer
from .disk_usage import disk_usage, delete_duplicates, delete_old_processed_zips
from .ai_models import list_and_create_ai_model, edit_ai_model, delete_ai_model
from .database_dump import database_dump, get_database_info
from .database_excel_export import database_excel_export, get_database_tables
from .database_restore import bp as database_restore_bp
from .materialized_view_status import materialized_view_status, api_materialized_view_status, api_last_refresh, manual_refresh, api_schedule_status
from .thumbnail_management import register_thumbnail_admin_routes
from .image_metadata import (
    image_metadata_admin,
    image_metadata_backfill,
    image_metadata_run_pii_queue,
    image_metadata_status,
    image_metadata_stop_all,
    image_metadata_clear_queued,
    image_metadata_clear_running,
)
from .task_backfill import task_backfill_admin, task_backfill_run
from .status import (
    admin_status,
    api_admin_status,
    register_status_routes,
    refresh_sequences,
    api_sequences_status,
)
from .task_review_inconsistency import task_review_inconsistency, apply_review_as_final
from .app_settings import upload_settings, admin_settings
from .upload_quotas import list_upload_quotas, update_upload_quota, upload_quota_redirect
from .email_settings import (
    email_settings_list, create_email_settings, edit_email_settings,
    test_email_settings, delete_email_settings, activate_email_settings,
    api_test_current_email_config, send_sample_email
)
from .grading_state_inconsistencies import grading_state_inconsistencies
from .audit_routes import sensitive_operations_audit, sensitive_operation_details
from .cve_scanner import (
    cve_security_report,
    api_cve_summary,
    api_cve_refresh,
    cve_report_text,
    api_cve_scan_history,
    htmx_cve_packages,
    htmx_cve_vulnerabilities,
    htmx_cve_scan_history,
)
from .package_updates import (
    package_updates_report,
    api_package_updates_summary,
    api_package_updates_refresh,
    api_package_updates_scan_history,
    api_package_updates_yaml,
    api_package_updates_instructions,
    htmx_package_list,
    htmx_scan_history,
)
from .s3_config import (
    s3_configs_list, s3_config_create, s3_config_edit, s3_config_delete,
    s3_config_activate, s3_config_test_connection, s3_config_rotate_pepper,
    s3_config_set_fallback,
    s3_configs_api_list, s3_config_api_test_connection_modal, s3_config_api_create,
)
from .s3_sync_status import (
    s3_sync_dashboard, s3_sync_hospital_detail,
    s3_sync_status_api, s3_sync_stats_api, s3_sync_retry,
)
from .celery_schedule import (
    celery_schedule_list,
    celery_schedule_create,
    celery_schedule_update,
    celery_schedule_delete,
)


# Register routes with the blueprint
admin_bp = Blueprint("admin", __name__, url_prefix="/admin", template_folder="templates")


# Register routes with the blueprint
# User management routes
admin_bp.add_url_rule("/users", view_func=users_list, methods=["GET"])
admin_bp.add_url_rule("/users/new", view_func=add_user, methods=["GET", "POST"])
admin_bp.add_url_rule("/users/created", view_func=user_created, methods=["GET"])
admin_bp.add_url_rule("/users/<int:user_id>/edit", view_func=edit_user, methods=["GET", "POST"])
admin_bp.add_url_rule("/users/<int:user_id>/update", view_func=users_update, methods=["POST"])

# Security routes (password and roles)
admin_bp.add_url_rule("/change-password", view_func=change_password, methods=["GET", "POST"])
admin_bp.add_url_rule("/roles", view_func=manage_roles, methods=["GET", "POST"])
admin_bp.add_url_rule("/role-usage", view_func=role_usage, methods=["GET"])
admin_bp.add_url_rule("/routes-by-role/<string:role_name>", view_func=routes_by_role, methods=["GET"])

# App settings routes (place before catch-all lookup routes)
admin_bp.add_url_rule(
    "/settings/uploads",
    view_func=upload_settings,
    methods=["GET", "POST"],
    endpoint="upload_settings",
    strict_slashes=False,
)
admin_bp.add_url_rule(
    "/settings",
    view_func=admin_settings,
    methods=["GET", "POST"],
    endpoint="admin_settings",
    strict_slashes=False,
)

# Upload quotas
admin_bp.add_url_rule(
    "/upload-quotas",
    view_func=list_upload_quotas,
    methods=["GET"],
    endpoint="list_upload_quotas",
)
admin_bp.add_url_rule(
    "/upload-quota",
    view_func=upload_quota_redirect,
    methods=["GET"],
    endpoint="upload_quota_redirect",
)
admin_bp.add_url_rule(
    "/grading-inconsistencies",
    view_func=grading_state_inconsistencies,
    methods=["GET", "POST"],
    endpoint="grading_state_inconsistencies",
)
admin_bp.add_url_rule(
    "/task_review_inconsistency",
    view_func=task_review_inconsistency,
    methods=["GET"],
    endpoint="task_review_inconsistency",
)
admin_bp.add_url_rule(
    "/task_review_inconsistency/<int:task_id>/apply",
    view_func=apply_review_as_final,
    methods=["POST"],
    endpoint="apply_review_as_final",
)

admin_bp.add_url_rule(
    "/celery-schedules",
    view_func=celery_schedule_list,
    methods=["GET"],
    endpoint="celery_schedule_list",
)
admin_bp.add_url_rule(
    "/celery-schedules",
    view_func=celery_schedule_create,
    methods=["POST"],
    endpoint="celery_schedule_create",
)
admin_bp.add_url_rule(
    "/celery-schedules/<int:schedule_id>",
    view_func=celery_schedule_update,
    methods=["POST"],
    endpoint="celery_schedule_update",
)
admin_bp.add_url_rule(
    "/celery-schedules/<int:schedule_id>/delete",
    view_func=celery_schedule_delete,
    methods=["POST"],
    endpoint="celery_schedule_delete",
)
admin_bp.add_url_rule(
    "/upload-quotas/<int:user_id>/update",
    view_func=update_upload_quota,
    methods=["POST"],
    endpoint="update_upload_quota",
)

# Lookup table routes
admin_bp.add_url_rule("/hospital", view_func=list_hospitals, methods=["GET", "POST"])
admin_bp.add_url_rule("/hospital/<int:item_id>/edit", view_func=edit_hospital, methods=["GET", "POST"])
admin_bp.add_url_rule("/hospital/<int:item_id>/delete", view_func=delete_hospital, methods=["POST"])
admin_bp.add_url_rule("/lab_unit", view_func=list_lab_units, methods=["GET", "POST"])
admin_bp.add_url_rule("/lab_unit/<int:item_id>/edit", view_func=edit_lab_unit, methods=["GET", "POST"])
admin_bp.add_url_rule("/lab_unit/<int:item_id>/delete", view_func=delete_lab_unit, methods=["POST"])
admin_bp.add_url_rule("/camera", view_func=list_cameras, methods=["GET", "POST"])
admin_bp.add_url_rule("/camera/<int:item_id>/edit", view_func=edit_camera, methods=["GET", "POST"])
admin_bp.add_url_rule("/camera/<int:item_id>/delete", view_func=delete_camera, methods=["POST"])
admin_bp.add_url_rule("/disease", view_func=list_diseases, methods=["GET", "POST"])
admin_bp.add_url_rule("/disease/<int:item_id>/edit", view_func=edit_disease, methods=["GET", "POST"])
admin_bp.add_url_rule("/disease/<int:item_id>/delete", view_func=delete_disease, methods=["POST"])
admin_bp.add_url_rule("/area", view_func=list_areas, methods=["GET", "POST"])
admin_bp.add_url_rule("/area/<int:item_id>/edit", view_func=edit_area, methods=["GET", "POST"])
admin_bp.add_url_rule("/area/<int:item_id>/delete", view_func=delete_area, methods=["POST"])

# Disease grading routes
admin_bp.add_url_rule("/disease-gradings", view_func=list_disease_gradings, methods=["GET", "POST"])
admin_bp.add_url_rule("/disease-gradings/<int:grading_id>/delete", view_func=delete_disease_grading, methods=["POST"])
admin_bp.add_url_rule("/disease-gradings/<int:grading_id>/features", view_func=get_grading_features, methods=["GET"])

# Linked disease grading routes
admin_bp.add_url_rule(
    "/linked-disease-gradings",
    view_func=linked_disease_gradings_list,
    methods=["GET", "POST"],
    endpoint="linked_disease_gradings_list",
)
admin_bp.add_url_rule(
    "/linked-disease-gradings/<int:link_id>/edit",
    view_func=edit_linked_disease_grading,
    methods=["GET", "POST"],
    endpoint="edit_linked_disease_grading",
)
admin_bp.add_url_rule(
    "/linked-disease-gradings/<int:link_id>/delete",
    view_func=delete_linked_disease_grading,
    methods=["POST"],
    endpoint="delete_linked_disease_grading",
)


# Grading Eligibility routes
admin_bp.add_url_rule("/grading-eligibility", view_func=manage_eligibility_users, methods=["GET"])
admin_bp.add_url_rule("/grading-eligibility/<int:user_id>", view_func=edit_eligibility, methods=["GET", "POST"])

# Uploads routes
admin_bp.add_url_rule("/malicious-uploads", view_func=malicious_uploads, methods=["GET"])

# Log viewer
admin_bp.add_url_rule("/logs", view_func=log_viewer, methods=["GET"])

# Disk usage analysis
admin_bp.add_url_rule("/disk-usage", view_func=disk_usage, methods=["GET"])
admin_bp.add_url_rule("/disk-usage/delete-duplicates", view_func=delete_duplicates, methods=["POST"])
admin_bp.add_url_rule("/disk-usage/delete-old-zips", view_func=delete_old_processed_zips, methods=["POST"])

# AI Model routes
admin_bp.add_url_rule("/ai-models", view_func=list_and_create_ai_model, methods=["GET", "POST"])
admin_bp.add_url_rule("/ai-models/<int:item_id>/edit", view_func=edit_ai_model, methods=["GET", "POST"])
admin_bp.add_url_rule("/ai-models/<int:item_id>/delete", view_func=delete_ai_model, methods=["POST"])

# Database dump routes
admin_bp.add_url_rule("/database-dump", view_func=database_dump, methods=["GET", "POST"])
admin_bp.add_url_rule("/database-info", view_func=get_database_info, methods=["GET"])

# Database Excel export routes
admin_bp.add_url_rule("/database-excel-export", view_func=database_excel_export, methods=["GET", "POST"])
admin_bp.add_url_rule("/database-tables", view_func=get_database_tables, methods=["GET"])

# Materialized View routes
admin_bp.add_url_rule("/materialized-view", view_func=materialized_view_status, methods=["GET"])
admin_bp.add_url_rule("/api/materialized-view/status", view_func=api_materialized_view_status, methods=["GET"])
admin_bp.add_url_rule("/api/materialized-view/last-refresh", view_func=api_last_refresh, methods=["GET"])
admin_bp.add_url_rule("/api/materialized-view/refresh", view_func=manual_refresh, methods=["POST"])
admin_bp.add_url_rule("/api/materialized-view/schedule", view_func=api_schedule_status, methods=["GET"])
admin_bp.add_url_rule("/sequences/refresh", view_func=refresh_sequences, methods=["POST"])
admin_bp.add_url_rule("/api/sequences/status", view_func=api_sequences_status, methods=["GET"])

# Image metadata backfill
admin_bp.add_url_rule("/image-metadata", view_func=image_metadata_admin, methods=["GET"])
admin_bp.add_url_rule("/image-metadata/backfill", view_func=image_metadata_backfill, methods=["POST"])
admin_bp.add_url_rule(
    "/image-metadata/stop",
    view_func=image_metadata_stop_all,
    methods=["POST"],
    endpoint="image_metadata_stop_all",
)
admin_bp.add_url_rule(
    "/image-metadata/clear-queued",
    view_func=image_metadata_clear_queued,
    methods=["POST"],
    endpoint="image_metadata_clear_queued",
)
admin_bp.add_url_rule(
    "/image-metadata/clear-running",
    view_func=image_metadata_clear_running,
    methods=["POST"],
    endpoint="image_metadata_clear_running",
)
admin_bp.add_url_rule(
    "/image-metadata/pii-queue/run",
    view_func=image_metadata_run_pii_queue,
    methods=["POST"],
    endpoint="image_metadata_run_pii_queue",
)
admin_bp.add_url_rule("/image-metadata/status", view_func=image_metadata_status, methods=["GET"])
admin_bp.add_url_rule("/metadata-backfill", view_func=image_metadata_admin, methods=["GET"], endpoint="metadata_backfill_admin")
admin_bp.add_url_rule("/metadata-backfill/run", view_func=image_metadata_backfill, methods=["POST"], endpoint="metadata_backfill_run")
admin_bp.add_url_rule("/metadat-backfilll", view_func=image_metadata_admin, methods=["GET"], endpoint="metadata_backfill_admin_alias")

# Task backfill
admin_bp.add_url_rule("/task-backfill", view_func=task_backfill_admin, methods=["GET"])
admin_bp.add_url_rule("/task-backfill/run", view_func=task_backfill_run, methods=["POST"])

# Register thumbnail management routes
register_thumbnail_admin_routes(admin_bp)

# Register admin status routes
register_status_routes(admin_bp)

# S3 Configuration routes
admin_bp.add_url_rule("/s3-configs", view_func=s3_configs_list, methods=["GET"])
admin_bp.add_url_rule("/s3-configs/new", view_func=s3_config_create, methods=["GET", "POST"])
admin_bp.add_url_rule("/s3-configs/<int:s3_config_id>/edit", view_func=s3_config_edit, methods=["GET", "POST"])
admin_bp.add_url_rule("/s3-configs/<int:s3_config_id>/delete", view_func=s3_config_delete, methods=["POST"])
admin_bp.add_url_rule("/s3-configs/<int:s3_config_id>/activate", view_func=s3_config_activate, methods=["POST"])
admin_bp.add_url_rule("/s3-configs/<int:s3_config_id>/test-connection", view_func=s3_config_test_connection, methods=["POST"])
admin_bp.add_url_rule("/s3-configs/<int:s3_config_id>/rotate-pepper", view_func=s3_config_rotate_pepper, methods=["POST"])
admin_bp.add_url_rule("/s3-configs/<int:s3_config_id>/fallback", view_func=s3_config_set_fallback, methods=["GET", "POST"])
# API endpoints for JS-based UI
admin_bp.add_url_rule("/s3-configs/api/list", view_func=s3_configs_api_list, methods=["GET"])
admin_bp.add_url_rule("/s3-configs/api/test-connection-modal", view_func=s3_config_api_test_connection_modal, methods=["POST"])
admin_bp.add_url_rule("/s3-configs/api/create", view_func=s3_config_api_create, methods=["POST"])

# S3 Sync Status routes
admin_bp.add_url_rule("/s3-sync-dashboard", view_func=s3_sync_dashboard, methods=["GET"], endpoint="s3_sync_dashboard")
admin_bp.add_url_rule("/s3-sync-dashboard/hospital/<int:hospital_id>", view_func=s3_sync_hospital_detail, methods=["GET"])
admin_bp.add_url_rule("/api/s3-sync-status", view_func=s3_sync_status_api, methods=["GET"])
admin_bp.add_url_rule("/api/s3-sync-retry/<int:sync_id>", view_func=s3_sync_retry, methods=["POST"])
admin_bp.add_url_rule("/api/s3-sync-stats", view_func=s3_sync_stats_api, methods=["GET"])

# Register database restore blueprint
admin_bp.register_blueprint(database_restore_bp)

# Email settings routes
admin_bp.add_url_rule("/email-settings", view_func=email_settings_list, methods=["GET"])
admin_bp.add_url_rule("/email-settings/new", view_func=create_email_settings, methods=["GET", "POST"])
admin_bp.add_url_rule("/email-settings/<int:settings_id>/edit", view_func=edit_email_settings, methods=["GET", "POST"])
admin_bp.add_url_rule("/email-settings/<int:settings_id>/test", view_func=test_email_settings, methods=["GET"])
admin_bp.add_url_rule("/email-settings/<int:settings_id>/delete", view_func=delete_email_settings, methods=["POST"])
admin_bp.add_url_rule("/email-settings/<int:settings_id>/activate", view_func=activate_email_settings, methods=["POST"])
admin_bp.add_url_rule("/api/email-settings/test-current", view_func=api_test_current_email_config, methods=["GET"])
admin_bp.add_url_rule("/api/email-settings/send-sample", view_func=send_sample_email, methods=["POST"])

# Sensitive Operations Audit routes
admin_bp.add_url_rule("/sensitive-operations", view_func=sensitive_operations_audit, methods=["GET"])
admin_bp.add_url_rule("/sensitive-operations/<int:log_id>", view_func=sensitive_operation_details, methods=["GET"])

# CVE Security Scanner routes
admin_bp.add_url_rule("/security/cves", view_func=cve_security_report, methods=["GET"])
admin_bp.add_url_rule("/api/security/cves/summary", view_func=api_cve_summary, methods=["GET"])
admin_bp.add_url_rule("/api/security/cves/refresh", view_func=api_cve_refresh, methods=["POST"])
admin_bp.add_url_rule("/api/security/cves/history", view_func=api_cve_scan_history, methods=["GET"])
admin_bp.add_url_rule("/api/security/cves/packages", view_func=htmx_cve_packages, methods=["GET"])
admin_bp.add_url_rule("/api/security/cves/vulnerabilities", view_func=htmx_cve_vulnerabilities, methods=["GET"])
admin_bp.add_url_rule("/api/security/cves/history/htmx", view_func=htmx_cve_scan_history, methods=["GET"])
admin_bp.add_url_rule("/security/cves/report.txt", view_func=cve_report_text, methods=["GET"])

# Package Updates Scanner routes
admin_bp.add_url_rule("/security/package-updates", view_func=package_updates_report, methods=["GET"])
admin_bp.add_url_rule("/api/security/package-updates/summary", view_func=api_package_updates_summary, methods=["GET"])
admin_bp.add_url_rule("/api/security/package-updates/refresh", view_func=api_package_updates_refresh, methods=["POST"])
admin_bp.add_url_rule("/api/security/package-updates/history", view_func=api_package_updates_scan_history, methods=["GET"])
admin_bp.add_url_rule("/api/security/package-updates/packages", view_func=htmx_package_list, methods=["GET"])
admin_bp.add_url_rule("/api/security/package-updates/history/htmx", view_func=htmx_scan_history, methods=["GET"])
admin_bp.add_url_rule("/api/security/package-updates/updates.yaml", view_func=api_package_updates_yaml, methods=["GET"])
admin_bp.add_url_rule("/api/security/package-updates/instructions", view_func=api_package_updates_instructions, methods=["GET"])
