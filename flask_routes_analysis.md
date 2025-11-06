# Flask Application Routes Analysis

This document provides a comprehensive analysis of all routes in the Fundus Image Manager Flask application, organized by blueprint/module.

## Application Structure

The application uses Flask blueprints to modularize routes. Based on the analysis of `app.py` and all blueprint files, here are all the routes organized by their respective modules:

## 1. Main Application Routes (app.py)

| Route | Methods | Authentication | Description |
|--------|----------|----------------|-------------|
| `/` | GET | Protected | Main dashboard/home page |
| `/login` | GET, POST | Public | User login page |
| `/logout` | GET | Protected | User logout |
| `/change_password` | GET, POST | Protected | Change user password |

## 2. Account Blueprint (`account/`)

| Route | Methods | Authentication | Roles | Description |
|--------|----------|----------------|---------|-------------|
| `/account/` | GET | Protected | User account profile |
| `/account/change_password` | GET, POST | Protected | Change account password |

## 3. Admin Blueprint (`admin/`)

| Route | Methods | Authentication | Roles | Description |
|--------|----------|----------------|---------|-------------|
| `/admin/` | GET | Protected | admin, data_manager | Admin dashboard |
| `/admin/users` | GET, POST | Protected | admin, data_manager | User management |
| `/admin/edit_user/<int:user_id>` | GET, POST | Protected | admin, data_manager | Edit user |
| `/admin/add_user` | GET, POST | Protected | admin, data_manager | Add new user |
| `/admin/change_password/<int:user_id>` | GET, POST | Protected | admin, data_manager | Change user password |
| `/admin/ai_models` | GET | Protected | admin, data_manager | AI model management |
| `/admin/ai_model_edit/<int:model_id>` | GET, POST | Protected | admin, data_manager | Edit AI model |
| `/admin/disease_gradings` | GET, POST | Protected | admin, data_manager | Disease grading management |
| `/admin/edit_grading_eligibility` | GET, POST | Protected | admin, data_manager | Edit grading eligibility |
| `/admin/lookup_edit/<string:lookup_type>` | GET, POST | Protected | admin, data_manager | Edit lookup tables |
| `/admin/lookup_list/<string:lookup_type>` | GET | Protected | admin, data_manager | List lookup items |
| `/admin/malicious_uploads` | GET | Protected | admin, data_manager | View malicious uploads |
| `/admin/role_usage` | GET | Protected | admin, data_manager | Role usage statistics |

## 4. Analytics Blueprint (`analytics/`)

| Route | Methods | Authentication | Roles | Description |
|--------|----------|----------------|---------|-------------|
| `/analytics/` | GET | Protected | admin, data_manager | Analytics dashboard |
| `/analytics/view_upload/<string:uuid_str>` | GET | Protected | admin, data_manager, optometrist | View upload details |
| `/analytics/direct_files_kpi` | GET | Protected | admin, data_manager | Direct files KPI |
| `/analytics/encounter_files_kpi` | GET | Protected | admin, data_manager | Encounter files KPI |
| `/analytics/encounter_results` | GET | Protected | admin, data_manager | Encounter results |
| `/analytics/image_results` | GET | Protected | admin, data_manager | Image results |
| `/analytics/images_without_tasks` | GET | Protected | admin, data_manager | Images without tasks |
| `/analytics/task_details/<int:task_id>` | GET | Protected | admin, data_manager, optometrist | Task details |
| `/analytics/direct_view` | GET | Protected | admin, data_manager | Direct view analytics |
| `/analytics/encounter_view` | GET | Protected | admin, data_manager | Encounter view analytics |

## 5. API Blueprint (`api/`)

| Route | Methods | Authentication | Roles | Description |
|--------|----------|----------------|---------|-------------|
| `/api/hospitals` | GET | Protected | admin, data_manager | Get hospitals |
| `/api/lab_units/<int:hospital_id>` | GET | Protected | admin, data_manager | Get lab units for hospital |
| `/api/ai_models` | GET, POST | Protected | admin, data_manager | AI model CRUD |
| `/api/disease` | GET, POST | Protected | admin, data_manager | Disease CRUD |
| `/api/grading_eligibility` | GET, POST | Protected | admin, data_manager | Grading eligibility |
| `/api/gradings` | GET, POST | Protected | admin, data_manager | Gradings management |
| `/api/kpis/direct_files_kpis` | GET | Protected | admin, data_manager | Direct files KPI data |
| `/api/kpis/encounter_files_kpis` | GET | Protected | admin, data_manager | Encounter files KPI data |

## 6. Auth Blueprint (`auth/`)

| Route | Methods | Authentication | Roles | Description |
|--------|----------|----------------|---------|-------------|
| `/auth/forgot_password` | GET, POST | Public | Forgot password |
| `/auth/reset_password` | GET, POST | Public | Reset password |

