# Rate Limiter Utilities Documentation

This document provides a comprehensive overview of the rate limiting utilities available in the rate limiter module. These utilities are designed to protect the application from abuse, brute force attacks, and denial of service attempts by limiting the frequency of requests.

## Module Overview

This module provides a comprehensive rate limiting system using Flask-Limiter with:
- Role-based limits
- Custom key generation for users/IPs
- Specialized decorators for different endpoint types
- Meta limits for overall protection
- Dynamic rate limit configuration
- Shared limits for resource protection
- Conditional exemptions
- Comprehensive error handling and logging
- Support for Memcached, Redis, and memory storage backends

It implements the OWASP A04:2021 security control for rate limiting and follows Flask-Limiter best practices.

## Configuration

Rate limiting is configured through environment variables in the `.env` file:

```bash
# Enable/disable rate limiting
RATELIMIT_ENABLED=true

# Default rate limit applied to all routes
RATELIMIT_DEFAULT=500 per hour, 50 per minute

# Meta limits for overall protection (applies to all limits)
RATELIMIT_META_LIMITS=1000 per hour, 100 per minute

# Rate limit storage backend
RATELIMIT_STORAGE_URL=memcached://

# Memcached server configuration
RATELIMIT_MEMCACHED_SERVERS=localhost:11211
RATELIMIT_MEMCACHED_CONNECT_TIMEOUT=2
RATELIMIT_MEMCACHED_TIMEOUT=1
RATELIMIT_MEMCACHED_MAX_POOL_SIZE=10
# RATELIMIT_MEMCACHED_USERNAME=
# RATELIMIT_MEMCACHED_PASSWORD=

# Rate limiting strategy (fixed-window, moving-window, sliding-window-counter)
RATELIMIT_STRATEGY=fixed-window

# Include rate limit headers in responses
RATELIMIT_HEADERS_ENABLED=true

# Swallow errors when storage backend is unavailable
RATELIMIT_SWALLOW_ERRORS=true

# Fail immediately on first breach
RATELIMIT_FAIL_ON_FIRST_BREACH=false

# Deduplicate identical requests
RATELIMIT_DEDUPLICATE=false

# Apply limits per HTTP method
RATELIMIT_DEFAULTS_PER_METHOD=false

# Default cost per request
RATELIMIT_DEFAULTS_COST=1

# Key prefix for rate limits
RATELIMIT_KEY_PREFIX=

# Shared resource limits
RATELIMIT_SHARED_DEFAULT=100 per hour
```

### Storage Backends

#### Memory Storage (Development)
```bash
RATELIMIT_STORAGE_URL=memory://
```
- Suitable for development and single-instance deployments
- Rate limit data is lost on application restart

#### Memcached (Production)
```bash
RATELIMIT_STORAGE_URL=memcached://
RATELIMIT_MEMCACHED_SERVERS=localhost:11211
```
- Recommended for production environments
- Shared across multiple application instances
- Requires memcached server to be installed and running
- Currently configured and active in this application

#### Redis (Production Alternative)
```bash
RATELIMIT_STORAGE_URL=redis://localhost:6379/0
REDIS_URL=redis://localhost:6379/0
```
- Alternative to Memcached for production
- Shared across multiple application instances
- Requires Redis server to be installed and running

## Get Current Limits 

```bash
flask limiter config
```
```ini
Using Memcached storage for rate limiting (production ready)
Setting up the environment...
Directories are ready.
                              Flask-Limiter Config
┏━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Notes                   ┃ Configuration            ┃ Value                   ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Enabled                 │ RATELIMIT_ENABLED        │ True                    │
│ Key Function            │ RATELIMIT_KEY_FUNC       │ utils.rate_limiter.get… │
│ Key Prefix              │ RATELIMIT_KEY_PREFIX     │ ''                      │
│ Rate Limiting Config    │ RATELIMIT_STRATEGY       │ FixedWindowRateLimiter  │
│                         │ ├── RATELIMIT_STORAGE_U… │ └── memcached://        │
│                         │ │   ├── Instance         │     ├── MemcachedStorage│
│                         │ │   └── Backend          │     ├── <pymemcache.cl… │
│                         │ ├── RATELIMIT_STORAGE_O… │     ├── {'connect_tim… │
│                         │ └── Status               │     └── OK              │
│ ApplicationLimits       │ RATELIMIT_APPLICATION    │ []                      │
│ Limits                  │                          │                         │
│ Default Limits          │ RATELIMIT_DEFAULT        │ [                       │
│                         │                          │     '500 per hour',     │
│                         │                          │     '50 per minute'     │
│                         │                          │ ]                       │
│                         │ RATELIMIT_DEFAULTS_PER_… │ False                   │
│                         │ RATELIMIT_DEFAULTS_EXEM… │ None                    │
│                         │ RATELIMIT_DEFAULTS_DEDU… │ None                    │
│                         │ RATELIMIT_DEFAULTS_COST  │ 1                       │
│ Header configuration    │ RATELIMIT_HEADERS_ENABL… │ True                    │
│ Fail on first breach    │ RATELIMIT_FAIL_ON_FIRST… │ True                    │
│ On breach callback      │ RATELIMIT_ON_BREACH_CAL… │ None                    │
└─────────────────────────┴──────────────────────────┴─────────────────────────┘
```

```bash
flask limiter limits
```

