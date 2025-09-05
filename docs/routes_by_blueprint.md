# Application Routes by Blueprint

This document organizes all application routes by their respective blueprints for easier navigation and understanding.

## Core Application Routes (app.py)

| Route Path | URL For | HTTP Methods | Roles Required |
|------------|---------|--------------|----------------|
| / | homepage | GET | - |
| /style_guide | style_guide | GET | - |
| /healthz | healthz | GET | - |
| /favicon.ico | _favicon | GET | - |

## Authentication (auth)

| Route Path | URL For | HTTP Methods | Roles Required |
|------------|---------|--------------|----------------|
| /login | auth.login | GET, POST | - |
| /logout | auth.logout | POST, GET | login_required |
| /ping | auth.ping | GET | login_required |

## Account Management (account)

| Route Path | URL For | HTTP Methods | Roles Required |
|------------|---------|--------------|----------------|
| /account/profile | account.profile | GET, POST | login_required |
| /account/change-password | account.change_password_self | GET, POST | login_required |

## Administration (admin)

| Route Path | URL For | HTTP Methods | Roles Required |
|------------|---------|--------------|----------------|
| /admin/users | admin.users_list | GET | admin |
| /admin/users/new | admin.add_user | GET, POST | admin |
| /admin/users/\<int:user_id\>/edit | admin.edit_user | GET, POST | admin |
| /admin/users/\<int:user_id\>/update | admin.users_update | POST | admin |
| /admin/change-password | admin.change_password | GET, POST | admin |
| /admin/roles | admin.manage_roles | GET, POST | admin |
| /admin/\<string:model_name\> | admin.list_and_create_lookup | GET, POST | admin |
| /admin/\<string:model_name\>/\<int:item_id\>/edit | admin.edit_lookup | GET, POST | admin |
| /admin/\<string:model_name\>/\<int:item_id\>/delete | admin.delete_lookup | POST | admin |
| /admin/disease-gradings | admin.list_disease_gradings | GET, POST | admin |
| /admin/disease-gradings/\<int:grading_id\>/json | admin.get_disease_grading_json | GET | admin |
| /admin/disease-gradings/\<int:grading_id\>/delete | admin.delete_disease_grading | POST | admin |
| /admin/malicious-uploads | admin.malicious_uploads | GET | admin |

## File Uploads (uploads)

| Route Path | URL For | HTTP Methods | Roles Required |
|------------|---------|--------------|----------------|
| /upload_files | uploads.upload_form | GET | admin, fileUploader |
| /upload | uploads.upload_files | POST | admin, fileUploader |

## Uploaded Results (uploaded_results)

| Route Path | URL For | HTTP Methods | Roles Required |
|------------|---------|--------------|----------------|
| /uploaded_results | uploaded_results.list_uploaded_results | GET | admin, fileUploader |

## Job Processing (jobs)

| Route Path | URL For | HTTP Methods | Roles Required |
|------------|---------|--------------|----------------|
| /jobs/ | jobs.list_recent_jobs | GET | admin |
| /jobs/\<job_token\> | jobs.job_status_json | GET | admin |
| /jobs/\<job_token\>/view | jobs.job_status_page | GET | admin |

## Patient Screenings (screenings)

| Route Path | URL For | HTTP Methods | Roles Required |
|------------|---------|--------------|----------------|
| /screenings/ | screenings.list_screenings | GET | admin, ophthalmologist |
| /screenings/\<int:encounter_id\> | screenings.screening_detail | GET | admin |

## Report Serving (reports)

| Route Path | URL For | HTTP Methods | Roles Required |
|------------|---------|--------------|----------------|
| /reports/dr/\<path:filename\> | reports.serve_dr_pdf | GET | admin |
| /reports/glaucoma/\<path:filename\> | reports.serve_glaucoma_pdf | GET | admin |
| /reports/dr/by-uuid/\<uuid\> | reports.serve_dr_pdf_by_uuid | GET | admin |
| /reports/glaucoma/by-uuid/\<uuid\> | reports.serve_glaucoma_pdf_by_uuid | GET | admin |
| /reports/glaucoma_results | reports.glaucoma_results_redirect | GET | admin |

## DR Verification (verify_remedio_dr)

| Route Path | URL For | HTTP Methods | Roles Required |
|------------|---------|--------------|----------------|
| /verify_remedio_dr/list | verify_remedio_dr.verify_dr_list | GET | admin, optometrist, data_manager |
| /verify_remedio_dr/detail/\<int:report_id\> | verify_remedio_dr.verify_dr_detail | GET | admin, optometrist, data_manager |
| /verify_remedio_dr/edit/\<int:report_id\> | verify_remedio_dr.verify_dr_edit | GET, POST | admin, optometrist, data_manager |
| /verify_remedio_dr/edit/\<int:report_id\>/verify | verify_remedio_dr.verify_dr_verify | POST | admin, optometrist |
| /verify_remedio_dr/edit/\<int:report_id\>/unverify | verify_remedio_dr.verify_dr_unverify | POST | admin, optometrist |
| /verify_remedio_dr/edit/\<int:report_id\>/mark_eye | verify_remedio_dr.verify_dr_mark_eye | POST | admin, optometrist, data_manager |