## 7. Dashboard Blueprint (`dashboard/`)

| Route | Methods | Authentication | Roles | Description |
|--------|----------|----------------|---------|-------------|
| `/dashboard/` | GET | Protected | admin, data_manager | Main dashboard |
| `/dashboard/hospitals` | GET | Protected | admin, data_manager | Hospitals list |
| `/dashboard/hospital/<int:hospital_id>` | GET | Protected | admin, data_manager | Hospital details |
| `/dashboard/images` | GET | Protected | admin, data_manager | Images list |

## 8. Direct Uploads Blueprint (`direct_uploads/`)

| Route | Methods | Authentication | Roles | Description |
|--------|----------|----------------|---------|-------------|
| `/direct_uploads/` | GET | Protected | fileUploader, optometrist, data_manager, admin | Direct uploads index |
| `/direct_uploads/upload` | GET, POST | Protected | fileUploader, optometrist, data_manager, admin | Upload images |
| `/direct_uploads/edit_upload/<string:uuid_str>` | GET, POST | Protected | fileUploader, optometrist, data_manager, admin | Edit upload |
| `/direct_uploads/pregraded_upload` | GET, POST | Protected | fileUploader, optometrist, data_manager, admin | Pre-graded upload |
| `/direct_uploads/pregraded_grades/<string:uuid_str>` | GET, POST | Protected | fileUploader, optometrist, data_manager, admin | Pre-graded grades |
| `/direct_uploads/recent_grades` | GET | Protected | fileUploader, optometrist, data_manager, admin | Recent grades |

## 9. Grading Blueprint (`grading/`)

| Route | Methods | Authentication | Roles | Description |
|--------|----------|----------------|---------|-------------|
| `/grading/` | GET | Protected | resident, ophthalmologist | Grading dashboard |
| `/grading/task/<string:task_uuid>/<string:slot_type>` | GET | Protected | resident, ophthalmologist, admin | Dual grading task |
| `/grading/task/submit` | POST | Protected | resident, ophthalmologist, admin | Submit grade |
| `/grading/revise/<int:grade_id>` | GET | Protected | resident, ophthalmologist, admin | Revise grading |
| `/grading/intra-task/<string:task_uuid>` | GET | Protected | resident, ophthalmologist, admin | Intra-rater task |
| `/grading/intra-task/submit` | POST | Protected | resident, ophthalmologist, admin | Submit intra-rater grade |
| `/grading/grade/<int:disease_id>/<string:role_slot>` | GET | Protected | resident, ophthalmologist | Start grading |

## 10. Help Blueprint (`help/`)

| Route | Methods | Authentication | Roles | Description |
|--------|----------|----------------|---------|-------------|
| `/help/` | GET | Protected | All authenticated users | Help documentation |

## 11. Jobs Blueprint (`jobs/`)

| Route | Methods | Authentication | Roles | Description |
|--------|----------|----------------|---------|-------------|
| `/jobs/` | GET | Protected | All authenticated users | Jobs index |
| `/jobs/upload_processing/<string:job_id>` | GET | Protected | All authenticated users | Upload processing status |

## 12. Media Blueprint (`media/`)

| Route | Methods | Authentication | Roles | Description |
|--------|----------|----------------|---------|-------------|
| `/media/uploads/<path:filename>` | GET | Protected | All authenticated users | Serve uploaded files |

## 13. Remedio ZIP Uploads Blueprint (`remedio_zip_uploads/`)

| Route | Methods | Authentication | Roles | Description |
|--------|----------|----------------|---------|-------------|
| `/remedio_zip_uploads/` | GET | Protected | fileUploader, optometrist, data_manager, admin | ZIP uploads index |
| `/remedio_zip_uploads/upload` | GET, POST | Protected | fileUploader, optometrist, data_manager, admin | Upload ZIP files |

## 14. Reports Blueprint (`reports/`)

| Route | Methods | Authentication | Roles | Description |
|--------|----------|----------------|---------|-------------|
| `/reports/` | GET | Protected | admin, data_manager | Reports index |

## 15. Review Blueprint (`review/`)

| Route | Methods | Authentication | Roles | Description |
|--------|----------|----------------|---------|-------------|
| `/review/discrepancy_review` | GET, POST | Protected | admin, data_manager, ophthalmologist | Discrepancy review |
| `/review/task_review` | GET, POST | Protected | admin, data_manager, ophthalmologist | Task review |

## 16. Screenings Blueprint (`screenings/`)

| Route | Methods | Authentication | Roles | Description |
|--------|----------|----------------|---------|-------------|
| `/screenings/` | GET | Protected | admin, data_manager, optometrist | Screenings index |
| `/screenings/detail/<int:encounter_id>` | GET | Protected | admin, data_manager, optometrist | Screening details |

