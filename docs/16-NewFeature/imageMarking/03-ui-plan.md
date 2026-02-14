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
- Configurable grid **within ROI** with slider range `3x3` to `32x32`.
- Default grid precision: `8x8` (faster marking).
- Cell size depends on ROI size.

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
  "mask": {"rows":8,"cols":8,"cells":[[r,c],...]},
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

## Draft + History Behavior
- Source of truth remains DB (saved on submit).
- Add local draft cache in `localStorage` for crash/reload resilience:
  - key: `geometry_draft:<user_id>:<task_uuid>:<slot>`
  - value: in-progress v1 payload + timestamp
- On load:
  - load server geometry first
  - if a newer local draft exists for same key, prompt user to restore draft or keep server version
- On successful submit:
  - clear draft key
- For adjudicator/review:
  - render prior graders' server-stored geometry as read-only overlay layers
  - do not rely on localStorage for cross-user visibility

## Implementation Reality Check (from 02 API verification)
- GET endpoints and submit wiring exist for dual/intra/regrade.
- Hidden fields for geometry are already present in grading templates.
- Backend validation now enforces strict v1 payload and rejects legacy `geom`.
- Malformed JSON is rejected (not silently dropped).

## Detailed Plan (03)

### 1) Freeze JSON Contract (v1)
- Finalize canonical payload under `items[]`:
  - `feature_id`
  - `roi` (`pixel`, `norm`)
  - `polygon` (`pixel`, `norm`)
  - `mask` (`rows`, `cols`, `cells`)
- Grid precision is configurable with allowed range `3..32`.
- Decide migration strategy for old `geom` payloads:
  - temporary compatibility read support, or
  - hard switch with rejection.
- Include DICOM-friendly fields in each item (`tracking_uid`, coded finding/site)
  so export is deterministic and standards-aligned.

### 1.1) DICOM Export Target (mandatory)
- Primary export format: **DICOM SEG** (binary mask projected from ROI-local `NxN` cells, `N in 3..32`).
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
  - mask cell integrity (index bounds based on selected grid precision, unique pairs)
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
  - ROI-local `3..32` grid and paint interactions with precision slider
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

### 6.1) Prior Annotator Overlay Layers
- Backend should provide prior-slot geometry payloads for adjudicator/review contexts.
- UI renders layered read-only overlays for:
  - resident
  - resident2
  - current slot (editable)
- Each layer has distinct color and visibility toggle in legend.

### 7) UX + Keyboard Mapping
- Add toolbar buttons for each mode with active state.
- Keyboard map (no conflicts with viewer keys):
  - `U`: ROI
  - `I`: Polygon
  - `O`: Add
  - `P`: Subtract
  - `Esc`: cancel current draw action
- Add per-feature clear and overlay visibility toggle.
- Add `Q` hold for temporary pan mode (instead of Space to avoid page scroll side effects).

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
  - local draft restore flow
  - prior-layer visibility toggles in adjudicator/review
- Export validation checks:
  - DICOM SEG/SR round-trip opens in standard DICOM viewers.
  - YOLO/COCO output passes schema validators and sample training data loaders.
