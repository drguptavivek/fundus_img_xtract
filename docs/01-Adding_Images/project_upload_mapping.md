# Project Upload Mapping

The old per-user `UploadMapping` design has been replaced by the current Projects and Upload Profiles system.

Use these current docs instead:

- [Upload Profiles, Projects, And Upload Rules](upload_profiles_projects_rules.md)
- [Upload Profiles API](../API/upload-profiles/README.md)

Do not add new code against `UploadMapping`. New upload governance code should use:

- `upload_profiles/models.py`
- `upload_profiles/service.py`
- `upload_profiles/admin_service.py`
- `admin/upload_profiles.py`
- `api/upload_profiles.py`
