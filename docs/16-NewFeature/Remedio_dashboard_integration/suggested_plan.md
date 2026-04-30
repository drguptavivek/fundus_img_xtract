Here’s a clean **API plan** for your camera-first Remidio → VCMS → app workflow.

## API groups

### 1. Auth/session check

```http
GET /api/me
```

Returns current logged-in VCMS user, role, site/team permissions.

---

### 2. Remidio sync

```http
POST /api/remidio/sync
```

Manually pull fresh encounters from Remidio queue.

Optional body:

```json
{
  "site_custom_id": "VC001",
  "max_items": 20
}
```

Returns:

```json
{
  "pulled": 12,
  "created": 10,
  "updated": 2,
  "failed": 0
}
```

---

### 3. Encounter listing

```http
GET /api/encounters
```

Query params:

```text
site_custom_id
date_from
date_to
status
reviewed
q
page
per_page
```

Example:

```http
GET /api/encounters?site_custom_id=VC001&date_from=2026-04-29&reviewed=false
```

Returns encounter cards for app list view.

---

### 4. Encounter detail

```http
GET /api/encounters/{encounter_id}
```

Returns:

```json
{
  "encounter": {},
  "patient": {},
  "images": [],
  "reports": [],
  "remidio_metadata": {},
  "corrections": []
}
```

This is the main endpoint for viewing report/image details.

---

### 5. Correct patient identity

```http
PATCH /api/encounters/{encounter_id}/patient-correction
```

Body:

```json
{
  "corrected_mrn": "PEC-2026-00123",
  "corrected_first_name": "Ramesh",
  "corrected_last_name": "Kumar",
  "reason": "MRN entered incorrectly in camera"
}
```

Rules:

* never overwrite original Remidio MRN/name
* save correction audit trail
* return updated patient block

---

### 6. Mark encounter reviewed

```http
POST /api/encounters/{encounter_id}/review
```

Body:

```json
{
  "review_status": "reviewed",
  "remarks": "MRN corrected and report verified"
}
```

Possible statuses:

```text
new
needs_correction
corrected
reviewed
linked
excluded
```

---

### 7. Images

```http
GET /api/encounters/{encounter_id}/images
```

Returns image list.

```http
GET /api/images/{image_id}
```

Serves/proxies image securely.

```http
GET /api/images/{image_id}/thumbnail
```

Serves thumbnail.

---

### 8. Reports

```http
GET /api/encounters/{encounter_id}/reports
```

Returns available reports.

```http
GET /api/reports/{report_id}
```

Serves report PDF/JSON/HTML depending on type.

---

### 9. Reconciliation by date

```http
POST /api/remidio/reconcile
```

Body:

```json
{
  "site_custom_id": "VC001",
  "start_date": "29-04-2026",
  "end_date": "29-04-2026"
}
```

Uses Remidio “Get Patient Visits By Date” API to detect missed queue items.

---

### 10. Sites

```http
GET /api/remidio/sites
```

Returns Remidio sites mapped to VCMS sites.

---

## Suggested minimum MVP API

Start with only these:

```text
POST  /api/remidio/sync
GET   /api/encounters
GET   /api/encounters/{id}
PATCH /api/encounters/{id}/patient-correction
POST  /api/encounters/{id}/review
GET   /api/images/{id}
GET   /api/reports/{id}
```

That is enough for:

```text
sync → list → view → correct → review → report/image access
```

## Key design rule

```text
Remidio original data is immutable.
VCMS corrections are layered on top.
App always displays corrected values first, with original values available for audit.
```
