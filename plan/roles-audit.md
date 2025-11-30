# Roles and LabUnit Audit

## api blueprint (implemented)
- Changes: Scoped `/api/hospitals*` and `/api/labunits*` to `get_user_lab_unit_ids_no_admin_override`, returning only hospitals/lab units tied to the caller; detail endpoints now 403 when outside scope. Direct uploads endpoints now only allow the caller to fetch their own lab units and block hospital lookup for lab units outside scope. `/api/eligibleLabUnit` no longer accepts a `user_id` override and uses no-admin-override helper. Added `roles_required` with full allowed set (`admin`, `local_admin`, `fileUploader`, `ophthalmologist`, `data_manager`, `resident`, `optometrist`) across these API routes.
- Status: Implemented in `api/hospitals.py`, `api/labUnits.py`, `api/direct_uploads.py`, `api/userUtils.py`.
