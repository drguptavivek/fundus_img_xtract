# ROI Marking - Implemented (Current State)

Last updated: 2026-02-17

## Scope
This document captures what is currently implemented in the grading viewer annotation workflow (ROI + brush).  
It is an implementation snapshot, not the final end-state export pipeline.

## Implemented UX Flow
1. Grader selects grade and features in existing grading UI.
2. Left annotation panel binds to selected feature.
3. Grader creates annotation via `Add Box`, `Add Ellipse`, `Add Pyramid`, or Brush add/subtract.
4. Annotation is selectable from canvas and annotation dropdown.
5. Selected annotation shows floating action controls.
6. Geometry/mask edits persist in `feature_geometry_json` on submit.

## Implemented Geometry Types
- `box`
- `ellipse` (with rotation)
- `pyramid` (cone-like polygon, with rotation + flip)
- `polygon` (including converted from box/ellipse/pyramid)
- `region` (brush-style image mask region)

## Implemented Data Model
Stored under `feature_geometry_json`:
- `version`, `grid`
- `items[]`:
  - `feature_id`
  - `feature_label`
  - `geometry_type`
  - `roi.pixel`, `roi.norm`
  - `polygon.pixel`, `polygon.norm` (as applicable)
  - `mask.rows`, `mask.cols`, `mask.cells`
  - `ellipse.rotation_deg` (ellipse items)
  - `dicom.tracking_id`

Backend storage normalization preserves `geometry_type` and ellipse rotation metadata.

## Selection, Editing, and Locking
- Click annotation on canvas to select and sync feature + annotation selectors.
- Click outside ROI to deselect.
- Existing annotations load locked by default.
- Unlock is required for move/resize/rotate/point editing.
- Lock blocks geometry edits.
- Multi-annotation editing works against currently selected annotation (including revise flow).

## Brush Behavior (Implemented)
- Brush is image-mask based (`region`) and not constrained to a per-ROI drawing box.
- Brush add/subtract works per selected annotation.
- Eraser edits selected annotation (no silent retargeting).
- Older brush-like full-image boxed masks are normalized for safe edit behavior.
- Brush areas are clickable for annotation selection sync.

## Floating Actions (Selected Annotation)
- Lock/Unlock
- Duplicate
- Convert to Polygon (box/ellipse/pyramid)
- Flip H / Flip V (pyramid only)
- Delete

## Annotation Selector UX
- Dropdown shows annotation visibility + type marker + serial:
  - Box `□`, Ellipse `◯`, Pyramid `△`, Polygon `⬠`, Brush `✎`
- Canvas selection updates dropdown selection.

## Viewer/Overlay Behavior
- Pan and zoom supported.
- Overlay alignment fixed for pan/zoom/resize paths.
- Loupe overlay supports annotation rendering.
- Brush region does not render full-image border box.
- Hover/click label bubble renders above pointer and is clamped to canvas bounds.

## Linked Grading Behavior
- Annotation tools are scoped per linked panel.
- Duplicate stacked toolbars are cleaned on context rediscovery/re-init.

## Keyboard/Controls Notes
- `Q` temporary pan mode supported.
- Brush diameter shortcut uses `[` and `]` in brush mode.
- Loupe and reset controls remain in viewer layer.

## Current Known Gaps
- Export pipeline hardening for production DICOM SEG + AI export bundles is still pending.
- Additional API/validation tightening may be needed for new geometry types under high-volume data.

## QA Checklist (Current)
- Create/select/edit for box, ellipse, pyramid.
- Convert box/ellipse/pyramid to polygon and verify point/shape editing.
- Brush add/subtract per selected annotation (`Ann1` vs `Ann2`).
- Lock state enforcement across all geometry types.
- Canvas<->dropdown selection sync.
- Pan/zoom/loupe alignment and no overlay drift.
- Linked panel tool visibility (no duplicate stacked toolbars).

## Primary Files
- `static/js/feature-geometry-editor.js`
- `static/js/grading-viewer.js`
- `utils/feature_geometry.py`
