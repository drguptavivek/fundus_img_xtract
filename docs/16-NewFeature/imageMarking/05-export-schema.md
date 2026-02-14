# 05 - Export Schema (Contract-First)

## Purpose
Define deterministic export mappings from `feature_geometry_json` so exports can be generated without re-annotation.

## Source of Truth
Stored payload in:
- `grades.feature_geometry_json`
- `intra_rater_grades.feature_geometry_json`

Each `items[]` entry is self-contained:
- `feature_id`
- `feature_label`
- `feature_sr_no`
- `roi`
- `polygon`
- `mask`
- `export`
- `dicom`

## Numeric Conventions
- Pixel coordinates: float in DB, exporter may round as target format requires.
- Normalized coordinates: `[0, 1]`.
- Determinism:
  - sort by `feature_id`, then `bbox_norm_xyxy`
  - keep stable `category_id` mapping from feature metadata.

## YOLO Detection Mapping
Output per object line:
`<class_id> <x_center> <y_center> <width> <height>`

Mapping:
- `class_id` -> category map from `feature_id`/`feature_label`
- `x_center,y_center,width,height` -> `items[i].export.yolo_bbox_xywh`

## YOLO Segmentation Mapping
Output per object line:
`<class_id> x1 y1 x2 y2 ...`

Mapping:
- `class_id` -> category map
- polygon points -> `items[i].export.yolo_polygon_norm`

## COCO Mapping
For each annotation:
- `category_id` -> category map
- `bbox` -> convert `items[i].export.bbox_pixel_xyxy` to `[x, y, w, h]`
- `segmentation` -> polygon list from `items[i].polygon.pixel` or normalized variant as configured
- `area` -> polygon area or mask area
- `iscrowd` -> `0` by default

## DICOM SEG Mapping
- Pixel mask source:
  - `items[i].mask` projected into image pixel space within `items[i].roi.pixel`
- Segment metadata:
  - `SegmentNumber` -> deterministic per export order
  - `SegmentLabel` -> `items[i].feature_label`
  - tracking/finding metadata from `items[i].dicom`

## DICOM SR (TID 1500) Mapping
- Tracking:
  - `Tracking Identifier` -> `items[i].dicom.tracking_id`
  - `Tracking UID` -> `items[i].dicom.tracking_uid`
- Finding concept:
  - `finding_code` and `finding_site_code` from `items[i].dicom`
- Spatial coords:
  - polygon from `items[i].polygon.pixel` as SCOORD where supported

## Minimal Required Fields for Export
Required per item:
- `feature_id`
- `feature_label` (fallback: lookup by id)
- `roi.pixel`
- `polygon.pixel`
- `mask.rows/cols/cells`
- `export.yolo_bbox_xywh`
- `export.yolo_polygon_norm`

## Validation Checklist
- [ ] All polygon points inside ROI bounds
- [ ] Mask cells valid and unique within `32x32`
- [ ] Normalized coords in `[0,1]`
- [ ] `feature_id` belongs to selected features
- [ ] Export fields present for each item
