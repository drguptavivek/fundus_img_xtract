# Admin JSON APIs

These endpoints support admin dashboards, operational tooling, and maintenance actions.

Auth model:

- Most routes use Flask session auth plus role checks.
- Several endpoints are internal dashboard APIs and return JSON objects intended for JS clients.
- A few helper routes are HTML or redirect flows; those are called out explicitly.

## Status and monitoring

| Route | Method | Response shape |
| --- | --- | --- |
| `/admin/api/status` | `GET` | `{"success": true, "data": {"timestamp": str, "thumbnail": object, "maintenance": object, "health": object, "system": object, "recent_activity": array, "celery": object}}` |
| `/admin/api/sequences/status` | `GET` | `{"success": true, "data": object}` |
| `/admin/api/celery/tasks/status` | `GET` | `{"success": true, "data": object}` |
| `/admin/api/materialized-view/status` | `GET` | `{"success": true, "data": object}` |
| `/admin/api/materialized-view/last-refresh` | `GET` | `{"success": true, "data": object}` |
| `/admin/api/materialized-view/refresh` | `POST` | `{"success": bool, "message": str}` |
| `/admin/api/materialized-view/schedule` | `GET` | `{"success": true, "data": object}` |
| `/admin/stuck-remidio-uploads/status` | `GET` | Dry-run scan across all intake date folders by default; returns `{"success": true, "data": {"dry_run": true, "scanned": int, "eligible": int, "moved": 0, "skipped": int, "errors": int, "items": array}}` |
| `/admin/stuck-remidio-uploads/cleanup` | `POST` | Guarded cleanup across all intake date folders by default; returns `{"success": bool, "data": {"dry_run": bool, "scanned": int, "eligible": int, "moved": int, "skipped": int, "errors": int, "items": array}}` |
| `/admin/sequences/refresh` | `POST` | Redirects to the admin status page; not JSON. |

## Thumbnail and media maintenance

| Route | Method | Response shape |
| --- | --- | --- |
| `/admin/api/thumbnail_stats` | `GET` | `{"success": true, "stats": {"direct_uploads": object, "encounter_files": object, "storage": object}}` |
| `/admin/api/maintenance_status` | `GET` | `{"success": true, "status": object}` |
| `/admin/api/thumbnail/health_check` | `GET` | `{"success": true, "health_status": {"overall_health": str, "issues": array, "recommendations": array}, "timestamp": str}` |
| `/admin/api/thumbnail/manual_maintenance` | `POST` | `{"success": bool, "task_type": str, "result": object}` |
| `/admin/api/thumbnail/cleanup_orphaned` | `POST` | `{"success": bool, "result": object}` |
| `/admin/api/thumbnail/regenerate_missing` | `POST` | `{"success": bool, "result": object}` |
| `/admin/api/thumbnail/validate_integrity` | `POST` | `{"success": bool, "result": object}` |
| `/admin/api/thumbnail/full_maintenance` | `POST` | `{"success": bool, "result": object}` |

## S3 sync and storage

All routes in this section require the global `admin` role. They have no
`local_admin`, Hospital/Lab Unit, or project-scoped alternative.

| Route | Method | Response shape |
| --- | --- | --- |
| `/admin/api/s3-sync-status` | `GET` | `{"syncs": array, "count": int}` |
| `/admin/api/s3-sync-retry/<sync_id>` | `POST` | `{"success": true, "message": str, "sync_id": int}` or error JSON |
| `/admin/api/s3-sync-stats` | `GET` | `{"stats": array}` |
| `/admin/s3-configs/api/list` | `GET` | JSON list of active S3 configs across hospitals |
| `/admin/s3-configs/api/test-connection-modal` | `POST` | `{"success": bool, "message": str}` |
| `/admin/s3-configs/api/create` | `POST` | JSON success/error payload for the created config |

## Security and support

| Route | Method | Response shape |
| --- | --- | --- |
| `/admin/api/security/cves/summary` | `GET` | JSON summary object |
| `/admin/api/security/cves/refresh` | `POST` | JSON task/result object |
| `/admin/api/security/cves/history` | `GET` | `{"history": array}` or equivalent scan-history payload |
| `/admin/api/security/cves/packages` | `GET` | JSON/HTMX-compatible packages payload |
| `/admin/api/security/cves/vulnerabilities` | `GET` | JSON/HTMX-compatible vulnerabilities payload |
| `/admin/api/security/cves/history/htmx` | `GET` | HTML fragment |
| `/admin/api/security/package-updates/summary` | `GET` | JSON summary object |
| `/admin/api/security/package-updates/refresh` | `POST` | `{"success": true, "task_id": str, "current_results": object, "message": str}` |
| `/admin/api/security/package-updates/history` | `GET` | `{"scans": array}` |
| `/admin/api/security/package-updates/packages` | `GET` | HTML fragment |
| `/admin/api/security/package-updates/history/htmx` | `GET` | HTML fragment |
| `/admin/api/security/package-updates/updates.yaml` | `GET` | YAML, not JSON |
| `/admin/api/security/package-updates/instructions` | `GET` | Plain-text instructions |
| `/admin/sensitive-operations/<log_id>` | `GET` | `{"id": int, "operation_type": str, "status": str, "user": str, "ip_address": str, "created_at": str, "request_details": object, "result_details": object}` |
| `/admin/rate-limits/status` | `GET` | Rate-limit status object |
| `/admin/rate-limits/my-key` | `GET` | `{"key": str}` |
| `/admin/rate-limits/clear-limit-ajax` | `POST` | `{"success": bool, "message": str}` |

## Email and lookup helpers

| Route | Method | Response shape |
| --- | --- | --- |
| `/admin/api/email-settings/test-current` | `GET` | `{"success": bool, "message": str}` |
| `/admin/api/email-settings/send-sample` | `POST` | `{"success": bool, "message": str}` |

## Database and export helpers

| Route | Method | Response shape |
| --- | --- | --- |
| `/admin/database-info` | `GET` | JSON database summary object |
| `/admin/database-tables` | `GET` | JSON list of database tables |
| `/admin/database-excel-export` | `POST` | JSON export result or error object when called via AJAX |
| `/admin/image-metadata/status` | `GET` | Metadata processing status JSON |

## Taxonomy and grading helpers

| Route | Method | Response shape |
| --- | --- | --- |
| `/admin/linked-grading` | `GET` | `{"diseases": array, "links": array}` |
| `/admin/linked-grading` | `POST` | `{"success": true}` or `{"error": str}` |
| `/admin/linked-grading/<link_id>` | `GET`/`POST` | HTML page or redirect flow, not JSON |
| `/admin/disease-gradings/<grading_id>/features` | `GET` | `{"features": array}` or `{"error": str}` |
| `/admin/ai-models/<item_id>/health` | `POST` | `{"success": bool, "message": str}` |

## Notes

- Most admin JSON routes are protected by `admin` or `data_manager`.
- Keep these contracts stable for dashboard JS consumers; if keys change, update this page in the same change.
