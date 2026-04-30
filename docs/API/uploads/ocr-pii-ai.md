# OCR, PII, and AI Model APIs

These endpoints support OCR review, PII extraction, and AI model introspection/inference triggers.

## `POST /api/ocr/pii/batch`

Runs batch PII/OCR processing for multiple images.

Required JSON:
- `image_uuids` as a list

Common errors:
- image_uuids must be a list

## `GET /api/ocr/pii/boxes/<image_uuid>`

Returns OCR/PII boxes for one image.

## `GET /api/ocr/pii/<image_uuid>`

Returns the OCR/PII result for one image.

## `POST /api/ocr/pii/override`

Overrides the OCR/PII status for one image.

Required JSON:
- `image_uuid`
- `pii_status`

Common errors:
- missing image UUID
- invalid status
- image not found

## `GET /api/ai-models`

Lists AI models available to the caller.

Auth:
- `admin`, `local_admin`, `data_manager`, `optometrist`

## `POST /api/ai-models/wadhwani-glaucoma/tasks/<task_id>/infer`

Triggers Wadhwani glaucoma inference for a task.

Auth:
- `admin`, `local_admin`, `data_manager`

Request body:
- `force` optional boolean

Response:
- success flag
- task/model/inference ids
- prediction metadata
- error code and message when inference fails
