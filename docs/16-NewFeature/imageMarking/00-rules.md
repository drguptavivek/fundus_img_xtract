# Image Marking Rules (Implemented)

This document describes the **currently implemented** behavior of the annotation tools in the grading image viewer.

## Quick Rules (At a Glance)

- Every annotation is feature-linked, stored in image-pixel coordinates, and persisted as ROI/polygon/mask payload.
- Lock state is authoritative: locked annotations are view-only; unlock is required for any geometry edits.
- Floating controls are the primary interaction surface for ROI actions (lock, duplicate, convert, flip, delete).
- Convert-to-polygon supports box, ellipse, and cone (pyramid) while preserving editable geometry intent.
- Grid/fill rendering is shape-bounded: ellipse and polygon/cone are clipped to shape; box uses ROI rectangle.
- Visual clutter is minimized: non-box ROI bounds and hover bubbles are suppressed during active/selected edits.

## 1. Core Concepts

- One annotation belongs to one selected feature (`feature_id`, `feature_label`).
- Each annotation has:
  - `geometry_type`: `box` | `ellipse` | `pyramid` | `polygon` | `region`
  - `roi.pixel`: `[[x1, y1], [x2, y2]]` (image-pixel coordinates)
  - optional `polygon.pixel`: list of points in image-pixel coordinates
  - `mask`: grid metadata and selected cells
  - lock state (`_locked` in UI state)
- Coordinates are stored in image pixel space and rendered to canvas via image transform mapping.

## 2. Creation Modes

- `Add Box`: creates rectangular ROI (`geometry_type=box`), then move/resize on canvas.
- `Add Ellipse`: creates ellipse (`geometry_type=ellipse`) with ROI bounding box and ellipse rotation support.
- `Add Pyramid`: creates cone-like triangular polygon inside ROI (`geometry_type=pyramid`).

## 3. Selection + Editing

- Click ROI/shape to select annotation and sync selection with feature/annotation selectors.
- Selected annotation shows floating action buttons.
- For move/resize/rotate operations, annotation must be **unlocked**.
- Clicking outside ROI deselects active ROI.

## 4. Lock Rules

- Lock/Unlock is controlled by floating lock button.
- Locked annotation is view-only for geometry edits:
  - no move
  - no resize
  - no rotate
  - no polygon point drag
  - no add/subtract paint edits
- Existing annotations load in locked state by default.

## 5. Floating Action Buttons (ROI)

Current floating actions:
- Lock/Unlock
- Duplicate
- Convert to Polygon
- Flip H / Flip V (pyramid only)
- Delete

Notes:
- Done/Tick button has been removed (lock is the single finalize/edit-state control).
- Flip actions are shown only for pyramid and only active when unlocked.

## 6. Conversion Rules

`Convert to Polygon` currently supports:
- Box -> polygon (4 corner points)
- Ellipse -> polygon (sampled perimeter points)
- Pyramid -> polygon (preserves existing cone points)

After conversion:
- `geometry_type` becomes `polygon`
- polygon mask is recalculated from polygon
- polygon enters editable polygon flow (when unlocked)

## 7. Shape Interaction Rules

### Box
- ROI rectangle with corner resize handles.
- Move by dragging inside box.

### Ellipse
- Ellipse outline rendered from ROI bounds.
- Rotatable using dedicated rotate handle.
- Resizable from rotated corner handles.

### Pyramid (Cone)
- Triangle polygon within ROI.
- Rotatable via apex-side rotate handle.
- Resize updates both outer ROI and inner cone geometry proportionally.
- Flip H/V mirrors polygon within ROI bounds.

### Polygon
- Click point to move that point.
- Click inside polygon to move whole polygon.
- Polygon points are editable only when unlocked.

## 8. Grid + Fill Rendering

- Box: grid/cells render in ROI rectangle.
- Ellipse: grid/cells are clipped to rotated ellipse area.
- Polygon/Pyramid: grid/cells are clipped to polygon area.
- This avoids visual spill outside actual shape.

## 9. Visual Clutter Rules

- Non-box ROI bounding rectangle is shown only when that annotation is selected.
- Shape outlines remain visible.
- Hover text is suppressed for selected annotation and during active drawing/editing interactions.

## 10. Keyboard / Viewer Interaction Rules

- Annotation editing is canvas-based; pan/zoom is viewer-level.
- Pan lock state is maintained independently of annotation tool visibility.
- Locking/finishing annotation interactions should not break global image navigation state synchronization.

## 11. Serialization Contract (UI state -> payload)

Each item serialized with:
- `feature_id`, `feature_label`
- `geometry_type`
- `roi.pixel`
- `polygon.pixel` (if applicable)
- `mask.rows`, `mask.cols`, `mask.cells`
- `ellipse.rotation_deg` for ellipse geometry

The payload remains image-centric and export-friendly for downstream converters (DICOM overlays/SEG pipelines, YOLO/VOC/COCO conversion utilities, etc.).
