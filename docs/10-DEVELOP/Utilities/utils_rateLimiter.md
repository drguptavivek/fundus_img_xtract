# Rate Limiter Utilities Documentation

This document provides an overview of the rate limiting utilities available in the rate limiter module. These utilities are designed to protect the application from abuse, brute force attacks, and denial of service attempts by limiting the frequency of requests.

## Module Overview

This module provides a comprehensive rate limiting system using Flask-Limiter with role-based limits, custom key generation, and specialized decorators for different endpoint types. It implements the OWASP A04:2021 security control for rate limiting.

## Get CUrrent Limits 

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

## Configuration

The rate limiter can be configured through environment variables:

### Basic Configuration
- `RATELIMIT_ENABLED`: Enable/disable rate limiting (default: "true")
- `RATELIMIT_DEFAULT`: Default rate limit string applied to all routes (default: "500 per hour, 50 per minute")
- `RATELIMIT_STORAGE_URL`: Storage backend URL (memory://, redis://, or memcached://)
- `RATELIMIT_KEY_PREFIX`: Prefix for rate limit keys (default: empty)
- `RATELIMIT_STRATEGY`: Rate limiting strategy - fixed-window, moving-window, or fixed-window-elastic-expiry (default: "fixed-window")

### Storage Backend Configuration
- `RATELIMIT_MEMCACHED_SERVERS`: Comma-separated list of Memcached servers (e.g., "localhost:11211")
- `RATELIMIT_MEMCACHED_USERNAME`: Username for authenticated Memcached connections (optional)
- `RATELIMIT_MEMCACHED_PASSWORD`: Password for authenticated Memcached connections (optional)
- `REDIS_URL`: Redis URL for distributed rate limiting (optional)

### Headers Configuration
- `RATELIMIT_HEADERS_ENABLED`: Enable rate limit headers in responses (default: "false" - disabled for compatibility with Werkzeug 3.1.3)
- `RATELIMIT_HEADER_RESET`: Include X-RateLimit-Reset header with Unix timestamp (default: "false")
- `RATELIMIT_HEADER_REMAINING`: Include X-RateLimit-Remaining header (default: "true")

**Note**: Due to a compatibility issue between Flask-Limiter (>=3.8.0) and Werkzeug (3.1.3), the built-in header functionality is disabled. Instead, custom headers are added via the `@app.after_request` handler in `app.py`.

### Behavior Configuration
- `RATELIMIT_FAIL_ON_FIRST_BREACH`: Fail immediately on first breach instead of waiting for window to reset (default: "false")
- `RATELIMIT_SWALLOW_ERRORS`: Continue processing when rate limit storage fails (default: "false")
- `RATELIMIT_DEDUPLICATE`: Deduplicate identical requests for rate limiting (default: "false")
- `RATELIMIT_DEFAULTS_PER_METHOD`: Apply rate limits per HTTP method instead of per endpoint (default: "false")
- `RATELIMIT_DEFAULTS_COST`: Cost per request for rate limiting (default: "1")
- `RATELIMIT_DEFAULTS_EXEMPT`: Comma-separated list of route patterns to exempt from rate limiting

### Advanced Configuration
- `RATELIMIT_KEY_FUNC`: Custom key function class (advanced usage)
- `RATELIMIT_ON_BREACH`: Custom function to call when rate limit is breached
- `RATELIMIT_APPLICATION`: Application-wide rate limits that override defaults

### Role-Based Configuration
- `ADMIN_RATE_LIMIT`: Custom rate limit for admin users
- `DATA_MANAGER_RATE_LIMIT`: Custom rate limit for data manager users
- `USER_RATE_LIMIT`: Custom rate limit for regular users
- `AUTHENTICATED_RATE_LIMIT`: Custom rate limit for any authenticated user
- `ANONYMOUS_RATE_LIMIT`: Custom rate limit for anonymous users

### Storage Backends

The rate limiter supports multiple storage backends:

1. **In-Memory Storage** (default):
   - Simple, no external dependencies
   - Not suitable for production or multi-instance deployments
   - Rate limits reset on application restart

2. **Redis Storage**:
   - Suitable for production and distributed systems
   - Persistent across application restarts
   - Shared state across multiple application instances
   - Configuration: Set `RATELIMIT_STORAGE_URL` to Redis connection string (e.g., "redis://localhost:6379")

3. **Memcached Storage**:
   - High-performance distributed caching
   - Suitable for production and large-scale deployments
   - Configuration: Set `RATELIMIT_MEMCACHED_SERVERS` to server list (e.g., "server1:11211,server2:11211")
   - Optional authentication with username/password
   - Automatic fallback to in-memory if Memcached is unavailable

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

## Best Practices

### When Applying Rate Limits:
1. Use stricter limits for authentication endpoints
2. Apply higher limits for trusted users/admins
3. Consider the resource cost of each operation
4. Monitor rate limit violations for security insights
5. Use appropriate time windows (minute, hour, day)

### Monitoring:
- All rate limit violations are logged
- Include user ID/IP in logs for investigation
- Monitor patterns of violations for attack detection

### Testing:
- Use `RATELIMIT_ENABLED=false` in test environments
- Test with different user roles
- Verify custom headers are properly set via the after_request handler
- Test custom error pages
- Use the test script in `tests/test_style_guide_rate_limit.py` to verify rate limiting on public routes

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

## Recent Updates

### Flask-Limiter Compatibility Fix (October 2025)

**Issue**: Flask-Limiter (>=3.8.0) had a compatibility issue with Werkzeug (3.1.3) causing `AttributeError: 'bool' object has no attribute 'lower'` when trying to inject rate limit headers.

**Solution**:
1. Disabled built-in header functionality by setting `RATELIMIT_HEADERS_ENABLED = False`
2. Added custom header injection via `@app.after_request` handler in `app.py`
3. Enhanced error handling to provide user-friendly flash messages
4. Applied rate limiting to all non-login required routes:
   - `/favicon.ico` - 100 per minute
   - `/` (homepage) - 100 per minute
   - `/style_guide` - 100 per minute
   - `/healthz` - 200 per minute (higher limit for health checks)
   - `/email-sse` - 20 per minute (SSE endpoint for real-time email status)
   - `/check-email-status` - 20 per minute (endpoint for polling email status)
   - `/check-session` - 20 per minute (endpoint for session validation)
   - `/docs/` - 20 per minute (documentation index)
   - `/docs/api.md` - 20 per minute (API documentation)
   - `/docs/api.html` - 20 per minute (API documentation HTML)
   - `/docs/openapi.yaml` - 20 per minute (OpenAPI specification)
   - `/docs/swagger` - 20 per minute (Swagger UI)
   - `/docs/swagger.json` - 20 per minute (Swagger JSON)
   - `/help/` - 20 per minute (help documentation)
   - `/help/<path:doc_path>` - 20 per minute (help documentation paths)

**Testing**:
- Created test script `tests/test_style_guide_rate_limit.py` to verify rate limiting on public routes
- Confirmed that rate limiting works correctly with 100 requests allowed before hitting the limit
- Verified that flash messages are displayed when rate limits are exceeded