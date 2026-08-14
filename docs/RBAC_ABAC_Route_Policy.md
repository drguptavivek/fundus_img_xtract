# RBAC/ABAC Route Policy

**Document Version:** 1.1
**Last Updated:** 2026-08-14
**Owner:** Security Team  
**Classification:** Internal  
**Related:** `docs/PII_Exposure_Control_Policy.md`

---

## 1. Purpose

Define RBAC (role-based access control) and ABAC (attribute-based access control) rules for each route group in the Fundus Image Manager. This policy is organized by workflow sequence:

Uploading -> Verify/Anonymize -> Grading -> Review -> Intra-rater -> My Discrepancy Reviews -> AI Review -> Analytics -> Admin

---

## 2. Authorization Layers And Enforcement Primitives

Authorization is enforced at multiple trust boundaries. Passing one boundary
does not bypass the others:

1. Routes authenticate and validate transport credentials, rate limits, and
   request shape.
2. Data services scope queries and workflow mutations.
3. `media.authorization` resolves patient-media lineage and independently
   authorizes the object before storage paths, metadata, OCR, or bytes are read.
4. The pure `authz` engine evaluates action policies against normalized
   relationships. It does not query application tables.

Use these standard relationship and scope resolvers:

- **Lab Unit Scoping:** `get_user_lab_unit_ids_no_admin_override(user_id)`
- **Hospital Scoping:** `apply_scoping(query, Model, user, operation)`
- **Grading Eligibility:** `UserDiseaseUnitRole` + `get_user_eligibility_for_task(...)`
- **Persisted Project Roles:** `data_authorization.service`
- **Legacy Project Capabilities:** `encounter_sets.permissions`
- **Patient Media:** `media.authorization.authorize_media_source(...)`
- **Central Decision Engine:** `authz.authorize(...)`

**Policy Rule:** Every route that touches patient data or images must apply an
applicable object/data scoping mechanism in addition to authentication. A
route-level `@roles_required(...)` check alone is insufficient. Route
decorators must not prematurely reject a valid scoped project role, legacy
capability, collaborator relationship, or exact task/media relationship.

`data_authorization` is the persisted project-grant resolver. It is not a
second policy engine. `media.authorization` is a resource enforcement layer,
not another role store.

---

## 3. Uploading

### 3.1 ZIP Uploads (Remedio)

| Route | Methods | Roles | ABAC | Notes |
|------|---------|-------|------|------|
| `/remedio_zip_uploads/upload_files` | GET | admin, local_admin, fileUploader, ophthalmologist, data_manager, resident, optometrist | Lab unit must be in `get_user_lab_unit_ids_no_admin_override` | Select hospital + lab unit; lab unit must belong to hospital |
| `/remedio_zip_uploads/upload` | POST | admin, local_admin, fileUploader, ophthalmologist, data_manager, resident, optometrist | Lab unit must be in `get_user_lab_unit_ids_no_admin_override` | Rejects if lab_unit not in selected hospital |

### 3.2 Direct Uploads

| Route | Methods | Roles | ABAC | Notes |
|------|---------|-------|------|------|
| `/direct/upload` | GET, POST | admin, local_admin, fileUploader, optometrist, data_manager | Lab unit must be in `get_user_lab_unit_ids_no_admin_override` | Enforces hospital/lab unit match |
| `/direct/upload/edit/<int:upload_id>` | GET, POST | admin, local_admin, fileUploader, optometrist, data_manager | Should enforce upload’s lab_unit in allowed set | Image editing before verification |
| `/direct/upload/edit_image/<int:upload_id>` | GET | admin, local_admin, fileUploader, optometrist, data_manager | Same as above | Image crop/mask |
| `/direct/upload/save_image/<int:upload_id>` | POST | admin, local_admin, fileUploader, optometrist, data_manager | Same as above | Save edits |
| `/direct/upload/restore_original/<int:upload_id>` | POST | admin, local_admin, fileUploader, optometrist, data_manager | Same as above | Restore original image |
| `/direct/dashboard` | GET, POST | admin, local_admin, fileUploader, optometrist, data_manager | Scoped via upload eligibility | Upload activity dashboard |
| `/api/direct/upload/status/<job_token>` | GET | admin, local_admin, fileUploader, optometrist, data_manager | Job must belong to user or allowed lab unit | Job status |

