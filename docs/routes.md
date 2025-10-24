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
- **Optometrists** have access to specific routes only (search, task details), also scoped to their associated lab units
- All access is restricted based on lab unit associations, meaning users can only view data related to the lab units they are associated with
- Filtering options are restricted so users can only filter by lab units they have access to
- UI dropdowns only show lab units and hospitals that the user has permission to access
- **Navbar visibility**: The "Discrepancy Review" link in the "Grade" menu is only visible to admin and data_manager roles (not visible to ophthalmologists)

### Route Summary

| Route Path | URL For | HTTP Methods | Roles Required | Purpose |
|------------|---------|--------------|----------------|---------|
| /analytics/images | analytics.image_results | GET | admin, data_manager | Render per-image grading results with filtering and pagination |
| /analytics/encounters | analytics.encounter_results | GET | admin, data_manager | Render encounter-level grading summaries |
| /analytics/images/no-tasks | analytics.images_without_tasks | GET | admin, data_manager | Display images that have no associated grading tasks |
| /analytics/images/search | analytics.search_images | GET | admin, data_manager, optometrist | Search for images with comprehensive filters |
| /analytics/direct/view/\<uuid_str\> | analytics.direct_view | GET | admin, data_manager | View details for a direct image upload |
| /analytics/encounter/view/\<int:encounter_id\> | analytics.encounter_view | GET | admin, data_manager | View details for a specific encounter |
| /analytics/encounters-simple | analytics.encounter_results_simple | GET | admin, data_manager | Render a simplified encounter list showing only encounters with non-pending tasks |
| /analytics/discrepancy-review | analytics.discrepancy_review | GET | admin, data_manager | Main page for discrepancy review process |
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
- **Organizational tasks route** (`/tasks/organizational-tasks`) is restricted to admin and data_manager roles only
- **Navbar visibility**: The "Tasks and Images" dropdown menu in the navbar is only visible to admin, data_manager, and optometrist roles (not visible to ophthalmologists)

### Route Summary

| Route Path | URL For | HTTP Methods | Roles Required | Purpose |
|------------|---------|--------------|----------------|---------|
| /tasks/ | tasks.index | GET | admin, data_manager, ophthalmologist, optometrist | Main tasks page |
| /tasks/my-tasks | tasks.my_tasks | GET | admin, data_manager, ophthalmologist, optometrist | View and manage user's assigned tasks |
| /tasks/pending | tasks.pending_tasks | GET | admin, data_manager, ophthalmologist, optometrist | View pending tasks in user's lab units |
| /tasks/organizational-tasks | tasks.organizational_tasks | GET | admin, data_manager | View all tasks scoped to user's lab units with filtering options |

---

## Search Routes

### Search Images Route

- **Route Path**: `/search/images/`
- **HTTP Methods**: GET
- **Route File**: `search/route_search_images.py`
- **Roles Required**: admin, data_manager
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
| /grading/ | grading.index | GET, POST | grading/dashboard.py | resident, ophthalmologist |
| /grading/grade/\<int:disease_id\>/\<string:role_slot\> | grading.start_grading | GET | grading/start_grading.py | resident, ophthalmologist |
| /grading/task/\<int:task_id\>/\<string:slot_type\> | grading.dual_grading_task | GET | grading/dual_grading.py | resident, ophthalmologist, admin |
| /grading/task/submit | grading.dual_grading_submit | POST | grading/dual_grading.py | resident, ophthalmologist, admin |
| /grading/revise/\<int:grade_id\> | grading.revise_grading | GET | grading/dual_grading.py | resident, ophthalmologist, admin |

---

## Media Serving Routes

| Route Path | URL For | HTTP Methods | Route File | Roles Required |
|------------|---------|--------------|------------|----------------|
| /media/encounter/img/\<uuid_str\> | media._encounterImageByUUID | GET | media/routes.py | fileUploader, optometrist, data_manager, admin, ophthalmologist, resident |
| /media/direct_upload/org_img/\<uuid_str\> | media._directImgOrigByUUID | GET | media/routes.py | fileUploader, optometrist, data_manager, admin, ophthalmologist, resident |
| /media/direct_upload/ed_img/\<uuid_str\> | media._directImgEdByUUID | GET | media/routes.py | fileUploader, optometrist, data_manager, admin, ophthalmologist, resident |
| /media/direct_upload/fn_img/\<uuid_str\> | media._directImgFinalByUUID | GET | media/routes.py | fileUploader, optometrist, data_manager, admin, ophthalmologist, resident |
| /media/img/\<uuid_str\> | media._imgForGradingByUUID | GET | media/routes.py | fileUploader, optometrist, data_manager, admin, ophthalmologist, resident |

---

## Report Serving Routes

