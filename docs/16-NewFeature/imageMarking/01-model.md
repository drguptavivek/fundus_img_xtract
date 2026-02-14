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
  "grid": {"rows": 32, "cols": 32},
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
        "rows": 32,
        "cols": 32,
        "cells": [[r,c], [r,c], ...]
      }
    }
  ]
}
```

## Notes
- Saved only on grade submit.
- Preserves history via grade records (no separate audit table required).
- Supports multiple geometries per feature by using multiple `items` with the same `feature_id`.

## Migration
Migration already applied:
- `migrations/versions/3c4f2a9b7e21_add_feature_geometry_json_to_grades.py`

## Model Fields
`models.py`:
- `Grade.feature_geometry_json: JSONB`
- `IntraRaterGrade.feature_geometry_json: JSONB`