### 3.3 Pre-graded Uploads

| Route | Methods | Roles | ABAC | Notes |
|------|---------|-------|------|------|
| `/direct/pregraded` | GET, POST | admin, local_admin, pregraded_uploader | Lab unit must be in allowed list | Pre-graded data import |
| `/direct/pregraded/grades` | GET, POST | admin, local_admin, pregraded_uploader | Lab unit must be in allowed list | Grade ingestion |
| `/direct/pregraded/grades/recent` | GET | admin, local_admin, pregraded_uploader | Lab unit must be in allowed list | Recent pre-graded jobs |

### 3.4 Upload Listing

| Route | Methods | Roles | ABAC | Notes |
|------|---------|-------|------|------|
| `/uploaded_zips` | GET | admin, fileUploader, optometrist, data_manager | Lab unit scoping required in query | Lists uploaded ZIPs |

---

## 4. Verify / Anonymize

### 4.1 ZIP Verification (Remedio)

| Route | Methods | Roles | ABAC | Notes |
|------|---------|-------|------|------|
| `/verify_remedio/` | GET | admin, local_admin, fileUploader, optometrist, data_manager | Uses lab unit scoping in list | Redirects to list |
| `/verify_remedio/list` | GET | admin, local_admin, fileUploader, optometrist, data_manager | `get_user_lab_unit_ids_no_admin_override` | PII visible for optometrist |
| `/verify_remedio/detail/<int:encounter_id>` | GET | admin, local_admin, fileUploader, optometrist, data_manager | Must be in allowed lab units | Encounter details |
| `/verify_remedio/edit/<int:encounter_id>` | GET | admin, local_admin, fileUploader, optometrist, data_manager | Must be in allowed lab units | Edit encounter |
| `/verify_remedio/edit/<int:encounter_id>/save` | POST | admin, local_admin, fileUploader, optometrist, data_manager | Must be in allowed lab units | Save edits |
| `/verify_remedio/edit/<int:encounter_id>/mark_eye` | POST | admin, local_admin, fileUploader, optometrist, data_manager | Must be in allowed lab units | Eye flags |
| `/verify_remedio/edit/<int:encounter_id>/verify/*` | POST | admin, local_admin, fileUploader, optometrist, data_manager | Must be in allowed lab units | DR/Glaucoma/Encounter verify |
| `/verify_remedio/edit/<int:encounter_id>/unverify/*` | POST | admin, local_admin, fileUploader, optometrist, data_manager | Must be in allowed lab units | Unverify |
| `/verify_remedio/edit/<int:encounter_id>/viewer/<int:image_id>` | GET | admin, local_admin, fileUploader, optometrist, data_manager | Must be in allowed lab units | Image viewer |
| `/verify_remedio/kpi_trend` | GET | admin, local_admin, fileUploader, optometrist, data_manager | Uses lab unit scoping | KPI chart |

### 4.2 Disease-specific Verify (DR/Glaucoma/NoDR)

All routes under:
- `/verify_remedio_dr/*`
- `/verify_remedio_glaucoma/*`
- `/verify_remedio_nodr/*`

**Roles:** admin, local_admin, fileUploader, optometrist, data_manager  
**ABAC:** `get_user_lab_unit_ids_no_admin_override` or equivalent lab-unit checks  
**Policy Rule:** The encounter must belong to a lab unit in the user’s allowed set.

### 4.3 Encounter Set Verification

| Route | Methods | Roles | ABAC | Notes |
|------|---------|-------|------|------|
| `/verify_encounter_set/` | GET | admin, optometrist, data_manager | `apply_scoping(..., operation='upload')` | List pending sets |
| `/verify_encounter_set/verify/<uuid>` | GET | admin, optometrist, data_manager | `apply_scoping(..., operation='upload')` | View grid |
| `/verify_encounter_set/update_position` | POST | admin, optometrist, data_manager | `apply_scoping` via encounter | Reorder grid |
| `/verify_encounter_set/finalize/<uuid>` | POST | admin, optometrist, data_manager | `get_user_lab_unit_ids_no_admin_override` | Finalize verified |
| `/verify_encounter_set/edit/<uuid>` | GET | admin, optometrist, data_manager | `apply_scoping` | Edit crop/mask |
| `/verify_encounter_set/save_edit/<uuid>` | POST | admin, optometrist, data_manager | `apply_scoping` | Save edits |
| `/verify_encounter_set/mark_anonymized/<uuid>` | POST | admin, optometrist, data_manager | `apply_scoping` | Mark anonymized |
| `/verify_encounter_set/restore_original/<uuid>` | POST | admin, optometrist, data_manager | `apply_scoping` | Restore original |

