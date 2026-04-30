# Upload Policy

This project separates **dashboard visibility** from **upload entitlement**.

## 1. Dashboard access

These roles may open upload-related dashboard pages and view upload statistics:

- `admin`
- `local_admin`
- `data_manager`
- `ophthalmologist`
- `resident`
- `optometrist`
- `fileUploader`

Examples:

- Upload dashboards
- Upload statistics
- Uploaded image listings
- Eligibility summaries shown on dashboards for reporting

## 2. Upload-form access

Only users with the `fileUploader` role may open or submit upload forms.

This includes:

- direct image upload forms
- ZIP upload forms
- pre-graded image upload forms
- pre-graded grade import forms
- upload-eligibility selectors
- form submissions that create upload jobs
- helper API calls used by upload forms
- encounter-set image upload submission API

## 3. Restricted upload eligibility

The following upload eligibility selectors are restricted to `fileUploader`:

- hospital
- lab unit
- project
- disease
- camera

If a user does not have `fileUploader`, they may still see the dashboard, but they must not be able to open the form or submit uploads.

## 4. Project-scoped grants

Project-scoped grants do not replace the `fileUploader` role for upload-form access.

They are used to narrow the valid combinations once a user is already allowed to upload, for example:

- project
- lab unit
- disease
- camera
- area
- mydriatic / non-mydriatic constraints

## 5. Current implementation intent

The application should follow this rule set:

- dashboard pages remain visible to the broader clinical/admin roles
- upload forms remain hidden unless the user has `fileUploader`
- upload helper APIs remain restricted to `fileUploader`
- upload-eligibility cards and selectors remain hidden unless the user has `fileUploader`
- `master-admin` does not bypass upload policy; it still needs the same explicit role grants as other users

`master-admin` may still have access to general admin pages, but it must not be treated as an automatic upload permission override.

## 6. Related code

- [`direct_uploads/upload.py`](/home/eyeimg/fundus_img_xtract/direct_uploads/upload.py)
- [`direct_uploads/pregraded.py`](/home/eyeimg/fundus_img_xtract/direct_uploads/pregraded.py)
- [`direct_uploads/dashboard.py`](/home/eyeimg/fundus_img_xtract/direct_uploads/dashboard.py)
- [`api/encounter_set.py`](/home/eyeimg/fundus_img_xtract/api/encounter_set.py)
- [`api/direct_uploads.py`](/home/eyeimg/fundus_img_xtract/api/direct_uploads.py)
- [`api/upload_stats.py`](/home/eyeimg/fundus_img_xtract/api/upload_stats.py)
- [`templates/direct_uploads/index.html`](/home/eyeimg/fundus_img_xtract/templates/direct_uploads/index.html)
- [`templates/base.html`](/home/eyeimg/fundus_img_xtract/templates/base.html)
- [`templates/home.html`](/home/eyeimg/fundus_img_xtract/templates/home.html)
