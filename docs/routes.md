# Application Routes Documentation

This document provides a comprehensive overview of all routes in the Fundus Image Manager application, organized by blueprint. It includes route paths, HTTP methods, required roles, functionality, and data scoping information.

## Table of Contents

1. [Core Application Routes](#core-application-routes)
2. [Authentication Routes](#authentication-routes)
3. [Account Management Routes](#account-management-routes)
4. [Administration Routes](#administration-routes)
5. [File Uploads Routes](#file-uploads-routes)
6. [Direct Uploads Routes](#direct-uploads-routes)
7. [Analytics Routes](#analytics-routes)
8. [Tasks Routes](#tasks-routes)
9. [Search Routes](#search-routes)
10. [Image Grading Routes](#image-grading-routes)
11. [Media Serving Routes](#media-serving-routes)
12. [Report Serving Routes](#report-serving-routes)
13. [DR Verification Routes](#dr-verification-routes)
14. [Glaucoma Verification Routes](#glaucoma-verification-routes)
15. [Patient Screenings Routes](#patient-screenings-routes)
16. [Job Processing Routes](#job-processing-routes)
17. [Data Audit Routes](#data-audit-routes)
18. [Image Preprocessing Routes](#image-preprocessing-routes)

---

## Core Application Routes

| Route Path | URL For | HTTP Methods | Route File | Roles Required |
|------------|---------|--------------|------------|----------------|
| / | homepage | GET | app.py | - |
| /style_guide | style_guide | GET | app.py | - |
| /healthz | healthz | GET | app.py | - |
| /favicon.ico | _favicon | GET | app.py | - |

---

## Authentication Routes

| Route Path | URL For | HTTP Methods | Route File | Roles Required |
|------------|---------|--------------|------------|----------------|
| /login | auth.login | GET, POST | auth/routes.py | - |
| /logout | auth.logout | POST, GET | auth/routes.py | login_required |
| /ping | auth.ping | GET | auth/routes.py | login_required |

---

## Account Management Routes

| Route Path | URL For | HTTP Methods | Route File | Roles Required |
|------------|---------|--------------|------------|----------------|
| /account/profile | account.profile | GET, POST | account/routes.py | login_required |
| /account/change-password | account.change_password_self | GET, POST | account/routes.py | login_required |

---

## Administration Routes

| Route Path | URL For | HTTP Methods | Route File | Roles Required |
|------------|---------|--------------|------------|----------------|
| /admin/users | admin.users_list | GET | admin/users.py | admin |
| /admin/users/new | admin.add_user | GET, POST | admin/users.py | admin |
| /admin/users/\<int:user_id\>/edit | admin.edit_user | GET, POST | admin/users.py | admin |
| /admin/users/\<int:user_id\>/update | admin.users_update | POST | admin/users.py | admin |
| /admin/change-password | admin.change_password | GET, POST | admin/security.py | admin |
| /admin/roles | admin.manage_roles | GET, POST | admin/security.py | admin |
| /admin/\<string:model_name\> | admin.list_and_create_lookup | GET, POST | admin/lookups.py | admin |
| /admin/\<string:model_name\>/\<int:item_id\>/edit | admin.edit_lookup | GET, POST | admin/lookups.py | admin |
| /admin/\<string:model_name\>/\<int:item_id\>/delete | admin.delete_lookup | POST | admin/lookups.py | admin |
| /admin/disease-gradings | admin.list_disease_gradings | GET, POST | admin/disease_gradings.py | admin |
| /admin/disease-gradings/\<int:grading_id\>/json | admin.get_disease_grading_json | GET | admin/disease_gradings.py | admin |
| /admin/disease-gradings/\<int:grading_id\>/delete | admin.delete_disease_grading | POST | admin/disease_gradings.py | admin |
| /admin/malicious-uploads | admin.malicious_uploads | GET | admin/uploads.py | admin |

---

## File Uploads Routes

| Route Path | URL For | HTTP Methods | Route File | Roles Required |
|------------|---------|--------------|------------|----------------|
| /upload_files | uploads.upload_form | GET | uploads/routes.py | admin, fileUploader |
| /upload | uploads.upload_files | POST | uploads/routes.py | admin, fileUploader |
| /uploaded_zips | uploaded_zips.list_uploaded_zips | GET | uploaded_zips/routes.py | admin, fileUploader |

---

## Direct Uploads Routes

| Route Path | URL For | HTTP Methods | Route File | Roles Required |
|------------|---------|--------------|------------|----------------|
| /direct/upload | direct_uploads.upload | GET, POST | direct_uploads/upload.py | fileUploader, optometrist, data_manager, admin |
| /direct/upload/processing/\<int:job_id\> | direct_uploads.upload_processing | GET | direct_uploads/upload.py | fileUploader, optometrist, data_manager, admin |
| /direct/dashboard | direct_uploads.dashboard | GET, POST | direct_uploads/dashboard.py | fileUploader, optometrist, data_manager, admin |
| /direct/upload/edit_image/\<int:upload_id\> | direct_uploads.edit_image | GET | direct_uploads/routes.py | fileUploader, optometrist, data_manager, admin |
| /direct/upload/edit/\<int:upload_id\> | direct_uploads.edit_upload | GET, POST | direct_uploads/routes.py | fileUploader, optometrist, data_manager, admin |
| /direct/upload/restore_original/\<int:upload_id\> | direct_uploads.restore_original | POST | direct_uploads/routes.py | fileUploader, optometrist, data_manager, admin |
| /direct/upload/save_image/\<int:upload_id\> | direct_uploads.save_edited_image | POST | direct_uploads/routes.py | fileUploader, optometrist, data_manager, admin |
| /api/direct/upload/status/\<int:job_id\> | direct_uploads.api_upload_status | GET | direct_uploads/routes.py | fileUploader, optometrist, data_manager, admin |
| /api/hospital/\<int:lab_unit_id\> | direct_uploads.get_hospital | GET | direct_uploads/routes.py | fileUploader, optometrist, data_manager, admin |
| /api/lab-units/\<int:user_id\> | direct_uploads.get_lab_units | GET | direct_uploads/routes.py | fileUploader, optometrist, data_manager, admin |

---

## Analytics Routes

### Access Control and Data Scoping

Access to analytics routes is controlled based on user roles and lab unit associations:
- **Admins** have unrestricted access to all data
- **Data managers** have access to analytics routes scoped to their associated lab units
- **Ophthalmologists, Residents, and other roles** have access to routes based on their lab unit associations
- **Optometrists** have access to specific routes, also scoped to their associated lab units
- All access is restricted based on lab unit associations, meaning users can only view data related to the lab units they are associated with
- Filtering options are restricted so users can only filter by lab units they have access to
- UI dropdowns only show lab units and hospitals that the user has permission to access

### Route Summary

| Route Path | URL For | HTTP Methods | Roles Required | Purpose |
|------------|---------|--------------|----------------|---------|
| /analytics/images | analytics.image_results | GET | admin, data_manager | Render per-image grading results with filtering and pagination |
| /analytics/encounters | analytics.encounter_results | GET | admin, data_manager | Render encounter-level grading summaries |
| /analytics/images/no-tasks | analytics.images_without_tasks | GET | admin, data_manager, optometrist | Display images that have no associated grading tasks |
| /analytics/images/search | analytics.search_images | GET | admin, data_manager, optometrist | Search for images with comprehensive filters |
| /analytics/direct/view/\<uuid_str\> | analytics.direct_view | GET | admin, data_manager, optometrist | View details for a direct image upload |
| /analytics/encounter/view/\<int:encounter_id\> | analytics.encounter_view | GET | admin, data_manager | View details for a specific encounter |
| /analytics/encounters-simple | analytics.encounter_results_simple | GET | admin, data_manager | Render a simplified encounter list showing only encounters with non-pending tasks |
| /analytics/discrepancy-review | analytics.discrepancy_review | GET | admin, data_manager, optometrist | Main page for discrepancy review process |
| /analytics/viewTaskDetails/\<int:task_id\> | analytics.task_details | GET | admin, data_manager, optometrist | View details for a specific grading task |

---

## Tasks Routes

### Access Control and Data Scoping

Access to tasks routes is controlled based on user roles and lab unit associations:
- **Admins** have unrestricted access to all tasks
- **Data managers** have access to tasks scoped to their associated lab units
- **Ophthalmologists** have access to tasks based on their associated lab units
- **Optometrists** have access to tasks assigned to their associated lab units
- All access is restricted based on lab unit associations, meaning users can only view tasks related to the lab units they are associated with

### Route Summary

| Route Path | URL For | HTTP Methods | Roles Required | Purpose |
|------------|---------|--------------|----------------|---------|
| /tasks/ | tasks.index | GET | admin, data_manager, ophthalmologist, optometrist | Main tasks page |
| /tasks/my-tasks | tasks.my_tasks | GET | admin, data_manager, ophthalmologist, optometrist | View and manage user's assigned tasks |
| /tasks/pending | tasks.pending_tasks | GET | admin, data_manager, ophthalmologist, optometrist | View pending tasks in user's lab units |

---

## Search Routes

### Search Images Route

- **Route Path**: `/search/images/`
- **HTTP Methods**: GET
- **Route File**: `search/route_search_images.py`
- **Roles Required**: admin, data_manager, optometrist
- **Purpose**: Provides comprehensive search functionality for images with various filters including hospital, lab unit, camera, disease, area, and date ranges.

#### Filter Parameters

**Global Filters (Apply to both image types when no specific filters are present)**
- `source` - Filter by image source (`all`, `zip`, `direct`)
- `hospital_id` - Filter by hospital ID
- `lab_unit_id` - Filter by lab unit ID
- `upload_start` - Filter for images uploaded after this date
- `upload_end` - Filter for images uploaded before this date
- `search_query` - Text search against UUIDs and filenames

**Direct Upload Specific Filters**
- `camera_id` - Filter by camera ID
- `disease_id` - Filter by disease ID
- `area_id` - Filter by area ID
- `is_mydriatic` - Filter by mydriatic status (`true`, `false`)

**ZIP Upload Specific Filters**
- `has_dr_report` - Filter for presence/absence of DR reports (`true`, `false`)
- `has_glaucoma_report` - Filter for presence/absence of Glaucoma reports (`true`, `false`)
- `capture_start` - Filter for images captured after this date
- `capture_end` - Filter for images captured before this date

---

## Image Grading Routes

| Route Path | URL For | HTTP Methods | Route File | Roles Required |
|------------|---------|--------------|------------|----------------|
| /grading/ | grading.index | GET, POST | grading/dashboard.py | - |
| /grading/remedio/glaucoma/image/\<uuid\> | grading.remedio_glaucoma_image | GET | grading/remedio_glaucoma.py | optometrist, ophthalmologist, admin |
| /grading/remedio/glaucoma/grade | grading.remedio_glaucoma_grade | POST | grading/remedio_glaucoma.py | optometrist, ophthalmologist, admin |
| /grading/remedio/glaucoma/remove | grading.remedio_glaucoma_remove | POST | grading/remedio_glaucoma.py | optometrist, ophthalmologist, admin |
| /grading/remedio/dr/image/\<uuid\> | grading.remedio_dr_image | GET | grading/remedio_dr.py | optometrist, ophthalmologist, admin |
| /grading/remedio/dr/grade | grading.remedio_dr_grade | POST | grading/remedio_dr.py | optometrist, ophthalmologist, admin |
| /grading/remedio/dr/remove | grading.remedio_dr_remove | POST | grading/remedio_dr.py | optometrist, ophthalmologist, admin |
| /grading/task/\<int:task_id\> | grading.dual_grading_task | GET | grading/dual_grading.py | admin, ophthalmologist, resident |
| /grading/task/submit | grading.dual_grading_submit | POST | grading/dual_grading.py | admin, ophthalmologist, resident |

---

## Media Serving Routes

| Route Path | URL For | HTTP Methods | Route File | Roles Required |
|------------|---------|--------------|------------|----------------|
| /media/img/\<path:filename\> | media.serve_image | GET | media/routes.py | admin |
| /media/file/\<uuid\> | media.serve_file_by_uuid | GET | media/routes.py | admin |
| /media/direct_upload/img_orig/\<int:upload_id\> | media.serve_img_orig | GET | media/routes.py | fileUploader, optometrist, data_manager, admin |
| /media/direct_upload/img_edited/\<int:upload_id\> | media.serve_img_edited | GET | media/routes.py | fileUploader, optometrist, data_manager, admin |
| /media/direct_upload/img/\<uuid_str\> | media.serve_img_by_uuid_preferring_edited | GET | media/routes.py | fileUploader, optometrist, data_manager, admin |

---

## Report Serving Routes

| Route Path | URL For | HTTP Methods | Route File | Roles Required |
|------------|---------|--------------|------------|----------------|
| /reports/dr/\<path:filename\> | reports.serve_dr_pdf | GET | reports/routes.py | admin |
| /reports/glaucoma/\<path:filename\> | reports.serve_glaucoma_pdf | GET | reports/routes.py | admin |
| /reports/dr/by-uuid/\<uuid\> | reports.serve_dr_pdf_by_uuid | GET | reports/routes.py | admin |
| /reports/glaucoma/by-uuid/\<uuid\> | reports.serve_glaucoma_pdf_by_uuid | GET | reports/routes.py | admin |
| /reports/glaucoma_results | reports.glaucoma_results_redirect | GET | reports/routes.py | admin |

---

## DR Verification Routes

| Route Path | URL For | HTTP Methods | Route File | Roles Required |
|------------|---------|--------------|------------|----------------|
| /verify_remedio_dr/list | verify_remedio_dr.verify_dr_list | GET | verify_remedio_dr/routes.py | admin, optometrist, data_manager |
| /verify_remedio_dr/detail/\<int:report_id\> | verify_remedio_dr.verify_dr_detail | GET | verify_remedio_dr/routes.py | admin, optometrist, data_manager |
| /verify_remedio_dr/edit/\<int:report_id\> | verify_remedio_dr.verify_dr_edit | GET, POST | verify_remedio_dr/routes.py | admin, optometrist, data_manager |
| /verify_remedio_dr/edit/\<int:report_id\>/verify | verify_remedio_dr.verify_dr_verify | POST | verify_remedio_dr/routes.py | admin, optometrist |
| /verify_remedio_dr/edit/\<int:report_id\>/unverify | verify_remedio_dr.verify_dr_unverify | POST | verify_remedio_dr/routes.py | admin, optometrist |
| /verify_remedio_dr/edit/\<int:report_id\>/mark_eye | verify_remedio_dr.verify_dr_mark_eye | POST | verify_remedio_dr/routes.py | admin, optometrist, data_manager |

---

## Glaucoma Verification Routes

| Route Path | URL For | HTTP Methods | Route File | Roles Required |
|------------|---------|--------------|------------|----------------|
| /verify_remedio_glaucoma/results | verify_remedio_glaucoma.glaucoma_results | GET | verify_remedio_glaucoma/routes.py | admin |
| /verify_remedio_glaucoma/list | verify_remedio_glaucoma.glaucoma_list | GET | verify_remedio_glaucoma/routes.py | admin |
| /verify_remedio_glaucoma/clean | verify_remedio_glaucoma.glaucoma_clean_workflow | GET, POST | verify_remedio_glaucoma/routes.py | admin |
| /verify_remedio_glaucoma/detail/\<int:clean_id\> | verify_remedio_glaucoma.glaucoma_detail | GET | verify_remedio_glaucoma/routes.py | admin |
| /verify_remedio_glaucoma/edit/\<int:clean_id\> | verify_remedio_glaucoma.glaucoma_edit | GET, POST | verify_remedio_glaucoma/routes.py | admin, optometrist, data_manager |
| /verify_remedio_glaucoma/edit/\<int:clean_id\>/verify | verify_remedio_glaucoma.glaucoma_verify | POST | verify_remedio_glaucoma/routes.py | admin, optometrist |
| /verify_remedio_glaucoma/edit/\<int:clean_id\>/unverify | verify_remedio_glaucoma.glaucoma_unverify | POST | verify_remedio_glaucoma/routes.py | admin, optometrist |
| /verify_remedio_glaucoma/edit/\<int:clean_id\>/mark_eye | verify_remedio_glaucoma.glaucoma_mark_eye | POST | verify_remedio_glaucoma/routes.py | admin, optometrist, data_manager |

---

## Patient Screenings Routes

| Route Path | URL For | HTTP Methods | Route File | Roles Required |
|------------|---------|--------------|------------|----------------|
| /screenings/ | screenings.list_screenings | GET | screenings/routes.py | admin, ophthalmologist |
| /screenings/\<int:encounter_id\> | screenings.screening_detail | GET | screenings/routes.py | admin |

---

## Job Processing Routes

| Route Path | URL For | HTTP Methods | Route File | Roles Required |
|------------|---------|--------------|------------|----------------|
| /jobs/ | jobs.list_recent_jobs | GET | jobs/routes.py | admin |
| /jobs/\<job_token\> | jobs.job_status_json | GET | jobs/routes.py | admin, fileUploader, optometrist, data_manager |
| /jobs/\<job_token\>/view | jobs.job_status_page | GET | jobs/routes.py | admin, fileUploader, optometrist, data_manager |

---

## Data Audit Routes

| Route Path | URL For | HTTP Methods | Route File | Roles Required |
|------------|---------|--------------|------------|----------------|
| /audit/missing_capture_date | audit.missing_capture_date | GET | audit/routes.py | admin |

---

## Image Preprocessing Routes

| Route Path | URL For | HTTP Methods | Route File | Roles Required |
|------------|---------|--------------|------------|----------------|
| /preprocess/dashboard | preprocess.anonymization_dashboard | GET | preprocess/anonymize_image.py | fileUploader, optometrist, data_manager, admin |
| /preprocess/anonymize_image/\<uuid:uuid\> | preprocess.anonymize_image | GET, POST | preprocess/anonymize_image.py | fileUploader, optometrist, data_manager, admin |
| /preprocess/anonymize_image/\<uuid:uuid\>/restore_original | preprocess.restore_original_anonymized_image | POST | preprocess/anonymize_image.py | fileUploader, optometrist, data_manager, admin |

---

## Notes

1. **URL For**: This column shows the value used in `url_for()` function in templates and redirects.
2. **Roles Required**: Some routes have role-based access control. The roles are:
   - `admin`: Administrative users
   - `fileUploader`: Users who can upload files
   - `ophthalmologist`: Medical doctors
   - `optometrist`: Eye care professionals
   - `data_manager`: Users who manage data
   - `resident`: Medical residents
   - `login_required`: Any authenticated user
3. **HTTP Methods**: All routes specify the HTTP methods they accept.
4. **Route File**: Indicates which file contains the route implementation.
5. **Data Scoping**: For routes with data scoping, users can only access data related to their associated lab units.

## API Routes

The application also includes API endpoints that are documented separately in [docs/api.md](api.md). These endpoints provide RESTful access to application functionality for programmatic integration.