### 4.4 Anonymize (Direct Upload PII)

| Route | Methods | Roles | ABAC | Notes |
|------|---------|-------|------|------|
| `/preprocess/dashboard` | GET | admin, local_admin, fileUploader, optometrist, data_manager | `get_user_lab_unit_ids_no_admin_override` | Lists PII candidates |
| `/preprocess/anonymize_image/<uuid>` | GET, POST | admin, local_admin, fileUploader, optometrist, data_manager | Allowed lab units only | Mask/verify PII |
| `/preprocess/anonymize_image/<uuid>/pii_override` | POST | admin, local_admin, fileUploader, optometrist, data_manager | Allowed lab units only | Override PII flag |
| `/preprocess/anonymize_image/<uuid>/restore_original` | POST | admin, local_admin, fileUploader, optometrist, data_manager | Allowed lab units only | Restore original |

---

## 5. Grading

### 5.1 Core Dual Grading

| Route | Methods | Roles | ABAC | Notes |
|------|---------|-------|------|------|
| `/grading/` | GET | resident, ophthalmologist | Role-based dashboard | No PII (masked) |
| `/grading/grade/<int:disease_id>/<role_slot>` | GET | resident, ophthalmologist | `UserDiseaseUnitRole` via eligibility in task selection | Resident2/arbitrator limited to ophthalmologist |
| `/grading/task/<task_uuid>/<slot_type>` | GET | resident, ophthalmologist, admin | Eligibility check in `get_user_eligibility_for_task` | PII masked |
| `/grading/task/submit` | POST | resident, ophthalmologist, admin | Eligibility + role slot enforcement | Save grade |
| `/grading/revise/<int:grade_id>` | GET | resident, ophthalmologist, admin | Must be grader + eligible | Revision |

### 5.2 Encounter Set Grading

| Route | Methods | Roles | ABAC | Notes |
|------|---------|-------|------|------|
| `/grading/encounter_set/<uuid>` | GET | resident, resident2, ophthalmologist, arbitrator, admin | Must be eligible for encounter set | Set-based grading |

### 5.3 Intra-rater (Grading)

| Route | Methods | Roles | ABAC | Notes |
|------|---------|-------|------|------|
| `/grading/intra-rater` | GET | resident, ophthalmologist, admin | `UserDiseaseUnitRole` + lab unit | Intra-rater queue |
| `/grading/intra-rater/<task_uuid>` | GET | resident, ophthalmologist, admin | Eligibility in task fetch | Intra-rater task |

### 5.4 Inter-rater + Statistics

| Route | Methods | Roles | ABAC | Notes |
|------|---------|-------|------|------|
| `/grading/inter-rater` | GET | ophthalmologist, admin | Scope by lab unit where applied | Comparison |
| `/grading/inter-rater/<int:task_id>` | GET | ophthalmologist, admin | Scope by lab unit | Task compare |
| `/grading/grader-statistics` | GET | ophthalmologist, local_admin, data_manager, admin | Lab-unit scope in queries | KPI stats |

---

## 6. Review

### 6.1 Discrepancy Review

| Route | Methods | Roles | ABAC | Notes |
|------|---------|-------|------|------|
| `/review/discrepancy-review` | GET | admin, discrepancy_reviewer, data_exporter | `apply_scoping(..., operation='view')` | Lab unit filter |
| `/review/discrepancy-export` | POST | admin, data_manager, data_exporter | Allowed lab units only | Export (PII masked) |
| `/review/discrepancy-export/<job_token>/<path:filename>` | GET | admin, data_manager, data_exporter | Job must belong to user or lab unit | Export download |

### 6.2 Task Review

| Route | Methods | Roles | ABAC | Notes |
|------|---------|-------|------|------|
| `/review/reviewTaskDetails/<int:task_id>` | GET, POST | discrepancy_reviewer or matching project grant | Shared task capability scope | Task review |
| `/review/my-discrepancy-reviews` | GET | discrepancy_reviewer or matching project grant | Shared task capability scope + current user | Personal discrepancy-review history |
| `/api/review/me/discrepancy-reviews` | GET | discrepancy_reviewer or matching project grant | Shared task capability scope + current user | JSON history contract |

