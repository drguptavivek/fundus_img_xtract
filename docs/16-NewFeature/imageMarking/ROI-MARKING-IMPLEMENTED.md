# ROI Marking - Implemented (Current State)

Last updated: 2026-02-14

## Scope
This document captures what is currently implemented in the grading viewer ROI marking workflow.
It is an implementation snapshot, not the full target design.

## Implemented UX
1. Grader selects grade + features in existing grading UI.
2. Left geometry panel shows selected features and annotation selector.
3. User clicks `+ Add Box` to start a new ROI annotation.
4. User draws ROI on canvas.
5. ROI becomes selectable/editable with canvas interactions.
6. Floating ROI actions appear for selected ROI.

## Implemented Geometry Model
- Stored under `feature_geometry_json`.
- Item-level fields include:
  - `feature_id`
  - `feature_label`
  - `roi.pixel` (box corners)
  - `roi.norm` (normalized corners)
  - `polygon.pixel` and `polygon.norm`
  - `mask.rows`, `mask.cols`, `mask.cells`
  - `dicom.tracking_id`
- For box annotations, polygon is serialized from ROI rectangle to keep geometry self-contained.

## Implemented Interaction Behavior
### Selection and Editing
- Click ROI to select it.
- Click outside ROI deselects.
- Canvas selection syncs to left panel (feature + annotation selector).
- Move: click-hold inside ROI body.
- Resize: drag visible corner handles.

### Locking
- Existing ROIs load as locked by default.
- Unlock is required before move/resize.
- Lock/Unlock is available in floating ROI actions.
- Unlock switches to edit/move mode.
- Lock blocks ROI move/resize but does not disable non-geometry viewer controls.

### Floating ROI Actions
Shown only when a valid ROI is selected:
- Lock/Unlock
- Done (lock + exit edit)
- Duplicate
- Delete

### Multi-ROI / Multi-Feature
- Multiple annotations per feature are supported.
- User can switch feature and annotation from left panel.
- Edit binding is tied to selected annotation (fix applied for second-ROI edit issue).

## Viewer / Canvas Behavior
- Pan and zoom supported in viewer.
- ROI rendering remains aligned during pan/zoom (latest fix path).
- Loupe support integrated with overlay rendering.
- ROI overlay in loupe uses current image transform mapping.

## Keyboard / Control Notes
- `Q` temporary pan mode is supported.
- `L` loupe toggle path is bound via the loupe UI button route to keep state consistent.
- `/` reset path includes loupe reset handling.

## Current Deliberate Simplification
The tool is currently operating in a box-first phase:
- Active ROI workflow centers on `+ Add Box` and canvas edit interactions.
- Advanced ROI geometry tools (full polygon/ellipse pipeline as primary creation path) are deferred.

## Known Gaps vs Planned End-State
- Full production export pipeline (DICOM SEG + AI package export) is not completed yet.
- Finalized annotation toolset sequencing (box/polygon/ellipse as complete suite) is staged.
- Additional validation and contract hardening will continue during subsequent milestones.

## QA Checklist (Current)
- Create ROI via `+ Add Box`.
- Select ROI from canvas and from dropdown; both stay in sync.
- Unlock selected ROI and move/resize.
- Select second ROI, unlock, move/resize (must work).
- Lock ROI and verify edit is blocked.
- Click outside ROI and verify deselection.
- Pan/zoom image and verify ROI stays aligned.
- Toggle loupe and verify ROI overlay visibility/alignment.

## Primary Files
- `static/js/feature-geometry-editor.js`
- `static/js/grading-viewer.js`
- `static/js/feature-geometry-draft.js`