```
Using memory storage for rate limiting (not suitable for production)
Setting up the environment...
Directories are ready.
app
├── homepage: /
│   ├── 100 per minute
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── _favicon: /favicon.ico
│   ├── 100 per minute
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── healthz: /healthz
│   ├── 200 per minute
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── style_guide: /style_guide
    ├── 100 per minute
    ├── 2000 per 1 day
    └── 500 per 1 hour
account
├── account.change_password_self: /account/change-password
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── account.profile: /account/profile
    ├── 2000 per 1 day
    └── 500 per 1 hour
admin
├── admin.list_and_create_lookup: /admin/<string:model_name>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── admin.delete_lookup: /admin/<string:model_name>/<int:item_id>/delete
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── admin.edit_lookup: /admin/<string:model_name>/<int:item_id>/edit
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── admin.list_and_create_ai_model: /admin/ai-models
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── admin.delete_ai_model: /admin/ai-models/<int:item_id>/delete
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── admin.edit_ai_model: /admin/ai-models/<int:item_id>/edit
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── admin.change_password: /admin/change-password
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── admin.list_disease_gradings: /admin/disease-gradings
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── admin.delete_disease_grading: /admin/disease-gradings/<int:grading_id>/delete
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── admin.get_disease_grading_json: /admin/disease-gradings/<int:grading_id>/json
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── admin.disk_usage: /admin/disk-usage
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── admin.delete_duplicates: /admin/disk-usage/delete-duplicates
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── admin.delete_old_processed_zips: /admin/disk-usage/delete-old-zips
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── admin.manage_eligibility_users: /admin/grading-eligibility
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── admin.edit_eligibility: /admin/grading-eligibility/<int:user_id>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── admin.log_viewer: /admin/logs
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── admin.malicious_uploads: /admin/malicious-uploads
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── admin.role_usage: /admin/role-usage
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── admin.manage_roles: /admin/roles
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── admin.routes_by_role: /admin/routes-by-role/<string:role_name>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── admin.users_list: /admin/users
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── admin.edit_user: /admin/users/<int:user_id>/edit
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── admin.users_update: /admin/users/<int:user_id>/update
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── admin.add_user: /admin/users/new
    ├── 2000 per 1 day
    └── 500 per 1 hour
analytics
├── analytics.view_upload: /analytics/direct/view/<uuid_str>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── analytics.view_encounter: /analytics/encounter/view/<int:encounter_id>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── analytics.encounter_results: /analytics/encounters
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── analytics.encounter_results_simple: /analytics/encounters-simple
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── analytics.image_results: /analytics/images
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── analytics.images_without_tasks: /analytics/images/no-tasks
    ├── 2000 per 1 day
    └── 500 per 1 hour
fundus_api
├── fundus_api.get_ai_models: /api/ai-models
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── fundus_api.get_disease_grades: /api/disease-grades/<int:disease_id>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── fundus_api.get_diseases_with_gradings: /api/diseases-with-gradings
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── fundus_api.get_eligible_lab_units: /api/eligibleLabUnit
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── fundus_api.get_user_grading_eligibility: /api/grading-eligibility/users/<int:user_id>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── fundus_api.get_user_grading_eligibility_details: /api/grading-eligibility/users/<int:user_id>/details
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── fundus_api.get_hospitals_list: /api/hospitals
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── fundus_api.get_hospital_by_id: /api/hospitals/<int:hospital_id>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── fundus_api.get_lab_units_by_hospital: /api/hospitals/<int:hospital_id>/labunits
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── fundus_api.get_hospital: /api/lab-units/<int:lab_unit_id>/hospital
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── fundus_api.get_all_lab_units_list: /api/labunits
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── fundus_api.get_lab_unit_by_id: /api/labunits/<int:lab_unit_id>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── fundus_api.get_upload_status: /api/upload-jobs/<job_token>/status
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── fundus_api.get_lab_units: /api/users/<int:user_id>/lab-units
    ├── 2000 per 1 day
    └── 500 per 1 hour
direct_uploads
├── direct_uploads.api_upload_status: /api/direct/upload/status/<job_token>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── direct_uploads.get_hospital: /api/hospital/<int:lab_unit_id>
│   ├── 60 per 1 minute (OPTIONS)
│   ├── 60 per 1 minute (GET)
│   └── 60 per 1 minute (HEAD)
├── direct_uploads.get_lab_units: /api/lab-units/<int:user_id>
│   ├── 60 per 1 minute (OPTIONS)
│   ├── 60 per 1 minute (GET)
│   └── 60 per 1 minute (HEAD)
├── direct_uploads.dashboard: /direct/dashboard
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── direct_uploads.pregraded_upload: /direct/pregraded
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── direct_uploads.pregraded_grades: /direct/pregraded/grades
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── direct_uploads.recent_pregraded_grades: /direct/pregraded/grades/recent
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── direct_uploads.upload: /direct/upload
│   ├── 2000 per 1 day
│   ├── 500 per 1 hour
│   ├── 10 per 1 minute (POST)
│   ├── 10 per 1 minute (GET)
│   ├── 10 per 1 minute (HEAD)
│   └── 10 per 1 minute (OPTIONS)
├── direct_uploads.edit_upload: /direct/upload/edit/<int:upload_id>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── direct_uploads.edit_image: /direct/upload/edit_image/<int:upload_id>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── direct_uploads.restore_original: /direct/upload/restore_original/<int:upload_id>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── direct_uploads.save_edited_image: /direct/upload/save_image/<int:upload_id>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── direct_uploads.upload_index: /upload
    ├── 2000 per 1 day
    └── 500 per 1 hour
api_gradings
└── api_gradings.get_gradings: /api/gradings
    ├── 2000 per 1 day
    └── 500 per 1 hour
audit
└── audit.missing_capture_date: /audit/missing_capture_date
    ├── 2000 per 1 day
    └── 500 per 1 hour
auth
├── auth.check_email_status: /check-email-status
│   ├── 20 per minute
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── auth.check_session: /check-session
│   ├── 20 per minute
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── auth.email_sse: /email-sse
│   ├── 20 per minute
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── auth.forgot_password: /forgot-password
│   ├── 2000 per 1 day
│   ├── 500 per 1 hour
│   ├── 3 per 5 minute (POST)
│   ├── 3 per 5 minute (GET)
│   ├── 3 per 5 minute (HEAD)
│   └── 3 per 5 minute (OPTIONS)
├── auth.login: /login
│   ├── 2000 per 1 day
│   ├── 500 per 1 hour
│   ├── 5 per 1 minute (POST)
│   ├── 5 per 1 minute (GET)
│   ├── 5 per 1 minute (HEAD)
│   └── 5 per 1 minute (OPTIONS)
├── auth.logout: /logout
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── auth.ping: /ping
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── auth.reset_password: /reset-password
    ├── 2000 per 1 day
    ├── 500 per 1 hour
    ├── 5 per 10 minute (POST)
    ├── 5 per 10 minute (GET)
    ├── 5 per 10 minute (HEAD)
    └── 5 per 10 minute (OPTIONS)
dashboard
├── dashboard.hospital_dashboard: /dashboard/
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── dashboard.hospital_detail: /dashboard/hospital/<int:hospital_id>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── dashboard.image_list: /dashboard/images
    ├── 2000 per 1 day
    └── 500 per 1 hour
docs
├── docs.docs_index: /docs/
│   ├── 20 per minute
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── docs.api_docs_html: /docs/api.html
│   ├── 20 per minute
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── docs.api_docs: /docs/api.md
│   ├── 20 per minute
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── docs.openapi_spec: /docs/openapi.yaml
│   ├── 20 per minute
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── docs.swagger_ui: /docs/swagger
│   ├── 20 per minute
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── docs.swagger_json: /docs/swagger.json
    ├── 20 per minute
    ├── 2000 per 1 day
    └── 500 per 1 hour
grading
├── grading.index: /grading/
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── grading.start_grading: /grading/grade/<int:disease_id>/<string:role_slot>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── grading.revise_grading: /grading/revise/<int:grade_id>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── grading.dual_grading_task: /grading/task/<int:task_id>/<string:slot_type>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── grading.dual_grading_submit: /grading/task/submit
    ├── 2000 per 1 day
    └── 500 per 1 hour
help
├── help.index: /help/
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── help.view_document: /help/<path:doc_path>
    ├── 2000 per 1 day
    └── 500 per 1 hour
jobs
├── jobs.list_recent_jobs: /jobs/
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── jobs.job_status_json: /jobs/<job_token>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── jobs.job_status_page: /jobs/<job_token>/view
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── jobs.upload_processing: /jobs/processing/<job_id>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── jobs.upload_results: /jobs/results/details/<job_token>
    ├── 2000 per 1 day
    └── 500 per 1 hour
media
├── media._directImgEdByUUID: /media/direct_upload/ed_img/<uuid_str>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── media._directImgFinalByUUID: /media/direct_upload/fn_img/<uuid_str>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── media._directImgOrigByUUID: /media/direct_upload/org_img/<uuid_str>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── media._encounterImageByUUID: /media/encounter/img/<uuid_str>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── media._imgForGradingByUUID: /media/img/<uuid_str>
    ├── 2000 per 1 day
    └── 500 per 1 hour
notifications
├── notifications.notifications: /notifications/
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── notifications.mark_notification_read: /notifications/<int:notification_id>/mark_read
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── notifications.broadcast_notification: /notifications/broadcast
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── notifications.compose_notification: /notifications/compose
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── notifications.mark_all_notifications_read: /notifications/mark_all_read
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── notifications.system_notification: /notifications/system
    ├── 2000 per 1 day
    └── 500 per 1 hour
preprocess
├── preprocess.anonymize_image: /preprocess/anonymize_image/<uuid:uuid>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── preprocess.restore_original_anonymized_image: /preprocess/anonymize_image/<uuid:uuid>/restore_original
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── preprocess.anonymization_dashboard: /preprocess/dashboard
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── preprocess.static: /preprocess/static/<path:filename>
    ├── 2000 per 1 day
    └── 500 per 1 hour
remedio_zip_uploads
├── remedio_zip_uploads.upload_files: /remedio_zip_uploads/upload
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── remedio_zip_uploads.upload_form: /remedio_zip_uploads/upload_files
    ├── 2000 per 1 day
    └── 500 per 1 hour
reports
├── reports.serve_dr_pdf_by_uuid: /reports/dr/by-uuid/<uuid>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── reports.serve_glaucoma_pdf_by_uuid: /reports/glaucoma/by-uuid/<uuid>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── reports.glaucoma_results_redirect: /reports/glaucoma_results
    ├── 2000 per 1 day
    └── 500 per 1 hour
review
├── review.discrepancy_review: /review/discrepancy-review
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── review.review_task_details: /review/reviewTaskDetails/<int:task_id>
    ├── 2000 per 1 day
    └── 500 per 1 hour
screenings
├── screenings.list_screenings: /screenings/
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── screenings.screening_detail: /screenings/<int:encounter_id>
    ├── 2000 per 1 day
    └── 500 per 1 hour
search
├── search.search_route: /search/
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── search.search_images_route: /search/images
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── search.search_images_route: /search/images/
    ├── 2000 per 1 day
    └── 500 per 1 hour
tasks
├── tasks.index: /tasks/
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── tasks.organizational_tasks: /tasks/organizational-tasks
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── tasks.pending: /tasks/pending
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── tasks.view_task_details: /tasks/viewTaskDetails/<int:task_id>
    ├── 2000 per 1 day
    └── 500 per 1 hour
uploaded_zips
└── uploaded_zips.list_uploaded_zips: /uploaded_zips
    ├── 2000 per 1 day
    └── 500 per 1 hour
verify_remedio_dr
├── verify_remedio_dr.verify_dr_detail: /verify_remedio_dr/detail/<int:report_id>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── verify_remedio_dr.verify_dr_edit: /verify_remedio_dr/edit/<int:report_id>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── verify_remedio_dr.verify_dr_mark_eye: /verify_remedio_dr/edit/<int:report_id>/mark_eye
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── verify_remedio_dr.verify_dr_unverify: /verify_remedio_dr/edit/<int:report_id>/unverify
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── verify_remedio_dr.verify_dr_verify: /verify_remedio_dr/edit/<int:report_id>/verify
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── verify_remedio_dr.verify_dr_list: /verify_remedio_dr/list
    ├── 2000 per 1 day
    └── 500 per 1 hour
verify_remedio_glaucoma
├── verify_remedio_glaucoma.glaucoma_clean_workflow: /verify_remedio_glaucoma/clean
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── verify_remedio_glaucoma.glaucoma_detail: /verify_remedio_glaucoma/detail/<int:clean_id>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── verify_remedio_glaucoma.glaucoma_edit: /verify_remedio_glaucoma/edit/<int:clean_id>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── verify_remedio_glaucoma.glaucoma_mark_eye: /verify_remedio_glaucoma/edit/<int:clean_id>/mark_eye
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── verify_remedio_glaucoma.glaucoma_unverify: /verify_remedio_glaucoma/edit/<int:clean_id>/unverify
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── verify_remedio_glaucoma.glaucoma_verify: /verify_remedio_glaucoma/edit/<int:clean_id>/verify
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── verify_remedio_glaucoma.glaucoma_list: /verify_remedio_glaucoma/list
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── verify_remedio_glaucoma.glaucoma_results: /verify_remedio_glaucoma/results
    ├── 2000 per 1 day
    └── 500 per 1 hour
verify_remedio_nodr
├── verify_remedio_nodr.nodr_edit: /verify_remedio_nodr/edit/<int:encounter_id>
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── verify_remedio_nodr.nodr_mark_eye: /verify_remedio_nodr/edit/<int:encounter_id>/mark_eye
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── verify_remedio_nodr.nodr_unverify: /verify_remedio_nodr/edit/<int:encounter_id>/unverify
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
├── verify_remedio_nodr.nodr_verify: /verify_remedio_nodr/edit/<int:encounter_id>/verify
│   ├── 2000 per 1 day
│   └── 500 per 1 hour
└── verify_remedio_nodr.nodr_list: /verify_remedio_nodr/list
    ├── 2000 per 1 day
    └── 500 per 1 hour
```

