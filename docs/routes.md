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
19. [Help & Documentation Routes](#help--documentation-routes)
20. [API Routes](#api-routes)
21. [Notifications Routes](#notifications-routes)
22. [Preprocessing Routes](#preprocessing-routes)

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

---

## Authentication Routes

**Base URL:** `/auth`
**No role restrictions** (public routes)

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/login` | GET, POST | login | User login page and form submission |
| `/logout` | GET | logout | User logout |
| `/forgot-password` | GET, POST | forgot_password | Forgot password page and request |
| `/reset-password` | GET, POST | reset_password | Reset password with token |
| `/check-email-status` | GET | check_email_status | Check email verification status |

---

## Account Management Routes

**Base URL:** `/account`
**Role restrictions:** `login_required` for all routes

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | profile | User profile page |
| `/settings` | GET | settings | Account settings |
| `/preferences` | GET | preferences | User preferences |
| `/security` | GET | security | Security settings |
| `/notifications` | GET | notifications | Notification preferences |

---

## Task Management Routes

**Base URL:** `/tasks`
**Role restrictions:** Multiple roles per route

| Route Path | HTTP Methods | Required Roles | Function | Description |
|------------|--------------|---------------|----------|-------------|
| `/` | GET | admin, data_manager, ophthalmologist, optometrist | index | Main tasks page |
| `/pending` | GET | admin, data_manager, ophthalmologist, optometrist | pending | View pending tasks |
| `/viewTaskDetails/<int:task_id>` | GET | admin, data_manager, optometrist | view_task_details | View task details |
| `/all-tasks` | GET | admin, data_manager | all_tasks | View all organizational tasks with filtering |
| `/intra-rater` | GET | ophthalmologist, admin, data_manager | intra_rater_dashboard | Intra-rater task dashboard |
| `/intra-rater/admin` | GET | admin, data_manager | intra_rater_admin | Intra-rater admin management |
| `/intra-rater/batches` | GET, POST | admin, data_manager | list/create_intra_rater_batch | List/create intra-rater batches |
| `/intra-rater/my-tasks` | GET | ophthalmologist, admin, data_manager | list_my_intra_rater_tasks | List user's intra-rater tasks |
| `/intra-rater/tasks/<int:task_id>/submit` | POST | ophthalmologist | submit_intra_rater_grade | Submit intra-rater grade |
| `/intra-rater/kpi-data` | GET | ophthalmologist, admin, data_manager | get_intra_rater_kpi_data | Get intra-rater KPI data |

---

## Ad-Hoc Tasks Routes

**Base URL:** `/tasks/ad_hoc`
**Role restrictions:** admin, data_manager only

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | index | Ad-hoc task creation interface |
| `/list` | GET | list_batches | List ad-hoc batches |
| `/detail/<int:ad_hoc_id>` | GET | detail | View ad-hoc batch details |
| `/search` | GET | search | Search images for ad-hoc tasks |
| `/preview` | POST | preview | Preview ad-hoc task candidates |
| `/create` | POST | create | Create ad-hoc tasks |

---

## Administration Routes

**Base URL:** `/admin`
**Role restrictions:** admin, data_manager only

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | index | Admin dashboard |
| `/users` | GET | users | User management |
| `/roles` | GET | roles | Role management |
| `/hospitals` | GET | hospitals | Hospital management |
| `/lab-units` | GET | lab_units | Lab unit management |
| `/diseases` | GET | diseases | Disease management |
| `/uploads` | GET | uploads | Upload management |
| `/logs` | GET | logs | System logs |
| `/disk-usage` | GET | disk_usage | Disk usage statistics |
| `/ai-models` | GET | ai_models | AI model management |
| `/grading-eligibility` | GET | grading_eligibility | Grading eligibility configuration |
| `/disease-gradings` | GET | disease_gradings | Disease grading management |
| `/security` | GET | security | Security settings |
| `/database-dump` | GET | database_dump | Database dump functionality |
| `/database-export` | GET | database_excel_export | Database export to Excel |
| `/materialized-view` | GET | materialized_view_status | Materialized view status and management |
| `/rate-limit` | GET | rate_limit_admin | Rate limit management interface |

---

## Analytics Routes

**Base URL:** `/analytics`
**Role restrictions:** admin, data_manager only

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | view_direct_view | Analytics dashboard |
| `/direct/view/<uuid_str>` | GET | view_upload | View direct upload details |
| `/encounter/view/<uuid_str>` | GET | view_encounter | View encounter file details |
| `/images` | GET | view_direct_image | View direct image details |
| `/encounterFiles` | GET | view_encounterFiles | View encounter files |
| `/image/results` | GET | route_image_results | Image results view |
| `/encounter/results` | GET | route_encounter_results | Encounter results view |
| `/imagesWithoutTasks` | GET | route_images_without_tasks | Images without tasks |
| `/directFilesKpi` | GET | route_directFiles_kpi_display | Direct files KPI display |
| `/encounterFilesKpi` | GET | route_encounterFiles_kpi_display | Encounter files KPI display |
| `/simpleRoutes` | GET | route_routes_simple | Simple routes view |

---

## Image Grading Routes

**Base URL:** `/grading`
**Role restrictions:** Varies by route (typically ophthalmologist, optometrist)

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | index | Grading interface |
| `/<int:task_id>` | GET | grade | Grade specific task |
| `/<int:task_id>/submit` | POST | submit | Submit grading |
| `/<int:task_id>/save` | POST | save | Save grading draft |

---

## File Uploads Routes

### Uploaded ZIPs
**Base URL:** `/uploaded_zips`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | index | List uploaded ZIP files |
| `/<int:zip_id>` | GET | view | View ZIP file details |
| `/<int:zip_id>/status` | GET | status | View ZIP processing status |
| `/<int:zip_id>/tasks` | GET | tasks | View tasks for ZIP file |

### Remedio ZIP Uploads
**Base URL:** `/remedio_zip_uploads`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | index | List Remedio ZIP uploads |
| `/<int:upload_id>` | GET | view | View upload details |

---

## Direct Uploads Routes

**Base URL:** `/direct_uploads`
**Role restrictions:** Multiple roles per route

| Route Path | HTTP Methods | Required Roles | Function | Description |
|------------|--------------|---------------|----------|-------------|
| `/` | GET | - | index | List direct uploads |
| `/upload` | GET | fileUploader, optometrist, data_manager, admin | upload | Upload page |
| `/upload` | POST | fileUploader, optometrist, data_manager, admin | upload | Process upload |
| `/<int:upload_id>` | GET | fileUploader, optometrist, data_manager, admin | view | View upload details |
| `/<int:upload_id>/download` | GET | fileUploader, optometrist, data_manager, admin | download | Download file |
| `/upload/edit_image/<int:upload_id>` | GET | fileUploader, optometrist, data_manager, admin | edit_image | Edit uploaded image |
| `/upload/edit/<int:upload_id>` | GET, POST | fileUploader, optometrist, data_manager, admin | edit_upload | Edit upload metadata |
| `/upload/restore_original/<int:upload_id>` | POST | fileUploader, optometrist, data_manager, admin | restore_original | Restore original image |
| `/upload/save_image/<int:upload_id>` | POST | fileUploader, optometrist, data_manager, admin | save_edited_image | Save edited image |
| `/api/direct/upload/status/<int:job_id>` | GET | fileUploader, optometrist, data_manager, admin | api_upload_status | Get upload status |

---

## Search Routes

**Base URL:** `/search`
**Role restrictions:** admin, data_manager only

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | search_route | Search interface |
| `/images` | GET | search_images_route | Search images with filters |

---

## Media Serving Routes

**Base URL:** `/media`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/image/<uuid_str>` | GET | _imgForGradingByUUID | Serve image for grading |
| `/thumbnail/<uuid_str>` | GET | _thumbnailByUUID | Serve image thumbnail |

---

## Report Serving Routes

**Base URL:** `/reports`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | index | List reports |
| `/<int:report_id>` | GET | view | View report details |
| `/<int:report_id>/download` | GET | download | Download report |

---

## Verification Workflows Routes

### Diabetic Retinopathy Verification
**Base URL:** `/verify_remedio_dr`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | index | Verify DR reports |

### Glaucoma Verification
**Base URL:** `/verify_remedio_glaucoma`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | index | Verify glaucoma reports |

### No DR Verification
**Base URL:** `/verify_remedio_nodr`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | index | Verify no DR reports |

---

## Patient Screenings Routes

**Base URL:** `/screenings`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | index | List screening encounters |
| `/<int:encounter_id>` | GET | view | View screening details |
| `/<int:encounter_id>/status` | GET | status | View screening status |

---

## Job Processing Routes

**Base URL:** `/jobs`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | jobs | List all jobs |
| `/queue` | GET | queue | View job queue |
| `/logs` | GET | logs | View job logs |
| `/cleanup` | GET | cleanup | Cleanup old jobs |
| `/status` | GET | status | Get job status |

---

## Data Audit Routes

**Base URL:** `/audit`
**Role restrictions:** admin, data_manager only

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | index | Audit trail |
| `/logs` | GET | logs | View audit logs |
| `/search` | GET | search | Search audit logs |

---

## Review Routes

**Base URL:** `/review`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | index | Review interface |
| `/discrepancies` | GET | discrepancies | View discrepancies |
| `/<int:task_id>` | GET | review_task | Review specific task |
| `/<int:task_id>/approve` | POST | approve | Approve task |
| `/<int:task_id>/reject` | POST | reject | Reject task |

---

## Dashboard Routes

**Base URL:** `/dashboard`
**Role restrictions:** Multiple roles per route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | dashboard | Main dashboard |
| `/hospitals` | GET | hospital_dashboard | Hospital overview |
| `/hospitals/<int:hospital_id>` | GET | hospital_detail | Hospital details |
| `/images` | GET | image_list | Image list with pagination |

---

## Help & Documentation Routes

### Help Documentation
**Base URL:** `/help`
**No role restrictions** (public routes)

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | index | Help documentation |
| `/faq` | GET | faq | FAQ page |
| `/contact` | GET | contact | Contact support |
| `/api` | GET | api_docs | API documentation |

### Docs System
**Base URL:** `/docs`
**No role restrictions** (public routes)

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | docs | Documentation |
| `/swagger` | GET | swagger_ui | Swagger UI |

---

## API Routes

**Base URL:** `/api`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | api_docs | API documentation |
| `/users` | GET | users | User API endpoints |
| `/uploads` | GET | uploads | Upload API endpoints |
| `/tasks` | GET | tasks | Task API endpoints |
| `/stats` | GET | stats | Statistics API endpoints |
| `/hospitals` | GET | hospitals | Hospital API endpoints |
| `/lab-units` | GET | labUnits | Lab unit API endpoints |
| `/kpis` | GET | kpis | KPI data API endpoints |

---

## Notifications Routes

**Base URL:** `/notifications`
**Role restrictions:** Varies by route

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/` | GET | index | Notification center |
| `/subscribe` | POST | subscribe | Subscribe to notifications |
| `/unsubscribe` | POST | unsubscribe | Unsubscribe from notifications |

---

## Preprocessing Routes

**Base URL:** `/preprocess`
**Role restrictions:** admin only

| Route Path | HTTP Methods | Function | Description |
|------------|--------------|----------|-------------|
| `/anonymize` | POST | anonymize | Anonymize images |

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