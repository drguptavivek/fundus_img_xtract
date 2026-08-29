# Thumbnail Management

This page documents the thumbnail maintenance dashboard and its AJAX endpoints.

## Routes

- `GET /admin/thumbnail-management`
- `GET /admin/api/thumbnail_stats`
- `GET /admin/api/maintenance_status`
- `GET /admin/api/thumbnail/health_check`
- `POST /admin/api/thumbnail/manual_maintenance`
- `POST /admin/api/thumbnail/cleanup_orphaned`
- `POST /admin/api/thumbnail/regenerate_missing`
- `POST /admin/api/thumbnail/validate_integrity`
- `POST /admin/api/thumbnail/full_maintenance`

## `GET /admin/thumbnail-management`

HTML dashboard for admins and data managers.

Auth:
- `@roles_required("admin", "data_manager")`

Response:
- `200 OK` HTML rendered from `templates/admin/thumbnail_management.html`

## `GET /admin/api/thumbnail_stats`

Response `200`:
```json
{
  "success": true,
  "stats": {
    "direct_uploads": {
      "total": 0,
      "with_original_thumbnails": 0,
      "with_edited_thumbnails": 0,
      "missing_thumbnails": 0
    },
    "encounter_files": {
      "total": 0,
      "with_thumbnails": 0,
      "missing_thumbnails": 0
    },
    "storage": {
      "estimated_thumbnail_size_mb": 0,
      "potential_space_saving_mb": 0
    }
  }
}
```

## `GET /admin/api/maintenance_status`

Response `200`:
```json
{ "success": true, "status": {} }
```

The `status` object comes from `utils.thumbnail_maintenance_scheduler.get_maintenance_status()` and is rendered directly by the dashboard JS.

## `GET /admin/api/thumbnail/health_check`

Response `200`:
```json
{
  "success": true,
  "health_status": {
    "overall_health": "healthy",
    "issues": [],
    "recommendations": []
  },
  "timestamp": "2026-04-30T12:00:00+00:00"
}
```

Response `500`:
```json
{
  "success": false,
  "error": "Internal health check error. Please check logs.",
  "overall_health": "error"
}
```

## Mutation endpoints

All four maintenance POST endpoints accept JSON and require CSRF through the `X-CSRFToken` header.

### Common request shape

```json
{ "task_type": "all" }
```

Only `manual_maintenance` reads `task_type`; the others read their own JSON fields:
- `POST /admin/api/thumbnail/regenerate_missing` accepts `{"limit": 200}`
- `POST /admin/api/thumbnail/validate_integrity` accepts `{"sample_size": 100}`
- `POST /admin/api/thumbnail/cleanup_orphaned` and `POST /admin/api/thumbnail/full_maintenance` accept an empty JSON body

### Common success shape

```json
{
  "success": true,
  "result": {}
}
```

`manual_maintenance` also returns:
```json
{
  "success": true,
  "task_type": "all",
  "result": {}
}
```

### Common failure shape

```json
{
  "success": false,
  "error": "Internal system error. Please check the logs."
}
```

## CSRF Rules

- The page includes a hidden CSRF field specifically for AJAX.
- All POST calls in the template send `X-CSRFToken` with the hidden token value.
- GET health/status endpoints do not require CSRF.