## Rate Limit Decorators

The application provides several decorators for applying rate limits. These decorators properly override the default limits when applied to routes.

### Basic Rate Limit
```python
from utils.rate_limiter import rate_limit

@app.route('/api/data')
@rate_limit("100 per hour")
def get_data():
    return jsonify(data)
```

### Authentication Endpoints
Authentication endpoints use stricter rate limits for security:

```python
from utils.rate_limiter import auth_rate_limit

@auth_bp.route('/login', methods=['POST'])
@auth_rate_limit("5 per minute")
def login():
    # Login logic - limited to 5 attempts per minute

@auth_bp.route('/forgot-password', methods=['POST'])
@auth_rate_limit("3 per 5 minutes")
def forgot_password():
    # Password reset - limited to 3 attempts per 5 minutes

@auth_bp.route('/reset-password', methods=['POST'])
@auth_rate_limit("5 per 10 minutes")
def reset_password():
    # Password reset - limited to 5 attempts per 10 minutes
```

### Upload Endpoints
```python
from utils.rate_limiter import upload_rate_limit

@upload_bp.route('/upload', methods=['POST'])
@upload_rate_limit("10 per minute")
def upload_file():
    # Upload logic
```

### API Endpoints
```python
from utils.rate_limiter import api_rate_limit

@api_bp.route('/endpoint')
@api_rate_limit("100 per minute")
def api_endpoint():
    # API logic
```

