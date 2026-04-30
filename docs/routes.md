# Application Routes Documentation

This document provides a comprehensive overview of all routes in the Fundus Image Manager application, organized by blueprint. It includes route paths, HTTP methods, required roles, functionality, and data scoping information.

## Table of Contents

1. [Core Application Routes](#core-application-routes)
2. [Authentication Routes](#authentication-routes)
3. [Account Management Routes](#account-management-routes)
4. [Task Management Routes](#task-management-routes)
5. [Ad-Hoc Tasks Routes](#ad-hoc-tasks-routes)
6. [Administration Routes](#administration-routes)
7. [Analytics Routes](#analytics-routes)
8. [Image Grading Routes](#image-grading-routes)
9. [File Uploads Routes](#file-uploads-routes)
10. [Direct Uploads Routes](#direct-uploads-routes)
11. [Search Routes](#search-routes)
12. [Media Serving Routes](#media-serving-routes)
13. [Report Serving Routes](#report-serving-routes)
14. [Verification Workflows Routes](#verification-workflows-routes)
15. [Patient Screenings Routes](#patient-screenings-routes)
16. [Job Processing Routes](#job-processing-routes)
17. [Data Audit Routes](#data-audit-routes)
18. [Review Routes](#review-routes)
19. [Dashboard Routes](#dashboard-routes)
20. [Help & Documentation Routes](#help--documentation-routes)
21. [API Routes](#api-routes)
22. [Notifications Routes](#notifications-routes)
23. [Preprocessing Routes](#preprocessing-routes)
24. [Rate Limiting Routes](#rate-limiting-routes)

---

## Core Application Routes

**Base URL:** `/`
**No role restrictions** (accessible without login)

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | homepage | Main homepage |
| `/favicon.ico` | GET | _favicon | Serve favicon |
| `/style_guide` | GET | style_guide | Display style guide |
| `/test-rate-limit` | GET | test_rate_limit | Test endpoint for rate limiting |
| `/healthz` | GET | healthz | Health check endpoint |
| `/static/<path:filename>` | GET | static | Serve static files |
| `/analytics` | GET | public_public_analytics | Public analytics dashboard |
| `/api/analytics/kpi` | GET | public_api_analytics_kpi | Public KPI API endpoint |
| `/api/analytics/chart-data` | GET | public_api_analytics_chart_data | Public chart data API endpoint |

---

## Authentication Routes

**Base URL:** `/auth`
**No role restrictions** (public routes)

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/login` | GET, POST | auth.login | User login page and form submission |
| `/logout` | GET, POST | auth.logout | User logout |
| `/forgot-password` | GET, POST | auth.forgot_password | Forgot password page and request |
| `/reset-password` | GET, POST | auth.reset_password | Reset password with token |
| `/check-email-status` | GET | auth.check_email_status | Check email verification status |
| `/check-session` | GET | auth.check_session | Check session validity |
| `/email-sse` | GET | auth.email_sse | Server-sent events for email status |
| `/ping` | GET | auth.ping | Ping endpoint for connectivity |
| `/captcha-audio` | GET | auth.captcha_audio | Audio captcha endpoint |
| `/refresh-captcha` | GET | auth.refresh_captcha | Refresh captcha endpoint |

---

## Account Management Routes

**Base URL:** `/account`
**Role restrictions:** `login_required` for all routes

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | account.profile | User profile page |
| `/profile` | GET, POST | account.profile | User profile management |
| `/change-password` | GET | account.change_password_self | Change user password |
| `/change-password/submit` | POST | account.change_password_submit | Change user password |

---

## Task Management Routes

**Base URL:** `/tasks`
**Role restrictions:** Multiple roles per route

| Route Path | HTTP Methods | Required Roles | Function | Description |
|------------|--------------|---------------|----------|-------------|
| `/` | GET | admin, data_manager, ophthalmologist, optometrist | tasks.index | Main tasks page |
| `/pending` | GET | admin, data_manager, ophthalmologist, optometrist | tasks.pending | View pending tasks |
| `/viewTaskDetails/<int:task_id>` | GET | admin, data_manager, optometrist | tasks.view_task_details | View task details |
| `/all-tasks` | GET | admin, data_manager | tasks.all_tasks | View all organizational tasks with filtering |
| `/intra-rater` | GET | ophthalmologist, admin, data_manager | tasks.intra_rater_dashboard | Intra-rater task dashboard |
| `/intra-rater/admin` | GET | ophthalmologist, admin, data_manager | tasks.intra_rater_admin | Intra-rater admin management |
| `/intra-rater/batches` | GET | ophthalmologist, admin, data_manager | tasks.list_intra_rater_batches | List intra-rater batches |
| `/intra-rater/batches` | POST | admin, data_manager | tasks.create_intra_rater_batch | Create intra-rater batch |
| `/intra-rater/my-tasks` | GET | ophthalmologist, admin, data_manager | tasks.list_my_intra_rater_tasks | List user's intra-rater tasks |
| `/intra-rater/tasks/<int:task_id>/submit` | POST | ophthalmologist | tasks.submit_intra_rater_grade | Submit intra-rater grade |
| `/intra-rater/kpi-data` | GET | ophthalmologist, admin, data_manager | tasks.get_intra_rater_kpi_data | Get intra-rater KPI data |

---

## Ad-Hoc Tasks Routes

**Base URL:** `/tasks/ad_hoc`
**Role restrictions:** admin, data_manager only

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | ad_hoc_tasks.index | Ad-hoc task creation interface |
| `/list` | GET | ad_hoc_tasks.list_batches | List ad-hoc batches |
| `/detail/<int:ad_hoc_id>` | GET | ad_hoc_tasks.detail | View ad-hoc batch details |
| `/search` | GET | ad_hoc_tasks.search | Search images for ad-hoc tasks |
| `/preview` | POST | ad_hoc_tasks.preview | Preview ad-hoc task candidates |
| `/create` | POST | ad_hoc_tasks.create | Create ad-hoc tasks |

---

## Administration Routes

**Base URL:** `/admin`
**Role restrictions:** admin, data_manager only

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | admin.admin_status | Admin dashboard |
| `/api/admin/status` | GET | admin.api_admin_status | Admin status API endpoint |
| `/api/maintenance_status` | GET | admin.api_maintenance_status | Maintenance status API endpoint |
| `/api/materialized-view/status` | GET | admin.api_materialized_view_status | Materialized view status API |
| `/api/materialized-view/last-refresh` | GET | admin.api_last_refresh | Last materialized view refresh info |
| `/api/materialized-view/schedule` | GET | admin.api_schedule_status | Materialized view schedule status |
| `/api/materialized-view/refresh` | POST | admin.manual_refresh | Manual materialized view refresh |
| `/api/thumbnail/health_check` | GET | admin.api_thumbnail_health_check | Thumbnail health check API |
| `/api/thumbnail_stats` | GET | admin.api_thumbnail_stats | Thumbnail statistics API |
| `/api/thumbnail/cleanup_orphaned` | POST | admin.api_cleanup_orphaned | Cleanup orphaned thumbnails |
| `/api/thumbnail/full_maintenance` | POST | admin.api_full_maintenance | Full thumbnail maintenance |
| `/api/thumbnail/manual_maintenance` | POST | admin.api_manual_maintenance | Manual thumbnail maintenance |
| `/api/thumbnail/regenerate_missing` | POST | admin.api_regenerate_missing | Regenerate missing thumbnails |
| `/api/thumbnail/validate_integrity` | POST | admin.api_validate_integrity | Validate thumbnail integrity |
| `/admin/thumbnail_management` | GET | admin.thumbnail_management | Thumbnail management interface |
| `/api/email-settings/test-current` | GET | admin.api_test_current_email_config | Test current email config |
| `/api/email-settings/send-sample` | POST | admin.send_sample_email | Send sample email |
| `/email-settings` | GET | admin.email_settings_list | Email settings list |
| `/email-settings/new` | GET, POST | admin.create_email_settings | Create new email settings |
| `/email-settings/<int:settings_id>/edit` | GET, POST | admin.edit_email_settings | Edit email settings |
| `/email-settings/<int:settings_id>/test` | GET | admin.test_email_settings | Test email settings |
| `/email-settings/<int:settings_id>/activate` | POST | admin.activate_email_settings | Activate email settings |
| `/email-settings/<int:settings_id>/delete` | POST | admin.delete_email_settings | Delete email settings |
| `/users` | GET | admin.users_list | User management list |
| `/users/new` | GET, POST | admin.add_user | Add new user |
| `/users/<int:user_id>` | GET | admin.user_detail | Canonical user hub with profile, access, grading, upload, sessions, and activity |
| `/users/<int:user_id>/edit` | GET, POST | admin.edit_user | Edit user |
| `/users/<int:user_id>/update` | POST | admin.users_update | Update user |
| `/users/<int:user_id>/mobile-sessions/<string:session_id>/revoke` | POST | admin.revoke_mobile_session | Revoke one mobile session for a user |
| `/roles` | GET, POST | admin.manage_roles | Role management |
| `/role-usage` | GET | admin.role_usage | Role usage statistics |
| `/routes-by-role/<string:role_name>` | GET | admin.routes_by_role | View routes by role |
| `/ai-models` | GET, POST | admin.list_and_create_ai_model | List/create AI models |
| `/ai-models/<int:item_id>/edit` | GET, POST | admin.edit_ai_model | Edit AI model |
| `/ai-models/<int:item_id>/delete` | POST | admin.delete_ai_model | Delete AI model |
| `/grading-eligibility` | GET | admin.manage_eligibility_users | Grading eligibility management |
| `/grading-eligibility/<int:user_id>` | GET, POST | admin.edit_eligibility | Edit user grading eligibility |
| `/disease-gradings` | GET, POST | admin.list_disease_gradings | List/create disease gradings |
| `/disease-gradings/<int:grading_id>/features` | GET | admin.get_grading_features | Get grading features |
| `/disease-gradings/<int:grading_id>/delete` | POST | admin.delete_disease_grading | Delete disease grading |
| `/hospital` | GET, POST | admin.list_hospitals | List/create hospitals |
| `/hospital/<int:item_id>/edit` | GET, POST | admin.edit_hospital | Edit hospital |
| `/hospital/<int:item_id>/delete` | POST | admin.delete_hospital | Delete hospital |
| `/lab_unit` | GET, POST | admin.list_lab_units | List/create lab units |
| `/lab_unit/<int:item_id>/edit` | GET, POST | admin.edit_lab_unit | Edit lab unit |
| `/lab_unit/<int:item_id>/delete` | POST | admin.delete_lab_unit | Delete lab unit |
| `/camera` | GET, POST | admin.list_cameras | List/create cameras |
| `/camera/<int:item_id>/edit` | GET, POST | admin.edit_camera | Edit camera |
| `/camera/<int:item_id>/delete` | POST | admin.delete_camera | Delete camera |
| `/disease` | GET, POST | admin.list_diseases | List/create diseases |
| `/disease/<int:item_id>/edit` | GET, POST | admin.edit_disease | Edit disease |
| `/disease/<int:item_id>/delete` | POST | admin.delete_disease | Delete disease |
| `/area` | GET, POST | admin.list_areas | List/create areas |
| `/area/<int:item_id>/edit` | GET, POST | admin.edit_area | Edit area |
| `/area/<int:item_id>/delete` | POST | admin.delete_area | Delete area |
| `/change-password` | GET, POST | admin.change_password | Change admin password |
| `/logs` | GET | admin.log_viewer | System log viewer |
| `/disk-usage` | GET | admin.disk_usage | Disk usage statistics |
| `/disk-usage/delete-duplicates` | POST | admin.delete_duplicates | Delete duplicate files |
| `/disk-usage/delete-old-zips` | POST | admin.delete_old_processed_zips | Delete old processed ZIPs |
| `/database-dump` | GET, POST | admin.database_dump | Database dump functionality |
| `/database-excel-export` | GET, POST | admin.database_excel_export | Database export to Excel |
| `/database-info` | GET | admin.get_database_info | Get database information |
| `/database-tables` | GET | admin.get_database_tables | Get database tables |
| `/materialized-view` | GET | admin.materialized_view_status | Materialized view status and management |
| `/malicious-uploads` | GET | admin.malicious_uploads | Malicious uploads management |
| `/rate-limits` | GET | rate_limit_admin.index | Rate limit management interface |
| `/rate-limits/status` | GET | rate_limit_admin.status | Rate limit status |
| `/rate-limits/my-key` | GET | rate_limit_admin.get_my_key | Get user rate limit key |
| `/rate-limits/clear` | POST | rate_limit_admin.clear_limit | Clear rate limit |
| `/rate-limits/clear-limit-ajax` | POST | rate_limit_admin.clear_limit_ajax | Clear rate limit via AJAX |
| `/rate-limits/clear-all` | POST | rate_limit_admin.clear_all | Clear all rate limits |

---

## Analytics Routes

**Base URL:** `/analytics`
**Role restrictions:** admin, data_manager only

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/direct-files` | GET | analytics.direct_files | Direct files analytics |
| `/encounter-files` | GET | analytics.encounter_files | Encounter files analytics |
| `/encounters` | GET | analytics.encounter_results | Encounter results analytics |
| `/encounters-simple` | GET | analytics.encounter_results_simple | Simplified encounter results |
| `/images` | GET | analytics.image_results | Image results analytics |
| `/images/no-tasks` | GET | analytics.images_without_tasks | Images without tasks |
| `/direct/view/<uuid_str>` | GET | analytics.view_upload | View direct upload details |
| `/encounter/view/<int:encounter_id>` | GET | analytics.view_encounter | View encounter file details |

---

## Image Grading Routes

**Base URL:** `/grading`
**Role restrictions:** Varies by route (typically ophthalmologist, optometrist)

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | grading.index | Grading interface |
| `/task/<string:task_uuid>/<string:slot_type>` | GET | grading.dual_grading_task | Grade specific task with UUID and slot type |
| `/task/submit` | POST | grading.dual_grading_submit | Submit dual grading |
| `/intra-task/<string:task_uuid>` | GET | grading.intra_rater_task | Intra-rater grading task |
| `/intra-task/submit` | POST | grading.intra_rater_submit | Submit intra-rater grading |
| `/grade/<int:disease_id>/<string:role_slot>` | GET | grading.start_grading | Start grading for disease and role |
| `/revise/<int:grade_id>` | GET | grading.revise_grading | Revise existing grading |

---

## File Uploads Routes

### Uploaded ZIPs
**Base URL:** `/uploaded_zips`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | uploaded_zips.list_uploaded_zips | List uploaded ZIP files |

### Remedio ZIP Uploads
**Base URL:** `/remedio_zip_uploads`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/upload_files` | GET | remedio_zip_uploads.upload_form | Remedio ZIP upload form |
| `/upload` | POST | remedio_zip_uploads.upload_files | Process Remedio ZIP upload |

---

## Direct Uploads Routes

**Base URL:** `/direct` and `/upload`
**Role restrictions:** Multiple roles per route

| Route Path | HTTP Methods | Required Roles | Function | Description |
|------------|--------------|---------------|----------|-------------|
| `/` | GET | fileUploader, optometrist, data_manager, admin | direct_uploads.upload_index | Upload index page |
| `/upload` | GET, POST | fileUploader, optometrist, data_manager, admin | direct_uploads.upload | Upload page and processing |
| `/direct/upload` | GET, POST | fileUploader, optometrist, data_manager, admin | direct_uploads.upload | Upload page and processing |
| `/direct/upload/edit_image/<int:upload_id>` | GET | fileUploader, optometrist, data_manager, admin | direct_uploads.edit_image | Edit uploaded image |
| `/direct/upload/edit/<int:upload_id>` | GET, POST | fileUploader, optometrist, data_manager, admin | direct_uploads.edit_upload | Edit upload metadata |
| `/direct/upload/restore_original/<int:upload_id>` | POST | fileUploader, optometrist, data_manager, admin | direct_uploads.restore_original | Restore original image |
| `/direct/upload/save_image/<int:upload_id>` | POST | fileUploader, optometrist, data_manager, admin | direct_uploads.save_edited_image | Save edited image |
| `/direct/dashboard` | GET, POST | fileUploader, optometrist, data_manager, admin | direct_uploads.dashboard | Direct uploads dashboard |
| `/direct/pregraded` | GET, POST | fileUploader, optometrist, data_manager, admin | direct_uploads.pregraded_upload | Pregraded upload interface |
| `/direct/pregraded/grades` | GET, POST | fileUploader, optometrist, data_manager, admin | direct_uploads.pregraded_grades | Pregraded grades management |
| `/direct/pregraded/grades/recent` | GET | fileUploader, optometrist, data_manager, admin | direct_uploads.recent_pregraded_grades | Recent pregraded grades |
| `/api/direct/upload/status/<job_token>` | GET | fileUploader, optometrist, data_manager, admin | direct_uploads.api_upload_status | Get upload status |
| `/api/hospital/<int:lab_unit_id>` | GET | fileUploader, optometrist, data_manager, admin | direct_uploads.get_hospital | Get hospital by lab unit |
| `/api/lab-units/<int:user_id>` | GET | fileUploader, optometrist, data_manager, admin | direct_uploads.get_lab_units | Get lab units for user |

---

## Search Routes

**Base URL:** `/search`
**Role restrictions:** admin, data_manager only

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | search.search_route | Search interface |
| `/images` | GET | search.search_images_route | Search images with filters |
| `/images/` | GET | search.search_images_route | Search images with filters (alternate) |

---

## Media Serving Routes

**Base URL:** `/media`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/img/<uuid_str>` | GET | media._imgForGradingByUUID | Serve image for grading |
| `/img/<uuid_str>/thumbnail` | GET | media._universalImageThumbnailByUUID | Serve universal image thumbnail |
| `/direct_upload/org_img/<uuid_str>` | GET | media._directImgOrigByUUID | Serve original direct upload image |
| `/direct_upload/org_img/<uuid_str>/thumbnail` | GET | media._directImgOrigThumbnailByUUID | Serve original direct upload thumbnail |
| `/direct_upload/ed_img/<uuid_str>` | GET | media._directImgEdByUUID | Serve edited direct upload image |
| `/direct_upload/ed_img/<uuid_str>/thumbnail` | GET | media._directImgEdThumbnailByUUID | Serve edited direct upload thumbnail |
| `/direct_upload/fn_img/<uuid_str>` | GET | media._directImgFinalByUUID | Serve final direct upload image |
| `/direct_upload/fn_img/<uuid_str>/thumbnail` | GET | media._directImgFinalThumbnailByUUID | Serve final direct upload thumbnail |
| `/encounter/img/<uuid_str>` | GET | media._encounterImageByUUID | Serve encounter image |
| `/encounter/img/<uuid_str>/thumbnail` | GET | media._encounterImageThumbnailByUUID | Serve encounter image thumbnail |
| `/encounter/pdf/<uuid_str>` | GET | media._encounterPDFByUUID | Serve encounter PDF |

---

## Report Serving Routes

**Base URL:** `/reports`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/glaucoma_results` | GET | reports.glaucoma_results_redirect | Redirect to glaucoma results |
| `/dr/by-uuid/<uuid>` | GET | reports.serve_dr_pdf_by_uuid | Serve DR PDF by UUID |
| `/glaucoma/by-uuid/<uuid>` | GET | reports.serve_glaucoma_pdf_by_uuid | Serve glaucoma PDF by UUID |

---

## Verification Workflows Routes

### Diabetic Retinopathy Verification
**Base URL:** `/verify_remedio_dr`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/list` | GET | verify_remedio_dr.verify_dr_list | List DR reports for verification |
| `/detail/<int:report_id>` | GET | verify_remedio_dr.verify_dr_detail | View DR report details |
| `/edit/<int:report_id>` | GET, POST | verify_remedio_dr.verify_dr_edit | Edit DR report |
| `/edit/<int:report_id>/verify` | POST | verify_remedio_dr.verify_dr_verify | Verify DR report |
| `/edit/<int:report_id>/unverify` | POST | verify_remedio_dr.verify_dr_unverify | Unverify DR report |
| `/edit/<int:report_id>/mark_eye` | POST | verify_remedio_dr.verify_dr_mark_eye | Mark eye in DR report |

### Glaucoma Verification
**Base URL:** `/verify_remedio_glaucoma`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/list` | GET | verify_remedio_glaucoma.glaucoma_list | List glaucoma reports for verification |
| `/results` | GET | verify_remedio_glaucoma.glaucoma_results | Glaucoma verification results |
| `/detail/<int:clean_id>` | GET | verify_remedio_glaucoma.glaucoma_detail | View glaucoma report details |
| `/edit/<int:clean_id>` | GET, POST | verify_remedio_glaucoma.glaucoma_edit | Edit glaucoma report |
| `/edit/<int:clean_id>/verify` | POST | verify_remedio_glaucoma.glaucoma_verify | Verify glaucoma report |
| `/edit/<int:clean_id>/unverify` | POST | verify_remedio_glaucoma.glaucoma_unverify | Unverify glaucoma report |
| `/edit/<int:clean_id>/mark_eye` | POST | verify_remedio_glaucoma.glaucoma_mark_eye | Mark eye in glaucoma report |
| `/clean` | GET, POST | verify_remedio_glaucoma.glaucoma_clean_workflow | Glaucoma clean workflow |

### No DR Verification
**Base URL:** `/verify_remedio_nodr`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/list` | GET | verify_remedio_nodr.nodr_list | List No-DR reports for verification |
| `/edit/<int:encounter_id>` | GET, POST | verify_remedio_nodr.nodr_edit | Edit No-DR report |
| `/edit/<int:encounter_id>/verify` | POST | verify_remedio_nodr.nodr_verify | Verify No-DR report |
| `/edit/<int:encounter_id>/unverify` | POST | verify_remedio_nodr.nodr_unverify | Unverify No-DR report |
| `/edit/<int:encounter_id>/mark_eye` | POST | verify_remedio_nodr.nodr_mark_eye | Mark eye in No-DR report |

---

## Patient Screenings Routes

**Base URL:** `/screenings`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | screenings.list_screenings | List screening encounters |
| `/<int:encounter_id>` | GET | screenings.screening_detail | View screening details |
| `/delete/<int:encounter_id>` | POST | screenings.delete_encounter | Delete screening encounter |
| `/delete_reports/<int:encounter_id>` | POST | screenings.delete_reports | Delete screening reports |
| `/reprocess_pdf/<int:encounter_id>` | POST | screenings.reprocess_pdf | Reprocess screening PDF |

---

## Job Processing Routes

**Base URL:** `/jobs`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | jobs.list_recent_jobs | List recent jobs |
| `/<job_token>` | GET | jobs.job_status_json | Get job status as JSON |
| `/<job_token>/view` | GET | jobs.job_status_page | View job status page |
| `/processing/<job_id>` | GET | jobs.upload_processing | View upload processing status |
| `/results/details/<job_token>` | GET | jobs.upload_results | View upload results details |

---

## Data Audit Routes

**Base URL:** `/audit`
**Role restrictions:** admin, data_manager only

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/missing_capture_date` | GET | audit.missing_capture_date | View records with missing capture dates |

---

## Review Routes

**Base URL:** `/review`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/discrepancy-review` | GET | review.discrepancy_review | Review grading discrepancies |
| `/reviewTaskDetails/<int:task_id>` | GET, POST | review.review_task_details | Review task details |

---

## Dashboard Routes

**Base URL:** `/dashboard`
**Role restrictions:** Multiple roles per route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | dashboard.hospital_dashboard | Main dashboard |
| `/hospital/<int:hospital_id>` | GET | dashboard.hospital_detail | Hospital details |
| `/images` | GET | dashboard.image_list | Image list with pagination |

---

## Help & Documentation Routes

### Help Documentation
**Base URL:** `/help`
**No role restrictions** (public routes)

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | help.index | Help documentation |
| `/<path:doc_path>` | GET | help.view_document | View specific help document |

### Docs System
**Base URL:** `/docs`
**No role restrictions** (public routes)

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | docs.docs_index | Documentation index |
| `/api.md` | GET | docs.api_docs | API documentation (Markdown) |
| `/api.html` | GET | docs.api_docs_html | API documentation (HTML) |
| `/openapi.yaml` | GET | docs.openapi_spec | OpenAPI specification |
| `/swagger.json` | GET | docs.swagger_json | Swagger JSON specification |
| `/swagger` | GET | docs.swagger_ui | Swagger UI |

---

## API Routes

**Base URL:** `/api`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/ai-models` | GET | fundus_api.get_ai_models | Get AI models |
| `/diseases-with-gradings` | GET | fundus_api.get_diseases_with_gradings | Get diseases with gradings |
| `/diseases-gradings-features/<int:disease_id>` | GET | fundus_api.get_disease_gradings_features | Get disease grading features |
| `/disease-grades/<int:disease_id>` | GET | fundus_api.get_disease_grades | Get disease grades |
| `/hospitals` | GET | fundus_api.get_hospitals_list | Get hospitals list |
| `/hospitals/<int:hospital_id>` | GET | fundus_api.get_hospital_by_id | Get hospital by ID |
| `/hospitals/<int:hospital_id>/labunits` | GET | fundus_api.get_lab_units_by_hospital | Get lab units by hospital |
| `/lab-units/<int:lab_unit_id>` | GET | fundus_api.get_lab_unit_by_id | Get lab unit by ID |
| `/lab-units/<int:lab_unit_id>/hospital` | GET | fundus_api.get_hospital | Get hospital by lab unit |
| `/labunits` | GET | fundus_api.get_all_lab_units_list | Get all lab units |
| `/users/<int:user_id>/lab-units` | GET | fundus_api.get_lab_units | Get lab units for user |
| `/eligibleLabUnit` | GET | fundus_api.get_eligible_lab_units | Get eligible lab units |
| `/eligibleLabUnitCurrentUser` | GET | fundus_api.get_eligible_lab_units_currentUser | Get eligible lab units for current user |
| `/grading-eligibility/users/<int:user_id>` | GET | fundus_api.get_user_grading_eligibility | Get user grading eligibility |
| `/grading-eligibility/users/<int:user_id>/details` | GET | fundus_api.get_user_grading_eligibility_details | Get user grading eligibility details |
| `/viewer/settings` | GET, POST | fundus_api.save_viewer_settings | Get/save viewer settings |
| `/viewer/presets` | GET | fundus_api.get_viewer_presets | Get viewer presets |
| `/viewer/presets/<int:slot_number>` | POST, DELETE | fundus_api.save_viewer_preset | Save/delete viewer preset |
| `/upload-jobs/<job_token>/status` | GET | fundus_api.get_upload_status | Get upload job status |
| `/kpis/encounter-files/dr-reports-count` | GET | fundus_api.dr_reports_count | Get DR reports count |
| `/kpis/encounter-files/dr-results-distribution` | GET | fundus_api.dr_results_distribution | Get DR results distribution |
| `/kpis/encounter-files/glaucoma-reports-count` | GET | fundus_api.glaucoma_reports_count | Get glaucoma reports count |
| `/kpis/encounter-files/glaucoma-results-distribution` | GET | fundus_api.glaucoma_results_distribution | Get glaucoma results distribution |
| `/kpis/encounter-files/images-count` | GET | fundus_api.images_count | Get images count |
| `/kpis/encounter-files/vcdr-distribution` | GET | fundus_api.vcdr_distribution | Get VCDR distribution |
| `/kpis/encounter-files/year-month-wise-uploads` | GET | fundus_api.year_month_wise_uploads | Get year-month wise uploads |
| `/kpis/encounter-files/filtered-dataframe` | GET | fundus_api.get_filtered_dataframe | Get filtered encounter dataframe |
| `/kpis/encounter-files/filtered-dataframe-excel` | GET | fundus_api.get_filtered_dataframe_excel | Get filtered encounter dataframe as Excel |
| `/kpis/direct-files/upload-metrics` | GET | fundus_api.get_upload_metrics | Get direct upload metrics |
| `/kpis/direct-files/filtered-dataframe` | GET | fundus_api.get_filtered_direct_dataframe | Get filtered direct dataframe |
| `/kpis/direct-files/filtered-dataframe-excel` | GET | fundus_api.get_filtered_direct_dataframe_excel | Get filtered direct dataframe as Excel |

---

## Notifications Routes

**Base URL:** `/notifications`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | notifications.notifications | Notification center |
| `/broadcast` | GET, POST | notifications.broadcast_notification | Broadcast notification |
| `/compose` | GET, POST | notifications.compose_notification | Compose notification |
| `/mark_all_read` | POST | notifications.mark_all_notifications_read | Mark all notifications as read |
| `/system` | GET, POST | notifications.system_notification | System notification |
| `/<int:notification_id>/mark_read` | POST | notifications.mark_notification_read | Mark notification as read |

---

## Preprocessing Routes

**Base URL:** `/preprocess`
**Role restrictions:** admin only

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/dashboard` | GET | preprocess.anonymization_dashboard | Anonymization dashboard |
| `/anonymize_image/<uuid:uuid>` | GET, POST | preprocess.anonymize_image | Anonymize specific image |
| `/anonymize_image/<uuid:uuid>/restore_original` | POST | preprocess.restore_original_anonymized_image | Restore original anonymized image |
| `/static/<path:filename>` | GET | preprocess.static | Serve static files |

---

## Rate Limiting Routes

**Base URL:** `/admin/rate-limits`
**Role restrictions:** admin, data_manager only

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | rate_limit_admin.index | Rate limit management interface |
| `/status` | GET | rate_limit_admin.status | Rate limit status |
| `/my-key` | GET | rate_limit_admin.get_my_key | Get user rate limit key |
| `/clear` | POST | rate_limit_admin.clear_limit | Clear rate limit |
| `/clear-limit-ajax` | POST | rate_limit_admin.clear_limit_ajax | Clear rate limit via AJAX |
| `/clear-all` | POST | rate_limit_admin.clear_all | Clear all rate limits |

---

## Route Access Control Notes

### Role Hierarchy
- **admin**: Full system access
- **data_manager**: Administrative data access and reporting
- **ophthalmologist**: Medical grading and review capabilities
- **optometrist**: Basic grading and data entry
- **fileUploader**: File upload and management
- **viewer**: Read-only access to assigned data

### Scoping Mechanisms
- **Lab Unit Scoping**: Users can be restricted to specific lab units within hospitals
- **Task-Based Access**: Grading access is controlled through task assignments
- **Role-Based UI**: Interface elements are shown/hidden based on user roles
- **Data Filtering**: Users only see data within their assigned scope

### Security Features
- **Global Authentication Guard**: All routes require authentication except explicitly public routes
- **CSRF Protection**: All state-changing requests require CSRF tokens
- **Rate Limiting**: Configurable rate limits per endpoint
- **Session Management**: Database-backed sessions with inactivity timeout
- **Audit Logging**: Comprehensive audit trail for all user actions
