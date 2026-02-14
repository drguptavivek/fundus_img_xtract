# 04 - Task Plan (Step-by-Step)

## A. Viewer Integration
1. Add an overlay canvas on top of `.imggr-main`.
2. Implement ROI box drawing and resize.
3. Implement polygon drawing (add points, close, edit).
4. Build ROI grid (configurable `3..32`), render cell boundaries.
5. Add paint modes:
   - Add cells (O)
   - Subtract cells (P)
6. Support drag-to-paint for touchpad.
7. Toggle overlay visibility.
8. Add mode shortcuts:
   - U = ROI
   - I = Polygon
   - O = Add
   - P = Subtract
   - Q (hold) = temporary pan mode

## B. Data Handling
1. On page load, fetch existing geometry using GET API.
2. Restore ROI/polygon/grid from JSON.
3. Write JSON to hidden fields on every change.
4. For linked panels, map data per `task_uuid`.
5. Add local draft cache in `localStorage` per key:
   - `geometry_draft:<user_id>:<task_uuid>:<slot>`
6. On submit success, clear draft cache.
7. If draft and server payload differ on load, prompt restore choice.

## B.1 Prior Annotation Layers
1. Fetch prior grader geometries for adjudicator/review flows.
2. Render resident/resident2 layers as read-only overlays.
3. Provide legend with per-layer color and visibility toggles.

## C. Validation & Constraints
1. Enforce ROI before polygon or grid edits.
2. Polygon must stay inside ROI.
3. Prevent cells outside ROI.
4. Ensure selected features match geometry feature IDs.

## D. QA/Testing
1. Verify single task save/load.
2. Verify linked panel save/load.
3. Verify regrade and intra-rater save/load.
4. Confirm no geometry saved without grade submit.
5. Verify local draft restore/clear lifecycle.
6. Verify prior-layer rendering and layer toggles for adjudicator/review.

## E. Docs
- Update `docs/00-Core/regrading_system.md` if needed.
- Update `docs/08-Workflow/linked_grading_workflow.md` if linked panel changes are user-visible.