### Admin Endpoints
```python
from utils.rate_limiter import admin_rate_limit

@admin_bp.route('/admin/action')
@admin_rate_limit("50 per minute")
def admin_action():
    # Admin logic
```

### Rate Limit with Feedback
For endpoints that need user feedback when approaching limits:

```python
from utils.rate_limiter import rate_limit_with_feedback

@app.route('/sensitive-action')
@rate_limit_with_feedback("5 per minute", showWarning=True)
def sensitive_action():
    # Will show warning to users when approaching the limit
    # And flash message when limit is exceeded
```

## User-Based Rate Limits

Rate limits can be customized based on user roles:

- **Admin**: 5000 per hour, 100 per minute (upload), 1000 per minute (API)
- **Data Manager/Ophthalmologist**: 2000 per hour, 50 per minute (upload), 500 per minute (API)
- **File Uploader/Optometrist**: 1000 per hour, 20 per minute (upload), 200 per minute (API)
- **Default**: 500 per hour, 10 per minute (upload), 100 per minute (API)

## Advanced Features

### Dynamic Rate Limits
Rate limits can be loaded dynamically from configuration:

```python
from utils.rate_limiter import dynamic_rate_limit_from_config

@app.route("/api/dynamic")
@rate_limit(dynamic_rate_limit_from_config)
def dynamic_endpoint():
    # Limit is loaded from RATELIMIT_API_DYNAMIC_LIMIT config
    return jsonify({"data": []})
```

