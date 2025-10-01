
Endpoint                                         Methods    Rule                                                    
-----------------------------------------------  ---------  --------------------------------------------------------
_favicon                                         GET        /favicon.ico                                            
static                                           GET        /static/<path:filename>                                 
style_guide                                      GET        /style_guide                                            
auth.login                                       GET, POST  /login                                                  
auth.logout                                      GET, POST  /logout                                                 
auth.ping                                        GET        /ping                                                   
homepage                                         GET        /                                                       

account.change_password_self                     GET, POST  /account/change-password                                
account.profile                                  GET, POST  /account/profile                                        

admin.add_user                                   GET, POST  /admin/users/new                                        
admin.change_password                            GET, POST  /admin/change-password                                  
admin.delete_disease_grading                     POST       /admin/disease-gradings/<int:grading_id>/delete         
admin.delete_lookup                              POST       /admin/<string:model_name>/<int:item_id>/delete         
admin.edit_lookup                                GET, POST  /admin/<string:model_name>/<int:item_id>/edit           
admin.edit_user                                  GET, POST  /admin/users/<int:user_id>/edit                         
admin.get_disease_grading_json                   GET        /admin/disease-gradings/<int:grading_id>/json           
admin.list_and_create_lookup                     GET, POST  /admin/<string:model_name>                              
admin.list_disease_gradings                      GET, POST  /admin/disease-gradings                                 
admin.malicious_uploads                          GET        /admin/malicious-uploads                                
admin.manage_roles                               GET, POST  /admin/roles                                            
admin.users_list                                 GET        /admin/users                                            
admin.users_update                               POST       /admin/users/<int:user_id>/update                       


uploads.upload_files                             POST       /upload                                                 
uploads.upload_form                              GET        /upload_files                                           
uploaded_results.list_uploaded_results           GET        /uploaded_results                                       

direct_uploads.upload                            GET, POST  /direct/upload                                          
direct_uploads.upload_processing                 GET        /direct/upload/processing/<int:job_id>                  
direct_uploads.upload_results                    GET        /direct/upload/results/<int:job_id>                     

direct_uploads.api_upload_status                 GET        /api/direct/upload/status/<int:job_id>                  
direct_uploads.dashboard                         GET, POST  /direct/dashboard                                       
direct_uploads.edit_image                        GET        /direct/upload/edit_image/<int:upload_id>               
direct_uploads.edit_upload                       GET, POST  /direct/upload/edit/<int:upload_id>                     
direct_uploads.get_hospital                      GET        /api/hospital/<int:lab_unit_id>                         
direct_uploads.get_lab_units                     GET        /api/lab-units/<int:user_id>                            
direct_uploads.restore_original                  POST       /direct/upload/restore_original/<int:upload_id>         
direct_uploads.save_edited_image                 POST       /direct/upload/save_image/<int:upload_id>               
direct_uploads.static                            GET        /static/direct_uploads/<path:filename>                  
audit.missing_capture_date                       GET        /audit/missing_capture_date                             


<!-- dr.dr_results                                    GET        /dr/results (route removed) -->                                             

grading.index                                    GET, POST  /grading/                                               
grading.dual_grading_submit                      POST       /grading/task/submit                                    
grading.dual_grading_task                        GET        /grading/task/<int:task_id>                             
grading.remedio_dr_grade                         POST       /grading/remedio/dr/grade                               
grading.remedio_dr_image                         GET        /grading/remedio/dr/image/<uuid>                        
grading.remedio_dr_remove                        POST       /grading/remedio/dr/remove                              
grading.remedio_glaucoma_grade                   POST       /grading/remedio/glaucoma/grade                         
grading.remedio_glaucoma_image                   GET        /grading/remedio/glaucoma/image/<uuid>                  
grading.remedio_glaucoma_remove                  POST       /grading/remedio/glaucoma/remove                        

healthz                                          GET        /healthz                                                

jobs.job_status_json                             GET        /jobs/<job_token>                                       
jobs.job_status_page                             GET        /jobs/<job_token>/view                                  
jobs.list_recent_jobs                            GET        /jobs/                                                  

media.serve_file_by_uuid                         GET        /media/file/<uuid>                                      
media.serve_image                                GET        /media/img/<path:filename>                              
media.serve_img_by_uuid_preferring_edited        GET        /media/direct_upload/img/<uuid_str>                     
media.serve_img_edited                           GET        /media/direct_upload/img_edited/<int:upload_id>         
media.serve_img_orig                             GET        /media/direct_upload/img_orig/<int:upload_id>           

preprocess.anonymization_dashboard               GET        /preprocess/dashboard                                   
preprocess.anonymize_image                       GET, POST  /preprocess/anonymize_image/<uuid:uuid>                 
preprocess.restore_original_anonymized_image     POST       /preprocess/anonymize_image/<uuid:uuid>/restore_original
preprocess.static                                GET        /preprocess/static/<path:filename>                      

reports.glaucoma_results_redirect                GET        /reports/glaucoma_results                               
reports.serve_dr_pdf                             GET        /reports/dr/<path:filename>                             
reports.serve_dr_pdf_by_uuid                     GET        /reports/dr/by-uuid/<uuid>                              
reports.serve_glaucoma_pdf                       GET        /reports/glaucoma/<path:filename>                       
reports.serve_glaucoma_pdf_by_uuid               GET        /reports/glaucoma/by-uuid/<uuid>                        

screenings.list_screenings                       GET        /screenings/                                            
screenings.screening_detail                      GET        /screenings/<int:encounter_id>                          



verify_remedio_dr.verify_dr_detail               GET        /verify_remedio_dr/detail/<int:report_id>               
verify_remedio_dr.verify_dr_edit                 GET, POST  /verify_remedio_dr/edit/<int:report_id>                 
verify_remedio_dr.verify_dr_list                 GET        /verify_remedio_dr/list                                 
verify_remedio_dr.verify_dr_mark_eye             POST       /verify_remedio_dr/edit/<int:report_id>/mark_eye        
verify_remedio_dr.verify_dr_unverify             POST       /verify_remedio_dr/edit/<int:report_id>/unverify        
verify_remedio_dr.verify_dr_verify               POST       /verify_remedio_dr/edit/<int:report_id>/verify          

verify_remedio_glaucoma.glaucoma_clean_workflow  GET, POST  /verify_remedio_glaucoma/clean                          
verify_remedio_glaucoma.glaucoma_detail          GET        /verify_remedio_glaucoma/detail/<int:clean_id>          
verify_remedio_glaucoma.glaucoma_edit            GET, POST  /verify_remedio_glaucoma/edit/<int:clean_id>            
verify_remedio_glaucoma.glaucoma_list            GET        /verify_remedio_glaucoma/list                           
verify_remedio_glaucoma.glaucoma_mark_eye        POST       /verify_remedio_glaucoma/edit/<int:clean_id>/mark_eye   
verify_remedio_glaucoma.glaucoma_results         GET        /verify_remedio_glaucoma/results                        
verify_remedio_glaucoma.glaucoma_unverify        POST       /verify_remedio_glaucoma/edit/<int:clean_id>/unverify   
verify_remedio_glaucoma.glaucoma_verify          POST       /verify_remedio_glaucoma/edit/<int:clean_id>/verify   
