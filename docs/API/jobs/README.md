# Job API Surface

This folder documents the job status and export-regeneration routes.

## Pages

- [Status](status.md)
- [Export](export.md)

## Notes

- The JSON job payload is built from `job_store.db_get_job_payload()`.
- Export jobs add `upload_type`, export file lists, and dataset-specific fields on top of the base payload.
- A missing Lab Unit never grants global visibility. Generic job reads are
  owner/admin, or exact classical Lab Unit scope when a non-NULL Lab Unit is
  present. Project-specific job families retain their explicit project and
  complete task-lineage authorization.
