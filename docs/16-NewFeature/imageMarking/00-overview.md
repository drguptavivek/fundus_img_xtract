# Image Marking: High-Level Plan

## Goal
Enable graders to mark lesion areas on the grading viewer using a touchpad-friendly workflow. The system should support:
- ROI-only grid masking (32x32 within ROI).
- Polygon boundary for lesion within ROI.
- Add/Subtract paint modes for cell selection.
- Save geometry only on grade submit.
- Store both pixel and normalized coordinates for AI use.

## Scope
- Applies to all role slots: `resident`, `resident2`, `arbitrator`, `review`, `regrade_adj`.
- Applies to `grades` and `intra_rater_grades` only (no regrade_task storage).
- Viewer-only: feature marking lives within the grading editor.

## Deliverables
- Storage: `feature_geometry_json` JSONB in `grades` + `intra_rater_grades`.
- API: read-only GET for existing geometry and image size.
- UI: ROI box + polygon + grid masking with add/subtract modes.
- Validation: enforce geometry bounds and feature matching.

## Dependencies
- Image dimensions from `image_metadata` (width/height).
- Existing grading feature selection logic.

## Non-Goals
- Autosave during drawing (save only on submit).
- Separate annotation subsystem outside grading viewer.
