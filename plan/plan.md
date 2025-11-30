# Review → Final Consensus Update Plan

## Objective
Allow review submissions on `/review/reviewTaskDetails/<id>` to update the final consensus grade when the task is already in `final` state, while exposing selected features from resident/resident2/arbitrator grades in the UI.

## Agreed Rules
- Update consensus only when `task.state == "final"`.
- Introduce a new consensus method `task_review` (alongside `match` and `adjudication`).
- When a review grade is saved on a final task, overwrite/create consensus with:
  - `final_disease_grading_id` = review grade
  - `method` = `task_review`
  - `decided_by_user_id` = reviewer ID
  - Denormalized fields refreshed from the chosen grading/disease
- Overriding an existing consensus (including arbitrator-based) is allowed; last write wins, but must be logged.
- If the task is not final, just store the review grade and leave consensus untouched.
- Validate the submitted grading is active and belongs to the task’s disease.

## Implementation Steps
1) **DB/migration**
   - Extend `Consensus.method` check constraint/enum to allow `task_review`.
   - Update any constants/labels that enumerate consensus methods.
2) **Backend (review submit)**
   - After persisting the review `Grade`, check `task.state`.
   - If final: fetch/create consensus and overwrite fields per above; log previous method/grade.
   - Else: no consensus change.
   - Ensure active grade validation on POST.
3) **Backend (GET data)**
   - Parse `selected_features_json` for resident, resident2, arbitrator grades and pass to the template.
4) **Frontend**
   - Display “Features noted” under each grader entry (resident/resident2/arbitrator) using parsed features.
   - Add a confirmation modal on review submit when task is `final` and consensus will be overwritten; modal shows current final grade/method and the new review grade that would replace it.
   - Optionally add a badge/label when consensus method is `task_review` so users understand the final grade source.
5) **Tests**
   - Consensus method accepts `task_review`.
   - Review override updates consensus on final tasks; does not when not final.
   - Confirmation modal flow blocks submission until user confirms on final tasks.
   - Feature rendering shows stored selections for resident/resident2/arbitrator.

## Touchpoints to Update for `task_review`
- **Schema/Model**: `models.py` `CheckConstraint` on `Consensus.method`; new migration for constraint.
- **Consensus utils**: `utils/dualGradingConsensusUtils.py` (`create_or_update_consensus`, `get_consensus_method`, logs) to allow the third method.
- **Routes/queries**: `review/route_discrepancy_review.py` selection/output of `consensus_method`.
- **UI templates**: `templates/review/task_detail_review.html`, `templates/review/discrepancy_review.html`, `templates/grading/dual_grading_task.html`, `templates/tasks/task_details.html`, `templates/analytics/task_details.html`, `templates/analytics/results_images.html`, `templates/analytics/results_encounters.html` to display the new method label and badge.
- **Analytics/data frames**: `utils/dataFrameTasks.py`, `analytics/encounterUtils.py`, `analytics/imageTasks.py`, `analytics/utils.py`, materialized view scripts/migrations referencing `consensus_method`. Eg (e.g., migrations/versions/ef304c5f8dd9_create_grading_data_materialized_view.py, c99df7413504_*, cd23f993eaf2_*, cee197bc69ef_*, 6c48c37fc19a_*, 5a49784f68f1_initial_migration.py) include consensus_method columns/indexes; the check constraint is the key blocker.
- **Docs**: dual grading docs and KPI/DF docs that enumerate consensus methods (e.g., `docs/04-Grade/dual_grading_flow.md`, `docs/04-Grade/dual_grading_utils.md`, `docs/11-KPI and DFs/*`).

## Risks / Watchouts
- Downstream analytics/pivots that assume only `match`/`adjudication` must handle `task_review`.
- Overwriting arbitrator decisions is allowed; rely on logging for audit trail (consider storing previous method/grade if needed later).
- Concurrency: last reviewer wins; logs should make this traceable.
- Ensure inactive/foreign disease gradings cannot be submitted via crafted POST.
