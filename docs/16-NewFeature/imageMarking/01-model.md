# 01 - Model (Implemented)

## Storage
`feature_geometry_json` (JSONB) is stored in:
- `grades.feature_geometry_json`
- `intra_rater_grades.feature_geometry_json`

## JSON Shape (v1)
High-level schema stored in JSONB:
```json
{
  "version": 1,
  "grid": {"rows": 8, "cols": 8},
  "items": [
    {
      "feature_id": 123,
      "roi": {
        "type": "box",
        "pixel": [[x1,y1],[x2,y2]],
        "norm": [[x1n,y1n],[x2n,y2n]]
      },
      "polygon": {
        "pixel": [[x,y],...],
        "norm": [[xn,yn],...]
      },
      "mask": {
        "rows": 8,
        "cols": 8,
        "cells": [[r,c], [r,c], ...]
      },
      "export": {
        "bbox_pixel_xyxy": [x1,y1,x2,y2],
        "bbox_norm_xyxy": [x1n,y1n,x2n,y2n],
        "yolo_bbox_xywh": [x_center,y_center,w,h],
        "yolo_polygon_norm": [x1,y1,x2,y2,...]
      },
      "dicom": {
        "tracking_id": "feature-123",
        "tracking_uid": "2.25....",
        "finding_code": {"scheme":"SCT","value":"...","meaning":"..."},
        "finding_site_code": {"scheme":"SCT","value":"...","meaning":"..."}
      }
    }
  ],
  "export_meta": {"dicom_ready": true, "ai_ready": true}
}
```

## Notes
- Saved only on grade submit.
- Preserves history via grade records (no separate audit table required).
- Supports multiple geometries per feature by using multiple `items` with the same `feature_id`.
- Grid precision is configurable (`3..32`) and persisted per item (`mask.rows`, `mask.cols`).

## Migration
Migration already applied:
- `migrations/versions/3c4f2a9b7e21_add_feature_geometry_json_to_grades.py`

## Model Fields
`models.py`:
- `Grade.feature_geometry_json: JSONB`
- `IntraRaterGrade.feature_geometry_json: JSONB`