## DR Dashboard (dr)

The DR blueprint has been removed as its functionality was moved to the verify_remedio_dr blueprint.

## Glaucoma Verification (verify_remedio_glaucoma)

| Route Path | URL For | HTTP Methods | Roles Required |
|------------|---------|--------------|----------------|
| /verify_remedio_glaucoma/results | verify_remedio_glaucoma.glaucoma_results | GET | admin |
| /verify_remedio_glaucoma/list | verify_remedio_glaucoma.glaucoma_list | GET | admin |
| /verify_remedio_glaucoma/clean | verify_remedio_glaucoma.glaucoma_clean_workflow | GET, POST | admin |
| /verify_remedio_glaucoma/detail/\<int:clean_id\> | verify_remedio_glaucoma.glaucoma_detail | GET | admin |
| /verify_remedio_glaucoma/edit/\<int:clean_id\> | verify_remedio_glaucoma.glaucoma_edit | GET, POST | admin, optometrist, data_manager |
| /verify_remedio_glaucoma/edit/\<int:clean_id\>/verify | verify_remedio_glaucoma.glaucoma_verify | POST | admin, optometrist |
| /verify_remedio_glaucoma/edit/\<int:clean_id\>/unverify | verify_remedio_glaucoma.glaucoma_unverify | POST | admin, optometrist |
| /verify_remedio_glaucoma/edit/\<int:clean_id\>/mark_eye | verify_remedio_glaucoma.glaucoma_mark_eye | POST | admin, optometrist, data_manager |

## Media Serving (media)

| Route Path | URL For | HTTP Methods | Roles Required |
|------------|---------|--------------|----------------|
| /media/img/\<path:filename\> | media.serve_image | GET | admin |
| /media/file/\<uuid\> | media.serve_file_by_uuid | GET | admin |
| /media/direct_upload/img_orig/\<int:upload_id\> | media.serve_img_orig | GET | contributor, data_manager, admin |
| /media/direct_upload/img_edited/\<int:upload_id\> | media.serve_img_edited | GET | contributor, data_manager, admin |
| /media/direct_upload/img/\<uuid_str\> | media.serve_img_by_uuid_preferring_edited | GET | contributor, data_manager, admin |

## Data Audit (audit)

| Route Path | URL For | HTTP Methods | Roles Required |
|------------|---------|--------------|----------------|
| /audit/missing_capture_date | audit.missing_capture_date | GET | admin |

## Image Grading (grading)

| Route Path | URL For | HTTP Methods | Roles Required |
|------------|---------|--------------|----------------|
| /grading/ | grading.index | GET, POST | - |
| /grading/remedio/glaucoma/image/\<uuid\> | grading.remedio_glaucoma_image | GET | optometrist, ophthalmologist, admin |
| /grading/remedio/glaucoma/grade | grading.remedio_glaucoma_grade | POST | optometrist, ophthalmologist, admin |
| /grading/remedio/glaucoma/remove | grading.remedio_glaucoma_remove | POST | optometrist, ophthalmologist, admin |
| /grading/remedio/dr/image/\<uuid\> | grading.remedio_dr_image | GET | optometrist, ophthalmologist, admin |
| /grading/remedio/dr/grade | grading.remedio_dr_grade | POST | optometrist, ophthalmologist, admin |
| /grading/remedio/dr/remove | grading.remedio_dr_remove | POST | optometrist, ophthalmologist, admin |
| /grading/direct/glaucoma/\<uuid\> | grading.direct_image | GET | optometrist, ophthalmologist, admin |
| /grading/direct/glaucoma/grade | grading.direct_glaucoma_grade | POST | optometrist, ophthalmologist, admin |
| /grading/direct/glaucoma/remove | grading.direct_glaucoma_remove | POST | optometrist, ophthalmologist, admin |
| /grading/direct/disease/\<uuid\>/\<int:disease_id\> | grading.direct_disease_image | GET | optometrist, ophthalmologist, admin |
| /grading/direct/disease/grade | grading.direct_disease_grade | POST | optometrist, ophthalmologist, admin |
| /grading/direct/disease/remove | grading.direct_disease_remove | POST | optometrist, ophthalmologist, admin |

## Direct Uploads (direct_uploads)

| Route Path | URL For | HTTP Methods | Roles Required |
|------------|---------|--------------|----------------|
| /direct/upload | direct_uploads.upload | GET, POST | contributor, data_manager, admin |
| /direct/upload/processing/\<int:job_id\> | direct_uploads.upload_processing | GET | contributor, data_manager, admin |
| /direct/dashboard | direct_uploads.dashboard | GET, POST | contributor, data_manager, admin |

## Image Preprocessing (preprocess)

| Route Path | URL For | HTTP Methods | Roles Required |
|------------|---------|--------------|----------------|
| /preprocess/dashboard | preprocess.anonymization_dashboard | GET | contributor, data_manager, admin |
| /preprocess/anonymize_image/\<uuid:uuid\> | preprocess.anonymize_image | GET, POST | contributor, data_manager, admin |
| /preprocess/anonymize_image/\<uuid:uuid\>/restore_original | preprocess.restore_original_anonymized_image | POST | contributor, data_manager, admin |