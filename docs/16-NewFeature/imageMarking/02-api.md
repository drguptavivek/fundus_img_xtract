# 02 - API (Implemented)

## GET Geometry (dual grading)
`GET /grading/task/<task_uuid>/feature-geometry?slot=<slot>`

Response:
```json
{
  "success": true,
  "task_uuid": "...",
  "slot": "resident",
  "feature_geometry": { ... },
  "image": { "uuid": "...", "width": 3200, "height": 3200 }
}
```

## GET Geometry (intra-rater)
`GET /grading/intra-task/<task_uuid>/feature-geometry`

Response is the same shape (without slot).

## Save (on submit only)
There is no standalone save API. Geometry is submitted with grade forms:

- Dual grading (single task):
  - Hidden input: `feature_geometry_json`

- Dual grading (linked panels):
  - Hidden input per panel: `feature_geometry_json_<task_uuid>`

- Regrade:
  - Hidden input: `feature_geometry_json`

- Intra-rater:
  - Hidden input: `feature_geometry_json`

### Save Methods (current)
- `grading/dual_grading.py::dual_grading_submit`
- `grading/regrade_tasks.py::regrade_task_submit`
- `grading/intra_rater.py::intra_rater_submit`
- `services/intra_rater_service.py::submit_grade`

## Validation
- Slot validation (`resident|resident2|arbitrator|review|regrade_adj`).
- Eligibility check before returning geometry.
- Image dimensions retrieved from `image_metadata` for bounds validation on submit.
- Geometry must match selected features and stay within ROI bounds.
