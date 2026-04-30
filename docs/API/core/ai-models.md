# AI Models API

These routes expose configured AI models and trigger Wadhwani glaucoma inference.

Auth and CSRF:

- `GET` requires a logged-in session and role checks.
- The inference `POST` route also requires CSRF because it is session-authenticated.

## Routes

| Route | Method | Auth | Request | Response | Status codes |
| --- | --- | --- | --- | --- | --- |
| `/api/ai-models` | `GET` | Session + login + `admin`, `local_admin`, `data_manager`, `optometrist` | None | `{ "models": [...] }` | `403` on role failure. |
| `/api/ai-models/wadhwani-glaucoma/tasks/<int:task_id>/infer` | `POST` | Session + login + `admin`, `local_admin`, `data_manager` + CSRF | JSON `{ "force": bool }` | Result object with `success`, `status`, `message`, `task_id`, `ai_model_id`, `inference_run_id`, `grade_id`, `prediction_id`, `confidence`, `predicted_class`, `predicted_class_name`, `grade_impression`, `reused_existing_grade`, `error_code` | `200` when `status` is `success` or `skipped`. `400` otherwise. |

## `GET /api/ai-models`

Each returned model has:

- `id`
- `name`
- `version`
- `description`
- `display_name`
- `integration_provider`
- `is_wadhwani_glaucoma_linked`

Example:

```json
{
  "models": [
    {
      "id": 1,
      "name": "wadhwani_glaucoma",
      "version": "1.0",
      "description": "Glaucoma inference model",
      "display_name": "wadhwani_glaucoma v1.0",
      "integration_provider": "wadhwani_glaucoma",
      "is_wadhwani_glaucoma_linked": true
    }
  ]
}
```

## `POST /api/ai-models/wadhwani-glaucoma/tasks/<int:task_id>/infer`

Request body:

```json
{ "force": false }
```

Behavior from code:

- `force` defaults to `false`.
- `success` is true for both `success` and `skipped` result statuses.
- `requested_by_user_id` is set from `current_user.id`.
- Non-success/non-skipped results return HTTP `400`.

Example response shape:

```json
{
  "success": true,
  "task_id": 99,
  "ai_model_id": 1,
  "inference_run_id": 1234,
  "grade_id": 55,
  "status": "success",
  "message": "Inference completed",
  "reused_existing_grade": false,
  "prediction_id": 777,
  "confidence": 0.98,
  "predicted_class": "glaucoma",
  "predicted_class_name": "Glaucoma",
  "grade_impression": "Glaucoma suspected",
  "error_code": null
}
```