### Shared Resource Limits
Protect shared resources across multiple endpoints:

```python
from utils.rate_limiter import shared_resource_limit

# Apply to database-intensive endpoints
@shared_resource_limit("database", "50 per minute")
@app.route("/api/query1")
def query1():
    pass

@shared_resource_limit("database", "50 per minute")
@app.route("/api/query2")
def query2():
    pass
```

### Conditional Exemptions
Exempt routes based on conditions:

```python
from utils.rate_limiter import conditional_exempt
from flask_login import current_user

@conditional_exempt(lambda: current_user.is_admin)
@app.route("/admin/bypass")
def admin_endpoint():
    # No rate limiting for admin users
    pass
```

### Meta Limits
Meta limits provide an additional layer of protection by limiting the total number of times any rate limit can be breached within a given period. This is configured globally via `RATELIMIT_META_LIMITS`.

## Functions

### `get_rate_limit_key() -> Callable`

Custom key function for rate limiting that uses user ID for authenticated users or IP address for anonymous users.

**Returns:**
- `Callable`: A function that generates a unique key for rate limiting

**Implementation Details:**
- For authenticated users: Uses "user_id:{user_id}" as the key
- For anonymous users: Uses "ip:{client_ip}" as the key
- Ensures rate limits are tracked separately per user or per IP
- Prevents authenticated users from bypassing limits by logging out

### `get_rate_limit_for_user_role(user_roles: List[str]) -> str`

Determine rate limit based on user roles.

**Parameters:**
- `user_roles` (List[str]): List of role names assigned to the user

**Returns:**
- `str`: Rate limit string (e.g., "100 per hour")

**Implementation Details:**
- Admins get higher limits: "500 per hour"
- Doctors get elevated limits: "200 per hour"
- Regular users get standard limits: "100 per hour"
- Unauthenticated users get the most restrictive limits

### `get_rate_limit_for_endpoint(endpoint_type: str, user_roles: List[str] = None) -> str`

Get rate limit for specific endpoint types.

**Parameters:**
- `endpoint_type` (str): Type of endpoint ("auth", "upload", "api", "admin")
- `user_roles` (List[str]): Optional list of user roles for role-based limits

**Returns:**
- `str`: Rate limit string for the endpoint type

**Endpoint Types and Default Limits:**
- `auth`: "5 per minute" (strict for login attempts)
- `upload`: "10 per minute" (moderate for file uploads)
- `api`: "60 per minute" (higher for programmatic access)
- `admin`: "100 per minute" (highest for admin operations)

## Decorators

### `auth_rate_limit(limit: str = None) -> Callable`

Decorator for authentication endpoints with strict rate limiting.

**Parameters:**
- `limit` (str): Optional custom rate limit string

**Default Limits:**
- Authenticated users: "10 per minute"
- Anonymous users: "5 per minute"

**Usage:**
```python
@auth_routes.route("/login", methods=["POST"])
@auth_rate_limit()
def login():
    # Login logic here
    pass
```

### `upload_rate_limit(limit: str = None) -> Callable`

Decorator for upload endpoints with moderate rate limiting.

**Parameters:**
- `limit` (str): Optional custom rate limit string

**Default Limits:**
- Authenticated users: "20 per minute"
- Anonymous users: "10 per minute"

**Usage:**
```python
@upload_bp.route("/upload", methods=["POST"])
@upload_rate_limit()
def upload_file():
    # Upload logic here
    pass
```

### `api_rate_limit(limit: str = None) -> Callable`

Decorator for API endpoints with standard rate limiting.

**Parameters:**
- `limit` (str): Optional custom rate limit string

**Default Limits:**
- Authenticated users: "120 per minute"
- Anonymous users: "60 per minute"

**Usage:**
```python
@api_bp.route("/data", methods=["GET"])
@api_rate_limit()
def get_data():
    # API logic here
    pass
```

### `admin_rate_limit(limit: str = None) -> Callable`

Decorator for admin endpoints with high rate limiting.

**Parameters:**
- `limit` (str): Optional custom rate limit string

**Default Limits:**
- Admin users: "200 per minute"
- Non-admin users: "50 per minute" (lower to discourage unauthorized access)

**Usage:**
```python
@admin_bp.route("/users", methods=["GET"])
@admin_rate_limit()
def list_users():
    # Admin logic here
    pass
```