---

## 7. Intra-rater (Tasks)

| Route | Methods | Roles | ABAC | Notes |
|------|---------|-------|------|------|
| `/tasks/intra-rater/batches` | GET, POST | admin, data_manager | `get_user_lab_unit_ids_no_admin_override` | Batch creation |
| `/tasks/intra-rater/my-tasks` | GET | ophthalmologist, admin, data_manager | Allowed lab units only | My intra-rater tasks |
| `/tasks/intra-rater/tasks/<int:task_id>/submit` | POST | ophthalmologist | Allowed lab units only | Submit intra-rater |
| `/tasks/intra-rater/kpi-data` | GET | ophthalmologist, admin, data_manager | Allowed lab units only | KPI |
| `/tasks/intra-rater` | GET | ophthalmologist, admin, data_manager | Allowed lab units only | Intra-rater list |
| `/tasks/intra-rater/admin` | GET | admin, data_manager | Allowed lab units only | Admin view |

---

## 8. My Discrepancy Reviews

Covered in **Review / Task Review** above (`/review/my-discrepancy-reviews`).
Policy: must be scoped to user’s lab units and user identity.

---

## 9. AI Review

AI review is exposed via Review/Discrepancy filters and Task Review filters.

| Route | Methods | Roles | ABAC | Notes |
|------|---------|-------|------|------|
| `/review/discrepancy-review` | GET | admin, discrepancy_reviewer, data_exporter | Lab unit scope | AI model filter supported |
| `/review/reviewTaskDetails/<int:task_id>` | GET, POST | admin, local_admin, data_manager, optometrist | Lab unit scope | AI grade status update |

---

## 10. Analytics

| Route Group | Roles | ABAC | Notes |
|------------|------|------|------|
| `/analytics/encounters` | admin, local_admin, data_manager, analytics_viewer | Lab unit scope | Encounter listing |
| `/analytics/encounter/view/<int:encounter_id>` | admin, local_admin, data_manager, analytics_viewer | Lab unit scope | Encounter details |
| `/analytics/encounter-files` | admin, local_admin, data_manager, analytics_viewer | Lab unit scope | File KPIs |
| `/analytics/images` | admin, local_admin, data_manager, analytics_viewer | Lab unit scope | Image KPIs |
| `/analytics/images-without-tasks` | admin, local_admin, data_manager, analytics_viewer | Lab unit scope | Missing tasks |
| `/analytics/direct/view/<uuid>` | admin, local_admin, data_manager, analytics_viewer | Lab unit scope | Direct upload view |
| `/analytics/direct-uploads/kpi` | admin, local_admin, data_manager, analytics_viewer | Lab unit scope | Direct KPIs |
| `/analytics/dataset-curation*` | admin, local_admin, data_manager, data_exporter, dataset_creator, analytics_viewer | Lab unit scope | Dataset curation |
| `/analytics/dataset-export/*` | admin, local_admin, data_manager, data_exporter, dataset_creator | Lab unit scope | Exports |
| `/analytics/model-performance*` | admin, local_admin, data_manager, analytics_viewer | Lab unit scope | AI metrics |
| `/analytics/encounters-simple` | admin, local_admin, data_manager, analytics_viewer | Lab unit scope | Simple listing |

**Policy Rule:** analytics routes must not return patient PII unless explicitly allowed in `docs/PII_Exposure_Control_Policy.md`.

### 10.1 Patient Media Used By Analytics And Workflows

| Route Group | Transport Gate | Object Authorization | Notes |
|------------|----------------|----------------------|------|
| `/media/img/<uuid>` and legacy image variants | Authenticated session | `media.image.view` or `media.thumbnail.view` | Full, edited, final, and thumbnail variants share one resource decision |
| `/media/<uuid>*` | HMAC credential; session auth also applies when logged in | Exact signed-media relationship plus session object authority when present | Successful HMAC validation is cached only until token expiry, capped at 15 minutes |
| Encounter PDFs and DR/glaucoma reports | Authenticated session | `media.pdf.view` | Missing and unauthorized objects use non-disclosing responses |
| `/api/images/<uuid>/metadata*` | Authenticated API role | `media.metadata.read` or `media.metadata.process` | Authorization occurs before path or metadata-cache access |
| `/api/ocr/*` | Authenticated API role | `media.ocr_pii.read` or `media.ocr_pii.process` | Authorization occurs before OCR record/cache/path access |
| Mobile upload thumbnail | Mobile bearer session plus job ownership | `media.thumbnail.view` | Both workflow ownership and media authority are required |
| Glaucoma-AI image and thumbnail | Mobile bearer session plus uploader/workflow visibility | `media.image.view` or `media.thumbnail.view` | Direct uploader authority is exact-UUID only |

