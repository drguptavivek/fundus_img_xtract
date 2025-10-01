# Upload & Verification RBAC Scoping Summary

## Findings
- **Remedio ZIP Uploads**: Routes enforce RBAC (`admin`, `fileUploader`) and validate hospital/lab selections, including cross-checking lab units owned by the user. ✅
- **Direct Uploads**: `/upload` hub, upload workflow, processing views, and anonymization tools now share the aligned role set (`fileUploader`, `optometrist`, `data_manager`, `admin`). Non-admin users are additionally constrained to their assigned lab units during submission and metadata edits. ✅
- **Verification (Glaucoma & DR)**: Listings and detail views respect lab-unit scope for non-admin users, preventing cross-site verification while retaining admin/data manager override. ✅

## Follow-ups
1. Monitor API endpoints (e.g., `direct_uploads.api`) when expanding capabilities to ensure they continue mirroring the same RBAC and lab-unit scoping rules. No gaps identified today.
2. Communicate the removal of the legacy `contributor` role to admins so user provisioning scripts and documentation stay in sync.
