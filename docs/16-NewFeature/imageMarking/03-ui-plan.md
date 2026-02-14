# 03 - UI Plan (ROI-Only Grid + Polygon)

## Interaction Design
1. Draw ROI Box (defines grid area).
2. Draw Polygon within ROI (lesion boundary).
3. Add/Subtract grid cells inside ROI.

## Touchpad-Friendly Controls
- Mode buttons: `ROI`, `Polygon`, `Add`, `Subtract`, `Pan`.
- Keyboard shortcuts (no conflicts with existing viewer keys):
  - `U` = ROI mode
  - `I` = Polygon mode
  - `O` = Add mode
  - `P` = Subtract mode
  - `Esc` = Cancel current draw

## Grid
- Fixed 32x32 grid **within ROI**.
- Cell size depends on ROI size (fine for small lesions).

## Overlay
- Toggle overlay visibility on/off.
- Clear/delete per feature.

## Serialization
Per feature:
```json
{
  "version": 1,
  "feature_id": 123,
  "roi": {"type":"box","pixel":[[x1,y1],[x2,y2]],"norm":[[x1n,y1n],[x2n,y2n]]},
  "polygon": {"pixel":[[x,y],...],"norm":[[xn,yn],...]},
  "mask": {"rows":32,"cols":32,"cells":[[r,c],...]},
  "dicom": {
    "tracking_uid": "2.25....",
    "tracking_id": "feature-123",
    "finding_code": {"scheme": "SCT", "value": "...", "meaning": "..."},
    "finding_site_code": {"scheme": "SCT", "value": "...", "meaning": "..."}
  }
}
```

## Linked Grading
- Use `window.linkedGradingData[taskUuid].existingFeatureGeometry` for preload.
- Save to the per-panel hidden field.

## Implementation Reality Check (from 02 API verification)
- GET endpoints and submit wiring exist for dual/intra/regrade.
- Hidden fields for geometry are already present in grading templates.
- Current backend validation still expects `items[].geom.{type,pixel,norm}` shape.
- Planned `roi/polygon/mask` v1 payload is not yet validated server-side.
- Invalid JSON currently degrades to `None` and may be treated as empty geometry.

## Detailed Plan (03)

### 1) Freeze JSON Contract (v1)
- Finalize canonical payload under `items[]`:
  - `feature_id`
  - `roi` (`pixel`, `norm`)
  - `polygon` (`pixel`, `norm`)
  - `mask` (`rows`, `cols`, `cells`)
- Keep `grid.rows=32`, `grid.cols=32` fixed.
- Decide migration strategy for old `geom` payloads:
  - temporary compatibility read support, or
  - hard switch with rejection.
- Include DICOM-friendly fields in each item (`tracking_uid`, coded finding/site)
  so export is deterministic and standards-aligned.

### 1.1) DICOM Export Target (mandatory)
- Primary export format: **DICOM SEG** (binary mask from ROI-local 32x32 cells projected to image space).
- Secondary/companion export: **DICOM SR TID 1500** with:
  - coded findings
  - tracking UID/ID
  - optional planar ROI points (SCOORD) for polygon.
- Result: standard DICOM viewers that support SEG/SR can read markings directly.

### 1.2) AI Export Target (mandatory)
- Use the same stored geometry to export AI-ready annotations:
  - **YOLO detection**: normalized bbox from ROI (`x_center y_center width height`).
  - **YOLO segmentation**: normalized polygon points.
  - **COCO**: segmentation polygons + bbox + area + category mapping.
  - **Mask PNG**: projected binary masks for segmentation pipelines.
- Keep a stable `category_id` mapping per feature/finding for reproducible training exports.
- Export package should include:
  - images
  - annotations (`.txt`/`.json` as format requires)
  - class mapping file (`data.yaml` for YOLO or categories in COCO).

### 2) Backend Validation Upgrade
- Update `utils/feature_geometry.py` to validate v1 payload:
  - required keys and types
  - ROI bounds inside image
  - polygon points inside ROI and image bounds
  - mask cell integrity (`0..31`, unique pairs)
  - `feature_id` must be in selected features
- Treat malformed JSON as a submit error, not silent drop.
- Keep submit-only persistence behavior.

### 3) Server Submit Path Alignment
- Keep geometry validation hooks in:
  - `grading/dual_grading.py`
  - `grading/regrade_tasks.py`
  - `grading/intra_rater.py`
- Preserve existing geometry only when geometry field is absent/blank.
- Reject present-but-invalid payload with user-facing error.

### 4) Frontend Geometry Editor Module
- Add `static/js/feature-geometry-editor.js`:
  - overlay canvas over `.imggr-main`
  - mode state machine: ROI / Polygon / Add / Subtract / Pan
  - ROI box draw/adjust
  - polygon draw/edit
  - ROI-local 32x32 grid and paint interactions
  - serialization/deserialization helpers
- Scope geometry by selected feature (`feature_id`).

### 5) Single-Task Integration
- Integrate editor in:
  - `templates/grading/dual_grading_task.html`
  - `templates/grading/intra_grading_task.html`
  - `templates/grading/regrade_task_detail.html`
- Use existing hidden field `feature_geometry_json`.
- Preload from `window.existingFeatureGeometry`.

### 6) Linked Panel Integration
- Integrate panel-scoped geometry state via `window.linkedGradingData`.
- Read/write panel-specific hidden fields:
  - `feature_geometry_json_<task_uuid>`
- Ensure panel isolation (no cross-panel geometry bleed).

### 7) UX + Keyboard Mapping
- Add toolbar buttons for each mode with active state.
- Keyboard map (no conflicts with viewer keys):
  - `U`: ROI
  - `I`: Polygon
  - `O`: Add
  - `P`: Subtract
  - `Esc`: cancel current draw action
- Add per-feature clear and overlay visibility toggle.

### 8) Test Plan
- Unit tests for validator:
  - valid v1 payload
  - invalid JSON
  - out-of-bounds coordinates
  - polygon outside ROI
  - invalid mask cells
  - feature mismatch
- Route tests for submit handlers ensuring invalid payload rejection.
- JS integration checks for:
  - preload -> edit -> hidden-field serialization
  - linked panel field isolation.
- Export validation checks:
  - DICOM SEG/SR round-trip opens in standard DICOM viewers.
  - YOLO/COCO output passes schema validators and sample training data loaders.