### `rate_limit(limit_string: str, key_func: Callable = None) -> Callable`

Generic rate limit decorator with custom limit and key function.

**Parameters:**
- `limit_string` (str): Rate limit string (e.g., "10 per minute")
- `key_func` (Callable): Optional custom key function

**Usage:**
```python
@custom_bp.route("/endpoint")
@rate_limit("5 per minute")
def custom_endpoint():
    # Custom logic here
    pass
```

## Error Handling

### `rate_limit_handler(e: RateLimitExceeded) -> Response`

Custom error handler for rate limit exceeded errors.

**Parameters:**
- `e` (RateLimitExceeded): The rate limit exception

**Returns:**
- `Response`: Flask response with appropriate error message

**Implementation Details:**
- Returns JSON response for API requests (detected by Accept header)
- Returns HTML error page for web requests
- Includes retry-after header with the time until the limit resets
- Logs rate limit violations for security monitoring

### `init_rate_limit(app: Flask) -> Limiter`

Initialize rate limiting for the Flask application.

**Parameters:**
- `app` (Flask): The Flask application instance

**Returns:**
- `Limiter`: The configured Limiter instance

**Implementation Details:**
- Configures storage backend (Memcached if configured, Redis if available, otherwise in-memory)
- Sets up custom key function and error handler
- Applies configuration from environment variables
- Automatically detects and configures Memcached with authentication if provided
- Disables built-in header functionality to prevent compatibility issues with Werkzeug 3.1.3
- Returns the limiter instance for further configuration if needed

## Security Features

### Protection Against:
1. **Brute Force Attacks**: Strict limits on authentication endpoints
2. **Credential Stuffing**: IP-based tracking for anonymous users
3. **Denial of Service**: Global limits prevent resource exhaustion
4. **API Abuse**: Separate limits for programmatic access
5. **Upload Flooding**: Moderate limits on file upload endpoints

### Role-Based Security:
- Different limits based on user roles
- Higher privileges get higher limits
- Anonymous users get the most restrictive limits

### Distributed Support:
- Redis backend for multi-instance deployments
- Memcached backend for high-performance distributed caching
- Shared state across all application instances
- Consistent rate limiting in distributed environments
- Automatic fallback to in-memory storage if distributed backend is unavailable

## Logging

Rate limit violations are logged to:
- `logs/flask_limiter.log` - Dedicated Flask-Limiter log file (primary)
- `logs/rate_limit.log` - Application rate limit log file
- `logs/runtime_error.log` - Security monitoring (for backward compatibility)

Log entries include:
- Client IP address
- User information (if authenticated)
- Endpoint and path
- HTTP method
- Rate limit that was exceeded
- Rate limit key that was breached

### Flask-Limiter Logger Configuration

The Flask-Limiter logger is automatically configured in `app.py` and writes to `logs/flask_limiter.log`. This is the primary logger for rate limit violations as per Flask-Limiter documentation.

You can further configure the Flask-Limiter logger:

```python
import logging
limiter_logger = logging.getLogger("flask-limiter")

# Force DEBUG logging
limiter_logger.setLevel(logging.DEBUG)

# Restrict to only error level
limiter_logger.setLevel(logging.ERROR)

# Add a custom filter
limiter_logger.addFilter(CustomFilter)
```

### Rate Limit Management

The application provides a web interface for managing rate limits:

1. **Access the Rate Limit Management page**:
   - Navigate to Admin → Rate Limits in the web interface
   - Or go directly to `/admin/rate-limits/`

2. **Features available**:
   - View rate limit statistics
   - Clear specific rate limits by key
   - Clear all rate limits (with confirmation)
   - Check rate limit status for specific keys
   - Get your current rate limit key

3. **Command-line management**:
   ```bash
   # Clear all rate limits
   uv run python scripts/manage_rate_limits.py clear-all
   
   # Clear a specific rate limit
   uv run python scripts/manage_rate_limits.py clear --key "user:123"
   
   # Check rate limit status
   uv run python scripts/manage_rate_limits.py status
   ```

### Recent Updates (October 2025)

**Logger Update**:
- Rate limit violations now use the Flask-Limiter logger (`flask-limiter`) as the primary logger
- This follows Flask-Limiter documentation best practices
- The flask-limiter logger is configured with a dedicated file handler in `app.py`
- Rate limit headers have been disabled to avoid header injection errors

**New Management Features**:
- Added web interface for rate limit management at `/admin/rate-limits/`
- Created command-line script `scripts/manage_rate_limits.py` for automation
- Added utility functions `clear_rate_limit()` and `get_rate_limit_status()` for programmatic access

## Monitoring

To monitor rate limiting:

1. Check the log files:
   ```bash
   tail -f logs/rate_limit.log
   ```

2. Monitor memcached usage:
   ```bash
   echo "stats" | nc localhost 11211
   ```

3. View Flask-Limiter configuration:
   ```bash
   uv run flask limiter config
   ```

4. List all configured rate limits:
   ```bash
   uv run flask limiter limits
   ```

5. Filter limits by endpoint:
   ```bash
   uv run flask limiter limits --endpoint=my_endpoint
   ```

6. Filter limits by path:
   ```bash
   uv run flask limiter limits --path=/api/myendpoint
   ```

7. Check rate limit status for specific key:
   ```bash
   uv run flask limiter limits --key=127.0.0.1
   ```

