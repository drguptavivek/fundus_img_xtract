# Model Performance

This surface documents the model performance page and the threshold explorer API.

## Routes

- `GET /analytics/model-performance`
- `POST /analytics/model-performance/threshold-explorer`

## `GET /analytics/model-performance`

HTML page.

Auth:
- `@roles_required("admin", "local_admin", "data_manager")`

Response:
- `200 OK` HTML rendered from `templates/analytics/model_performance.html`

The page passes a large context including:
- `diseases`
- `ai_models`
- `performance`
- `labels_for_disease`
- `reference_source`
- `final_grade_basis`
- `positive_class`
- `threshold`
- `bootstrap_samples`
- `lab_units`
- `upload_type`
- `cameras`
- `roc_points_json`
- `class_map_json`
- `unresolved_excluded_count`

## `POST /analytics/model-performance/threshold-explorer`

Computes binary metrics over a threshold range.

Auth:
- `@roles_required("admin", "local_admin", "data_manager")`

Request JSON:
```json
{
  "disease_id": 1,
  "ai_model_id": 2,
  "final_grade_basis": "consensus",
  "upload_type": "direct",
  "camera_id": 5,
  "class_map": {"Positive": ["A", "B"]},
  "positive_class": "Positive",
  "lab_unit_id": [1, 2],
  "threshold_min": 0,
  "threshold_max": 1,
  "threshold_delta": 0.1
}
```

Validation errors:
- `400 {"error":"scikit-learn is required for this analysis."}`
- `400 {"error":"Threshold inputs must be numeric."}`
- `400 {"error":"<range validation message>"}`
- `400 {"error":"disease_id and ai_model_id are required."}`
- `400 {"error":"<class map validation message>"}`
- `400 {"error":"Positive class could not be resolved."}`
- `400 {"error":"No cases available for the selected filters."}`

Success `200`:
```json
{
  "thresholds": [
    {
      "threshold": 0.5,
      "sensitivity": 0.8,
      "specificity": 0.7,
      "ppv": 0.75,
      "npv": 0.77,
      "f1": 0.77,
      "accuracy": 0.75,
      "balanced_accuracy": 0.75,
      "kappa": 0.5,
      "weighted_kappa": 0.5,
      "tp": 0,
      "fp": 0,
      "tn": 0,
      "fn": 0,
      "support": 0
    }
  ],
  "auc": 0.0,
  "sample_size": 0,
  "positive_class": "Positive",
  "probabilities_present": true
}
```

## CSRF Rules

- The threshold explorer is a JSON `POST` from browser JS and must include the page CSRF token via `X-CSRFToken`.
- The page route itself is a normal `GET` HTML render.
