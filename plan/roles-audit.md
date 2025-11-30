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

## verify_remedio_glaucoma blueprint (implemented)
- Changes: Roles aligned to `admin/local_admin/fileUploader/optometrist/data_manager`; all pages/actions scoped with `get_user_lab_unit_ids_no_admin_override`. Results/list/clean workflows, detail/edit, verify/unverify, mark_eye, navigation (prev/next/back) all filtered to allowed lab units; users without lab units are blocked.
- Status: Implemented in `verify_remedio_glaucoma/routes.py`.

## verify_remedio_dr blueprint (implemented)
- Changes: Roles aligned to `admin/local_admin/fileUploader/optometrist/data_manager`; list, detail, edit, verify/unverify, mark_eye scoped to allowed lab units via `get_user_lab_unit_ids_no_admin_override`. Prev/next/back navigation and recent lists respect allowed lab units.
- Status: Implemented in `verify_remedio_dr/routes.py`.

## verify_remedio_nodr blueprint (implemented)
- Changes: Roles aligned to `admin/local_admin/fileUploader/optometrist/data_manager`; list, edit, verify/unverify, mark_eye scoped via `get_user_lab_unit_ids_no_admin_override` with prev/next filtered to allowed lab units; users without lab units are blocked. Base encounter queries now use allowed lab units for navigation.
- Status: Implemented in `verify_remedio_nodr/routes.py`.

## preprocess blueprint (implemented)
- Changes: Role gates now `admin/local_admin/fileUploader/optometrist/data_manager`. Dashboard KPIs, lists, filters, dropdowns, and charts are scoped to assigned lab units/hospitals via `get_user_lab_unit_ids_no_admin_override`; invalid filters redirect. Anonymize/restore routes require the image lab unit to be in scope (no admin override) and block users with no lab access; next-image navigation uses the same scoping.
- Status: Implemented in `preprocess/anonymize_image.py`.

## tasks blueprint (implemented)
- Changes: Role gates for task index/pending/all-tasks/view-task-details expanded to `admin/local_admin/fileUploader/ophthalmologist/data_manager/resident/optometrist`; all use `get_user_lab_unit_ids_no_admin_override` and block users without lab access. All-tasks filters, dropdowns, and summaries are restricted to the caller’s lab units/hospitals with invalid filters rejected. Intra-rater admin JSON/UI now filters batches, hospitals, lab units, and graders to allowed lab units; batch creation requires a permitted lab unit and rejects out-of-scope labs. Ad-hoc task pages/search/list/detail are scoped to allowed lab units (no admin override), and batches without in-scope tasks are hidden/blocked.
- Status: Implemented in `tasks/route_index.py`, `tasks/route_pending.py`, `tasks/route_task_details.py`, `tasks/route_organizationalTasks.py`, `tasks/route_intra_rater.py`, `tasks/ad_hoc.py`.

## search blueprint (implemented)
- Changes: Roles expanded to `admin/local_admin/fileUploader/ophthalmologist/data_manager/resident/optometrist`. Search routes now enforce lab-unit access with `get_user_lab_unit_ids_no_admin_override`; users without lab units are redirected. Hospital/lab filters are validated against allowed sets; dropdown data (hospitals, lab units, cameras/diseases/areas) is limited to images within allowed lab units. Search queries always run with allowed lab_unit_ids; out-of-scope hospital/lab requests return 403.
- Status: Implemented in `search/route_search_images.py`, `search/route_search.py`.