| Route Path | URL For | HTTP Methods | Route File | Roles Required |
|------------|---------|--------------|------------|----------------|
| /reports/dr/\<path:filename\> | reports.serve_dr_pdf | GET | reports/routes.py | admin, fileUploader, optometrist, data_manager |
| /reports/glaucoma/\<path:filename\> | reports.serve_glaucoma_pdf | GET | reports/routes.py | admin, fileUploader, optometrist, data_manager |
| /reports/dr/by-uuid/\<uuid\> | reports.serve_dr_pdf_by_uuid | GET | reports/routes.py | admin, fileUploader, optometrist, data_manager |
| /reports/glaucoma/by-uuid/\<uuid\> | reports.serve_glaucoma_pdf_by_uuid | GET | reports/routes.py | admin, fileUploader, optometrist, data_manager |
| /reports/glaucoma_results | reports.glaucoma_results_redirect | GET | reports/routes.py | admin, fileUploader, optometrist, data_manager |

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
| /verify_remedio_glaucoma/results | verify_remedio_glaucoma.glaucoma_results | GET | verify_remedio_glaucoma/routes.py | admin, optometrist, data_manager |
| /verify_remedio_glaucoma/list | verify_remedio_glaucoma.glaucoma_list | GET | verify_remedio_glaucoma/routes.py | admin, optometrist, data_manager |
| /verify_remedio_glaucoma/clean | verify_remedio_glaucoma.glaucoma_clean_workflow | GET, POST | verify_remedio_glaucoma/routes.py | admin, optometrist, data_manager |
| /verify_remedio_glaucoma/detail/\<int:clean_id\> | verify_remedio_glaucoma.glaucoma_detail | GET | verify_remedio_glaucoma/routes.py | admin, optometrist, data_manager |
| /verify_remedio_glaucoma/edit/\<int:clean_id\> | verify_remedio_glaucoma.glaucoma_edit | GET, POST | verify_remedio_glaucoma/routes.py | admin, optometrist, data_manager |
| /verify_remedio_glaucoma/edit/\<int:clean_id\>/verify | verify_remedio_glaucoma.glaucoma_verify | POST | verify_remedio_glaucoma/routes.py | admin, optometrist, data_manager |
| /verify_remedio_glaucoma/edit/\<int:clean_id\>/unverify | verify_remedio_glaucoma.glaucoma_unverify | POST | verify_remedio_glaucoma/routes.py | admin, optometrist, data_manager |
| /verify_remedio_glaucoma/edit/\<int:clean_id\>/mark_eye | verify_remedio_glaucoma.glaucoma_mark_eye | POST | verify_remedio_glaucoma/routes.py | admin, optometrist, data_manager |

---

## Patient Screenings Routes

| Route Path | URL For | HTTP Methods | Route File | Roles Required |
|------------|---------|--------------|------------|----------------|
| /screenings/ | screenings.list_screenings | GET | screenings/routes.py | admin, fileUploader, optometrist, data_manager |
| /screenings/\<int:encounter_id\> | screenings.screening_detail | GET | screenings/routes.py | admin, fileUploader, optometrist, data_manager |

---

## Job Processing Routes

| Route Path | URL For | HTTP Methods | Route File | Roles Required |
|------------|---------|--------------|------------|----------------|
| /jobs/ | jobs.list_recent_jobs | GET | jobs/routes.py | - |
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
| /preprocess/dashboard | preprocess.anonymization_dashboard | GET | preprocess/anonymize_image.py | admin, optometrist, data_manager |
| /preprocess/anonymize_image/\<uuid:uuid\> | preprocess.anonymize_image | GET, POST | preprocess/anonymize_image.py | admin, optometrist, data_manager |
| /preprocess/anonymize_image/\<uuid:uuid\>/restore_original | preprocess.restore_original_anonymized_image | POST | preprocess/anonymize_image.py | admin, optometrist, data_manager |

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
6. **Navbar Menu Items**:
   - **Account Menu**: Contains user profile, change password, notifications, and Help items
   - **Help Item**: Provides access to API documentation and user guides

## API Routes

The application includes comprehensive API endpoints that are documented separately in [OpenAPI Specification](openapi.yaml). These endpoints provide RESTful access to application functionality for programmatic integration.

### API Route Summary

| Route Path | HTTP Methods | Route File | Roles Required | Purpose |
|------------|--------------|------------|----------------|---------|
| /api/users/\<int:user_id\>/lab-units | GET | api/direct_uploads.py | admin, data_manager, or user themselves | Get lab units for a user |
| /api/lab-units/\<int:lab_unit_id\>/hospital | GET | api/direct_uploads.py | All authenticated users | Get hospital for a lab unit |
| /api/upload-jobs/\<int:job_id\>/status | GET | api/direct_uploads.py | Job owner | Get upload job status |
| /api/disease-grades/\<int:disease_id\> | GET | api/disease.py | admin, data_manager, optometrist | Get disease grading options |
| /api/diseases-with-gradings | GET | api/disease.py | admin, data_manager, optometrist | Get all diseases with gradings |
| /api/diseases-gradings-features/\<int:disease_id\> | GET | api/disease.py | admin, data_manager, ophthalmologist, resident, optometrist | Get all gradings and features for a disease |
| /api/grading-eligibility/users/\<int:user_id\> | GET | api/grading_eligibility.py | admin | Get user grading eligibility |
| /api/grading-eligibility/users/\<int:user_id\>/details | GET | api/grading_eligibility.py | admin | Get detailed grading eligibility |
| /api/gradings | GET | api/gradings.py | admin, resident, ophthalmologist | Get filtered gradings data |
| /api/hospitals | GET | api/hospitals.py | admin, data_manager, ophthalmologist, resident, optometrist | Get all hospitals |
| /api/hospitals/\<int:hospital_id\> | GET | api/hospitals.py | admin, data_manager, ophthalmologist, resident, optometrist | Get hospital by ID |
| /api/hospitals/\<int:hospital_id\>/labunits | GET | api/labUnits.py | admin, data_manager, ophthalmologist, resident, optometrist | Get lab units by hospital |
| /api/labunits | GET | api/labUnits.py | admin, data_manager, ophthalmologist, resident, optometrist | Get all lab units |
| /api/labunits/\<int:lab_unit_id\> | GET | api/labUnits.py | admin, data_manager, ophthalmologist, resident, optometrist | Get lab unit by ID |
| /api/eligibleLabUnit | GET | api/userUtils.py | admin, data_manager, optometrist, fileUploader | Get eligible lab units |
