# Application Routes

This document lists all the routes in the Fundus Image Manager application, organized by blueprint.

| Route Path | URL For | HTTP Methods | Route File | Roles Required |
|------------|---------|--------------|------------|----------------|
| / | homepage | GET | app.py | - |
| /style_guide | style_guide | GET | app.py | - |
| /healthz | healthz | GET | app.py | - |
| /favicon.ico | _favicon | GET | app.py | - |
| /login | auth.login | GET, POST | auth/routes.py | - |
| /logout | auth.logout | POST, GET | auth/routes.py | login_required |
| /ping | auth.ping | GET | auth/routes.py | login_required |
| /account/profile | account.profile | GET, POST | account/routes.py | login_required |
| /account/change-password | account.change_password_self | GET, POST | account/routes.py | login_required |
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
| /upload_files | uploads.upload_form | GET | uploads/routes.py | admin, fileUploader |
| /upload | uploads.upload_files | POST | uploads/routes.py | admin, fileUploader |
| /uploaded_results | uploaded_results.list_uploaded_results | GET | uploaded_results/routes.py | admin, fileUploader |
| /jobs/ | jobs.list_recent_jobs | GET | jobs/routes.py | admin |
| /jobs/\<job_token\> | jobs.job_status_json | GET | jobs/routes.py | admin |
| /jobs/\<job_token\>/view | jobs.job_status_page | GET | jobs/routes.py | admin |
| /screenings/ | screenings.list_screenings | GET | screenings/routes.py | admin, ophthalmologist |
| /screenings/\<int:encounter_id\> | screenings.screening_detail | GET | screenings/routes.py | admin |
| /reports/dr/\<path:filename\> | reports.serve_dr_pdf | GET | reports/routes.py | admin |
| /reports/glaucoma/\<path:filename\> | reports.serve_glaucoma_pdf | GET | reports/routes.py | admin |
| /reports/dr/by-uuid/\<uuid\> | reports.serve_dr_pdf_by_uuid | GET | reports/routes.py | admin |
| /reports/glaucoma/by-uuid/\<uuid\> | reports.serve_glaucoma_pdf_by_uuid | GET | reports/routes.py | admin |
| /reports/glaucoma_results | reports.glaucoma_results_redirect | GET | reports/routes.py | admin |
| /verify_remedio_dr/list | verify_remedio_dr.verify_dr_list | GET | verify_remedio_dr/routes.py | admin, optometrist, data_manager |
| /verify_remedio_dr/detail/\<int:report_id\> | verify_remedio_dr.verify_dr_detail | GET | verify_remedio_dr/routes.py | admin, optometrist, data_manager |
| /verify_remedio_dr/edit/\<int:report_id\> | verify_remedio_dr.verify_dr_edit | GET, POST | verify_remedio_dr/routes.py | admin, optometrist, data_manager |
| /verify_remedio_dr/edit/\<int:report_id\>/verify | verify_remedio_dr.verify_dr_verify | POST | verify_remedio_dr/routes.py | admin, optometrist |
| /verify_remedio_dr/edit/\<int:report_id\>/unverify | verify_remedio_dr.verify_dr_unverify | POST | verify_remedio_dr/routes.py | admin, optometrist |
| /verify_remedio_dr/edit/\<int:report_id\>/mark_eye | verify_remedio_dr.verify_dr_mark_eye | POST | verify_remedio_dr/routes.py | admin, optometrist, data_manager |
<!-- /dr/results route removed -->
| /verify_remedio_glaucoma/results | verify_remedio_glaucoma.glaucoma_results | GET | verify_remedio_glaucoma/routes.py | admin |
| /verify_remedio_glaucoma/list | verify_remedio_glaucoma.glaucoma_list | GET | verify_remedio_glaucoma/routes.py | admin |
| /verify_remedio_glaucoma/clean | verify_remedio_glaucoma.glaucoma_clean_workflow | GET, POST | verify_remedio_glaucoma/routes.py | admin |
| /verify_remedio_glaucoma/detail/\<int:clean_id\> | verify_remedio_glaucoma.glaucoma_detail | GET | verify_remedio_glaucoma/routes.py | admin |
| /verify_remedio_glaucoma/edit/\<int:clean_id\> | verify_remedio_glaucoma.glaucoma_edit | GET, POST | verify_remedio_glaucoma/routes.py | admin, optometrist, data_manager |
| /verify_remedio_glaucoma/edit/\<int:clean_id\>/verify | verify_remedio_glaucoma.glaucoma_verify | POST | verify_remedio_glaucoma/routes.py | admin, optometrist |
| /verify_remedio_glaucoma/edit/\<int:clean_id\>/unverify | verify_remedio_glaucoma.glaucoma_unverify | POST | verify_remedio_glaucoma/routes.py | admin, optometrist |
| /verify_remedio_glaucoma/edit/\<int:clean_id\>/mark_eye | verify_remedio_glaucoma.glaucoma_mark_eye | POST | verify_remedio_glaucoma/routes.py | admin, optometrist, data_manager |
| /media/img/\<path:filename\> | media.serve_image | GET | media/routes.py | admin |
| /media/file/\<uuid\> | media.serve_file_by_uuid | GET | media/routes.py | admin |
| /media/direct_upload/img_orig/\<int:upload_id\> | media.serve_img_orig | GET | media/routes.py | fileUploader, optometrist, data_manager, admin |
| /media/direct_upload/img_edited/\<int:upload_id\> | media.serve_img_edited | GET | media/routes.py | fileUploader, optometrist, data_manager, admin |
| /media/direct_upload/img/\<uuid_str\> | media.serve_img_by_uuid_preferring_edited | GET | media/routes.py | fileUploader, optometrist, data_manager, admin |
| /audit/missing_capture_date | audit.missing_capture_date | GET | audit/routes.py | admin |
| /grading/ | grading.index | GET, POST | grading/dashboard.py | - |
| /grading/remedio/glaucoma/image/\<uuid\> | grading.remedio_glaucoma_image | GET | grading/remedio_glaucoma.py | optometrist, ophthalmologist, admin |
| /grading/remedio/glaucoma/grade | grading.remedio_glaucoma_grade | POST | grading/remedio_glaucoma.py | optometrist, ophthalmologist, admin |
| /grading/remedio/glaucoma/remove | grading.remedio_glaucoma_remove | POST | grading/remedio_glaucoma.py | optometrist, ophthalmologist, admin |
| /grading/remedio/dr/image/\<uuid\> | grading.remedio_dr_image | GET | grading/remedio_dr.py | optometrist, ophthalmologist, admin |
| /grading/remedio/dr/grade | grading.remedio_dr_grade | POST | grading/remedio_dr.py | optometrist, ophthalmologist, admin |
| /grading/remedio/dr/remove | grading.remedio_dr_remove | POST | grading/remedio_dr.py | optometrist, ophthalmologist, admin |
| /grading/task/\<int:task_id\> | grading.dual_grading_task | GET | grading/dual_grading.py | admin, ophthalmologist, resident |
| /grading/task/submit | grading.dual_grading_submit | POST | grading/dual_grading.py | admin, ophthalmologist, resident |
| /direct/upload | direct_uploads.upload | GET, POST | direct_uploads/upload.py | fileUploader, optometrist, data_manager, admin |
| /direct/upload/processing/\<int:job_id\> | direct_uploads.upload_processing | GET | direct_uploads/upload.py | fileUploader, optometrist, data_manager, admin |
| /direct/dashboard | direct_uploads.dashboard | GET, POST | direct_uploads/dashboard.py | fileUploader, optometrist, data_manager, admin |
| /preprocess/dashboard | preprocess.anonymization_dashboard | GET | preprocess/anonymize_image.py | fileUploader, optometrist, data_manager, admin |
| /preprocess/anonymize_image/\<uuid:uuid\> | preprocess.anonymize_image | GET, POST | preprocess/anonymize_image.py | fileUploader, optometrist, data_manager, admin |
| /preprocess/anonymize_image/\<uuid:uuid\>/restore_original | preprocess.restore_original_anonymized_image | POST | preprocess/anonymize_image.py | fileUploader, optometrist, data_manager, admin |

## Notes

1. **URL For**: This column shows the value used in `url_for()` function in templates and redirects.
2. **Roles Required**: Some routes have role-based access control. The roles are:
   - `admin`: Administrative users
   - `fileUploader`: Users who can upload files
   - `ophthalmologist`: Medical doctors
   - `optometrist`: Eye care professionals
   - `data_manager`: Users who manage data
   - `login_required`: Any authenticated user
3. **HTTP Methods**: All routes specify the HTTP methods they accept.
4. **Route File**: Indicates which file contains the route implementation.
