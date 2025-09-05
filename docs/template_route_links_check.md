# Template Route Links Check

This document identifies any non-existent route links in the templates by cross-referencing url_for calls with actual routes.

## Findings

After analyzing all url_for calls in the templates and comparing them with the actual routes in the application, no non-existent route links were found. All url_for calls in the templates correspond to actual routes defined in the application.

## Verified Template Links

All of the following url_for calls in templates were verified to correspond to actual routes:

1. account.change_password_self
2. account.profile
3. admin.users_list
4. admin.add_user
5. admin.change_password
6. admin.list_disease_gradings
7. admin.edit_user
8. admin.edit_lookup
9. admin.list_and_create_lookup
10. admin.delete_lookup
10. admin.get_disease_grading_json
11. admin.delete_disease_grading
12. admin.manage_roles
13. admin.malicious_uploads
14. auth.login
15. direct_uploads.dashboard
16. media.serve_img_orig
17. media.serve_img_edited
18. direct_uploads.edit_upload
19. direct_uploads.edit_image
20. grading.direct_image
21. direct_uploads.save_edited_image
22. direct_uploads.restore_original
23. static (for JS/CSS assets)
24. screenings.list_screenings
25. verify_remedio_dr.verify_dr_list
26. verify_remedio_dr.verify_dr_detail
27. verify_remedio_dr.verify_dr_edit
28. reports.serve_dr_pdf_by_uuid
29. verify_remedio_glaucoma.glaucoma_list
30. verify_remedio_glaucoma.glaucoma_results
31. verify_remedio_glaucoma.glaucoma_detail
32. verify_remedio_glaucoma.glaucoma_edit
33. reports.serve_glaucoma_pdf_by_uuid
34. preprocess.anonymization_dashboard
35. jobs.list_recent_jobs
36. jobs.job_status_page
37. homepage
38. uploads.upload_form
39. uploaded_results.list_uploaded_results
40. audit.missing_capture_date
41. dr.dr_results
42. verify_remedio_dr.verify_dr_verify
43. verify_remedio_dr.verify_dr_unverify
44. verify_remedio_glaucoma.glaucoma_verify
45. verify_remedio_glaucoma.glaucoma_unverify

## Conclusion

All template links are valid and correspond to actual routes in the application. No broken or non-existent route links were found.