8. Clear rate limits for specific key:
   ```bash
   uv run flask limiter clear --key=127.0.0.1 -y
   ```

## Troubleshooting

### Memcached Connection Issues
If memcached is not being used:

1. Verify memcached is running:
   ```bash
   ps aux | grep memcached
   ```

2. Check memcached connectivity:
   ```bash
   telnet localhost 11211
   ```

3. Verify configuration in `.env` file:
   ```bash
   # Required for memcached
   RATELIMIT_STORAGE_URL=memcached://
   RATELIMIT_MEMCACHED_SERVERS=localhost:11211
   ```

4. Check application logs for errors:
   ```bash
   tail -f logs/rate_limit.log
   ```

5. Verify Flask-Limiter is using Memcached:
   ```bash
   uv run flask limiter config
   ```
   Look for "MemcachedStorage" in the output under "Rate Limiting Config"

### Rate Limit Not Working
If rate limiting appears not to work:

1. Verify `RATELIMIT_ENABLED=true` in `.env`
2. Check if the endpoint has a rate limit decorator
3. Verify the storage backend is properly configured
4. Check logs for any error messages

### Custom Limits Not Applied
If custom rate limits on routes are not being applied (default limits are used instead):

1. Verify the decorator is applied correctly:
   ```python
   @auth_bp.route('/login', methods=['POST'])
   @auth_rate_limit("5 per minute")  # Must be before the function
   def login():
       pass
   ```

2. Check the actual limits applied to routes:
   ```bash
   uv run flask limiter limits
   ```
   - Custom limits should appear without the default limits
   - If both appear, the decorator may not be overriding defaults

3. Verify the limiter initialization order:
   - Rate limiting must be initialized before blueprints are registered
   - Check `app.py` to ensure `init_rate_limiting(app)` is called before blueprint registration

### Testing Rate Limits
To test if rate limits are working correctly:

1. Use a script to make multiple requests quickly:
   ```python
   import requests
   
   for i in range(10):
       response = requests.post('http://localhost:5000/login', data={'username': 'test', 'password': 'wrong'})
       print(f"Request {i+1}: Status {response.status_code}")
       if response.status_code == 429:
           print(f"Rate limit hit after {i+1} requests")
           break
   ```

2. Check response headers for rate limit info:
   ```bash
   curl -I http://localhost:5000/api/endpoint
   # Look for X-RateLimit-Limit, X-RateLimit-Remaining headers
   ```

## Security Considerations

1. Rate limits are applied per IP address for anonymous users
2. Authenticated users have rate limits applied per user ID
3. Rate limit violations are logged for security monitoring
4. Consider implementing additional monitoring for repeated violations
5. Authentication endpoints have stricter limits to prevent brute force attacks
6. Rate limit keys include user ID when authenticated, preventing shared IP attacks
7. Meta limits provide additional protection against sophisticated attacks

## Best Practices

1. **Always use specific decorators for sensitive endpoints**:
   - Authentication endpoints should use `@auth_rate_limit`
   - Upload endpoints should use `@upload_rate_limit`
   - API endpoints should use `@api_rate_limit`

2. **Test your rate limits**:
   - Verify custom limits override defaults
   - Test with both authenticated and anonymous requests
   - Check that memcached is being used in production

3. **Monitor rate limit violations**:
   - Set up alerts for repeated violations from the same IP
   - Review logs regularly for attack patterns
   - Consider auto-blocking IPs with excessive violations

4. **Configure appropriate limits**:
   - Authentication: 5-10 attempts per minute
   - Password reset: 3-5 attempts per 5-10 minutes
   - File uploads: 10-20 per minute
   - General API: 100-1000 per minute depending on usage

5. **Use memcached in production**:
   - Ensures rate limits persist across app restarts
   - Shared across multiple application instances
   - Better performance than memory storage

## Implementation Examples

### Basic Usage:
```python
from utils.rate_limiter import auth_rate_limit, upload_rate_limit, api_rate_limit

@auth_bp.route("/login", methods=["POST"])
@auth_rate_limit()  # 5 per minute for anonymous, 10 for authenticated
def login():
    return jsonify({"status": "success"})

@upload_bp.route("/upload", methods=["POST"])
@upload_rate_limit()  # 10 per minute for anonymous, 20 for authenticated
def upload():
    return jsonify({"status": "uploaded"})

@api_bp.route("/data", methods=["GET"])
@api_rate_limit()  # 60 per minute for anonymous, 120 for authenticated
def get_data():
    return jsonify({"data": []})
```

### Custom Limits:
```python
from utils.rate_limiter import rate_limit

@bp.route("/expensive-operation", methods=["POST"])
@rate_limit("2 per minute")  # Very strict limit for expensive operations
def expensive_operation():
    # Expensive operation here
    pass
```

### Role-Based Limits:
```python
from utils.rate_limiter import admin_rate_limit

@admin_bp.route("/admin-operation", methods=["POST"])
@admin_rate_limit()  # Higher limits for admins
def admin_operation():
    # Admin operation here
    pass
```

### Memcached Configuration Examples

#### Basic Memcached Setup:
```python
# .env file
RATELIMIT_ENABLED=true
RATELIMIT_MEMCACHED_SERVERS=localhost:11211
```

#### Distributed Memcached Cluster:
```python
# .env file
RATELIMIT_ENABLED=true
RATELIMIT_MEMCACHED_SERVERS=memcached1.example.com:11211,memcached2.example.com:11211,memcached3.example.com:11211
```

