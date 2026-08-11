# Remidio EncounterSet Attachment OCR API

The EncounterSet verification and browser workspaces use this API to queue PDF OCR and poll its status without navigating away from the page.

## Queue or rerun OCR

`POST /api/remidio/encounter-set-attachments/{attachment_id}/ocr`

JSON request:

```json
{"force": true}
```

`force` requests a rerun even when prior OCR metadata exists. Browser requests require `X-CSRFToken`. Allowed roles are `admin`, `local_admin`, `data_manager`, `fileUploader`, and `optometrist`; attachment access is additionally restricted by upload scope.

## Read OCR status

`GET /api/remidio/encounter-set-attachments/{attachment_id}/ocr`

The response `data` includes `status`, queue/start/completion/failure timestamps, `error`, and any structured `dr_report`, `amd_report`, and `glaucoma_report`. Active states are `queued` and `processing`; terminal states are `completed`, `completed_no_reports_detected`, and `failed`.

The verification UI polls this endpoint while its OCR progress modal is open. Closing the modal after a terminal state reloads the document panel from the server so the latest report fields are displayed.
