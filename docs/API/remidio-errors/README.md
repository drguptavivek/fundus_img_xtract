# Remidio project error log API

`GET /api/remidio/projects/{project_id}/errors` returns sanitized route-level and job-item failures from recent project sync jobs. The caller must hold a project-wide Data Manager grant accepted by the Remidio project-sync policy.

The response contains `job_id`, job and route status, date window, site custom identifier, route IDs, remote status code, sanitized error text, and route/download error counts. Provider response bodies and patient data are not exposed.

The HTML view is available at `/admin/remidio/error-log?project_id={project_id}`.