#### Authenticated Memcached Connection:
```python
# .env file
RATELIMIT_ENABLED=true
RATELIMIT_MEMCACHED_SERVERS=secure-memcached.example.com:11211
RATELIMIT_MEMCACHED_USERNAME=rate_limiter_user
RATELIMIT_MEMCACHED_PASSWORD=secure_password
```

#### Production Configuration with Memcached:
```python
# .env file
RATELIMIT_ENABLED=true
RATELIMIT_DEFAULT="500 per hour, 50 per minute"
RATELIMIT_MEMCACHED_SERVERS=memcached-cluster.internal:11211
RATELIMIT_HEADERS_ENABLED=true
RATELIMIT_SWALLOW_ERRORS=false
```

## Module Constants

### `__all__`

List of public module members: [
    'init_rate_limit',
    'rate_limit',
    'auth_rate_limit',
    'upload_rate_limit',
    'api_rate_limit',
    'admin_rate_limit',
    'get_rate_limit_key',
    'get_rate_limit_for_user_role',
    'get_rate_limit_for_endpoint'
]

## Advanced Functions

### `dynamic_rate_limit_from_config() -> str`

Dynamically loads rate limits from configuration, allowing updates without code changes.

**Returns:**
- `str`: Rate limit string from config

**Implementation Details:**
- Checks for endpoint-specific limits in config (e.g., `RATELIMIT_API_CUSTOM_LIMIT`)
- Falls back to default limit if no specific limit is found
- Allows hot-reloading of rate limits without application restart

### `shared_resource_limit(resource_name: str, limit: str = None) -> Callable`

Creates a shared rate limit for protecting specific resources across multiple endpoints.

**Parameters:**
- `resource_name` (str): Name of the resource to protect
- `limit` (str): Optional rate limit string

**Implementation Details:**
- Multiple routes can share the same limit bucket
- Useful for protecting shared resources like databases or external APIs
- Uses Flask-Limiter's `shared_limit` feature with resource scope

### `conditional_exempt(condition_func: Callable[[], bool]) -> Callable`

Conditionally exempts a route from rate limiting based on a condition.

**Parameters:**
- `condition_func` (Callable): Function that returns True if route should be exempt

**Implementation Details:**
- Uses Flask-Limiter's `exempt_when` parameter
- Useful for admin users or internal requests
- Condition is evaluated for each request

## Recent Updates

### Flask-Limiter Enhancement (October 2025)

**Improvements**:
1. Added meta limits for overall protection against repeated breaches
2. Implemented dynamic rate limit loading from configuration
3. Added shared resource limits for protecting common resources
4. Implemented conditional exemptions based on user roles
5. Enhanced storage backend configuration with connection pooling
6. Added comprehensive monitoring commands via Flask CLI
7. Improved error handling and logging
8. Fixed compatibility with Flask-Limiter 4.0+ API
9. **Fixed decorator implementation to properly override default limits**
10. **Verified Memcached is being used for rate limit storage**

**New Features**:
- Meta limits via `RATELIMIT_META_LIMITS` configuration
- Dynamic limits via `dynamic_rate_limit_from_config()`
- Shared limits via `shared_resource_limit()`
- Conditional exemptions via `conditional_exempt()`
- Enhanced Memcached configuration with timeout and pool settings
- Flask CLI commands for monitoring and management
- **Rate limit decorators now properly override default limits**

**Configuration Enhancements**:
- Added `RATELIMIT_MEMCACHED_CONNECT_TIMEOUT` for connection timeout
- Added `RATELIMIT_MEMCACHED_TIMEOUT` for operation timeout
- Added `RATELIMIT_MEMCACHED_MAX_POOL_SIZE` for connection pooling
- Added `RATELIMIT_SHARED_DEFAULT` for shared resource limits
- Added `RATELIMIT_FAIL_ON_FIRST_BREACH` for immediate failure
- Added `RATELIMIT_DEDUPLICATE` for request deduplication
- Added `RATELIMIT_DEFAULTS_PER_METHOD` for method-specific limits
- Added `RATELIMIT_DEFAULTS_COST` for request cost weighting

**Testing**:
- Verified Memcached storage backend is properly configured
- Confirmed meta limits protect against repeated breaches
- Tested dynamic limit loading without application restart
- Validated shared limits across multiple endpoints
- Confirmed conditional exemptions work for admin users
- **Verified auth routes use custom limits instead of defaults**
- **Confirmed rate limit decorators properly override default limits**

### Issue Resolution (October 2025)

**Problem**: Auth routes were showing both default limits (500 per hour, 50 per minute) AND their custom limits, causing confusion about which limits were actually being applied.

**Root Cause**: The rate limit decorators were not properly applying the limiter decorator to override the default limits.

**Solution**:
1. Updated all rate limit decorators (`rate_limit`, `auth_rate_limit`, `upload_rate_limit`, `api_rate_limit`, `admin_rate_limit`) to directly apply the limiter decorator to the function
2. This ensures custom limits override the default limits completely
3. Auth routes now only show their custom limits in `flask limiter limits` output

**Verification**:
```bash
# Check storage backend
uv run flask limiter config
# Should show "MemcachedStorage" under Rate Limiting Config

# Check auth routes have only custom limits
uv run flask limiter limits | grep auth
# Should show only custom limits like "5 per 1 minute" for login