Project media relationships may come from a scoped project role, legacy
project capability, collaborator membership, exact grading-task eligibility,
or exact direct-uploader ownership. Classical media continues to use accepted
admin, hospital, or lab-unit relationships.

Authorization decisions use Redis for 900 seconds. Image and thumbnail actions
share the same decision key. User, project, and signing-hospital epochs are
advanced only after a successful database commit; rollbacks discard pending
invalidation. Redis errors fall back to persisted relationship evaluation and
never create an allow result.

Authorization telemetry is resource-blind for denials: it records action,
outcome, and actor ID but not cache state, UUID, media source type, storage path,
denial reason, signed token, or cache key. Successful decisions may include
cache-hit state and grant source.

---

## 11. Admin

All `/admin/*` routes MUST require `@roles_required(...)` and should default to `admin` unless explicitly permitted.

Key admin route groups:

| Route Group | Roles | ABAC | Notes |
|------------|------|------|------|
| `/admin/users*` | admin | N/A | User management |
| `/admin/roles*` | admin | N/A | Role management |
| `/admin/settings*` | admin | N/A | App settings |
| `/admin/hospital*`, `/admin/lab_unit*` | admin | N/A | Lookups |
| `/admin/disease*`, `/admin/area*`, `/admin/camera*` | admin | N/A | Lookups |
| `/admin/disease-gradings*` | admin | N/A | Grading options |
| `/admin/linked-disease-gradings*` | admin | N/A | Linked grading |
| `/admin/upload-quotas*` | admin, data_manager | Lab unit scoped if applicable | Upload quotas |
| `/admin/database-dump*` | admin | N/A | Sensitive export |
| `/admin/database-excel-export*` | admin | N/A | Sensitive export |
| `/admin/database-restore*` | admin | N/A | Restore |
| `/admin/audit*` | admin, local_admin, data_manager | N/A | Audit logs |
| `/admin/s3*` | admin, local_admin | Hospital scoped | S3 configs |
| `/admin/cve*` | admin, local_admin | N/A | Vulnerability report |
| `/admin/package-updates*` | admin, local_admin | N/A | Update report |
| `/admin/ai-models*` | admin | N/A | AI model registry |
| `/admin/materialized-view-status*` | admin | N/A | MV refresh |
| `/admin/thumbnail-management*` | admin, data_manager | Lab unit scoped | Thumbnail ops |
| `/admin/image-metadata*` | admin, local_admin | Hospital scoped | PII status |

---

## 12. Gaps / Decisions Needed

1. **Direct upload edit routes**: confirm they enforce lab unit scoping per upload ID.  
2. **Uploaded ZIP list**: confirm lab unit scoping is applied in queries.  
3. **Admin route granularity**: decide which routes may be delegated to local_admin beyond current usage.  
4. **AI review**: confirm whether AI review actions should be restricted to `data_manager` or `discrepancy_reviewer` only.  
5. **Route inventory drift**: the route tables above are a policy inventory,
   not a generated route manifest. Compare them with `flask routes` during each
   authorization migration and update renamed API paths.

---

## 13. Enforcement Checklist

- [ ] Every protected route has an authentication or signed-credential gate
- [ ] Route decorators permit applicable scoped project and workflow authorities
- [ ] Every data-access route applies classical or project-aware object scoping
- [ ] Every patient-media delivery path calls the shared media resolver before storage access
- [ ] Grading routes use `UserDiseaseUnitRole` for role-slot eligibility
- [ ] Analytics routes return masked PII (unless explicitly allowed)
- [ ] Sensitive exports require re-auth + audit per `PII_Exposure_Control_Policy.md`
- [ ] Redis authorization invalidation occurs after commit and is discarded on rollback
- [ ] Denial telemetry omits resource identity, source type, path, reason, token, and cache key
