# Roles and LabUnit Audit

## api blueprint (implemented)
- Changes: Scoped `/api/hospitals*` and `/api/labunits*` to `get_user_lab_unit_ids_no_admin_override`, returning only hospitals/lab units tied to the caller; detail endpoints now 403 when outside scope. Direct uploads endpoints now only allow the caller to fetch their own lab units and block hospital lookup for lab units outside scope. `/api/eligibleLabUnit` no longer accepts a `user_id` override and uses no-admin-override helper. Added `roles_required` with full allowed set (`admin`, `local_admin`, `fileUploader`, `ophthalmologist`, `data_manager`, `resident`, `optometrist`) across these API routes.
- Status: Implemented in `api/hospitals.py`, `api/labUnits.py`, `api/direct_uploads.py`, `api/userUtils.py`.

## direct_uploads blueprint (implemented)
- Changes: Enforced `get_user_lab_unit_ids_no_admin_override` scoping across UI/API routes; all hospital/lab-unit dropdowns and lookups are limited to assigned lab units only. Managers can act across users only within their assigned lab units. Role gates tightened to the allowed set (`admin`, `local_admin`, `fileUploader`, `optometrist`, `data_manager`) for all direct_uploads routes (UI + APIs + job status); resident/ophthalmologist access removed per guidance. Pregraded grades import and pages now scope lab units with no admin override.
- Status: Implemented in `direct_uploads/api.py`, `direct_uploads/upload.py`, `direct_uploads/dashboard.py`, `direct_uploads/edit_upload.py`, `direct_uploads/edit_image.py`, `direct_uploads/save_image.py`, `direct_uploads/pregraded.py`, `direct_uploads/pregraded_grades.py`, `direct_uploads/jobs.py`.
- Notes: Admin/local_admin can view job status for other users if the job’s lab unit is in their scope. Admin/local_admin/fileUploader/optometrist/data_manager can manage others’ items (edit/bulk actions/edit image/save) within scoped lab units; all actions remain lab-unit scoped with no global override.

## jobs blueprint (implemented)
- Changes: Added login + role gates (`admin`, `local_admin`, `fileUploader`, `optometrist`, `data_manager`) to all routes. Scoped job listings and detail endpoints to the caller’s assigned lab units via `get_user_lab_unit_ids_no_admin_override`; owners can still access their jobs. Admin/local_admin/fileUploader/optometrist/data_manager can view other users’ jobs only when the job’s lab unit is within their scope.
- Status: Implemented in `jobs/routes.py`.