## 17. Search Blueprint (`search/`)

| Route | Methods | Authentication | Roles | Description |
|--------|----------|----------------|---------|-------------|
| `/search/` | GET | Protected | admin, data_manager | Search index |
| `/search/images` | GET | Protected | admin, data_manager | Search images |

## 18. Tasks Blueprint (`tasks/`)

| Route | Methods | Authentication | Roles | Description |
|--------|----------|----------------|---------|-------------|
| `/tasks/` | GET | Protected | admin, data_manager, ophthalmologist, optometrist | Tasks index |
| `/tasks/pending` | GET | Protected | admin, data_manager, ophthalmologist, optometrist | Pending tasks |
| `/tasks/viewTaskDetails/<int:task_id>` | GET | Protected | admin, data_manager, optometrist | Task details |

## 19. Verify Remedio DR Blueprint (`verify_remedio_dr/`)

| Route | Methods | Authentication | Roles | Description |
|--------|----------|----------------|---------|-------------|
| `/verify_remedio_dr/list` | GET | Protected | admin, optometrist, data_manager | DR verification list |
| `/verify_remedio_dr/detail/<int:report_id>` | GET | Protected | admin, optometrist, data_manager | DR verification detail |
| `/verify_remedio_dr/edit/<int:report_id>` | GET, POST | Protected | admin, optometrist, data_manager | Edit DR report |
| `/verify_remedio_dr/edit/<int:report_id>/verify` | POST | Protected | admin, optometrist, data_manager | Verify DR report |
| `/verify_remedio_dr/edit/<int:report_id>/unverify` | POST | Protected | admin, optometrist, data_manager | Unverify DR report |
| `/verify_remedio_dr/edit/<int:report_id>/mark_eye` | POST | Protected | admin, optometrist, data_manager | Mark eye laterality |

## 20. Verify Remedio No-DR Blueprint (`verify_remedio_nodr/`)

| Route | Methods | Authentication | Roles | Description |
|--------|----------|----------------|---------|-------------|
| `/verify_remedio_nodr/list` | GET | Protected | admin, optometrist, data_manager | No-DR verification list |
| `/verify_remedio_nodr/edit/<int:encounter_id>` | GET, POST | Protected | admin, optometrist, data_manager | Edit No-DR encounter |
| `/verify_remedio_nodr/edit/<int:encounter_id>/verify` | POST | Protected | admin, optometrist, data_manager | Verify No-DR encounter |
| `/verify_remedio_nodr/edit/<int:encounter_id>/unverify` | POST | Protected | admin, optometrist, data_manager | Unverify No-DR encounter |
| `/verify_remedio_nodr/edit/<int:encounter_id>/mark_eye` | POST | Protected | admin, optometrist, data_manager | Mark eye laterality |

## 21. Audit Blueprint (`audit/`)

| Route | Methods | Authentication | Roles | Description |
|--------|----------|----------------|---------|-------------|
| `/audit/missing_capture_date` | GET | Protected | admin | View encounters missing capture dates |

## 22. Docs Blueprint (`docs/`)

| Route | Methods | Authentication | Roles | Description |
|--------|----------|----------------|---------|-------------|
| `/docs/` | GET | Public | Documentation index |
| `/docs/api.md` | GET | Public | API documentation (markdown) |
| `/docs/api.html` | GET | Public | API documentation (HTML) |
| `/docs/openapi.yaml` | GET | Public | OpenAPI specification |

## Authentication Patterns

The application uses role-based access control with the following main roles:
- `admin` - Full system access
- `data_manager` - Data management access
- `ophthalmologist` - Medical expert access
- `optometrist` - Basic medical access
- `resident` - Trainee access
- `fileUploader` - File upload access

## Route Protection

Most routes are protected and require authentication. The only public routes are:
- `/login`
- `/auth/forgot_password`
- `/auth/reset_password`
- `/docs/*` (documentation routes)

## Key Features by Module

1. **User Management**: Account and admin blueprints handle user authentication, profile management
2. **Image Management**: Direct uploads, remedio ZIP uploads handle image ingestion
3. **Verification**: verify_remedio_dr and verify_remedio_nodr handle report verification
4. **Grading**: Grading blueprint handles dual grading workflow with resident/resident2/arbitrator roles
5. **Analytics**: Analytics blueprint provides KPIs and data analysis
6. **Search**: Search blueprint provides image search capabilities
7. **Task Management**: Tasks blueprint handles task viewing and management
8. **Audit**: Audit blueprint provides data quality checks
9. **API**: API blueprint provides REST endpoints for frontend integration
10. **Documentation**: Docs blueprint serves API documentation

This comprehensive route structure supports the complete workflow of the Fundus Image Manager system, from image upload through verification, grading, and analysis.