# Discrepancy Review MV v2 Adoption Plan

## Goal
Switch `/review/discrepancy-review`, `/review/discrepancy-export`, and dataset curation flows to use per-disease `mvw_image_listing_<slug>_<disease_id>_v2` views with no runtime joins, while preserving current filters and behavior.

## Prerequisites
- Per-disease MV v2 creation and refresh tasks are running.
- At least one full refresh completed after definition changes.

## Plan
1. **Confirm MV selection logic**
   - Map `disease_id` to MV name via slug rules.
   - Unknown disease ids should error (no legacy fallback).

2. **Replace query source**
   - Update `review/route_discrepancy_review.py` and `review/discrepancy_export.py` to select from the per-disease MV only.
   - Remove joins to `grading_tasks`, `consensus`, `disease_gradings`, and `grades`.

3. **Filter mapping**
   - Map filters to MV v2 fields:
     - `has_consensus` -> `has_consensus`
     - `consensus_method` -> `consensus_type`
     - `resident_compare` -> `resident_vs_resident2`
     - `has_review` -> `has_review`
     - `has_arbitrator` -> `has_arbitrator`
     - `has_ai_grade` -> `has_ai`
     - grade filters -> `resident_grade_name`, `resident2_grade_name`, `arbitrator_grade_name`, `review_grade_name`, `final_grade_name`
     - AI filters -> `ai_models_json`
   - When `has_consensus=no`, clear `consensus_method`, `final_grade`, `has_arbitrator`, `arbitrator_grade`, `has_review`, `review_grade` (backend + UI).

4. **Result shape**
   - Ensure template expects the same fields (task id, state, grades, consensus).
   - Map MV fields to the current `task_data` structure used by templates.

5. **Performance checks**
   - Compare response time for count + data queries.
   - Verify CPU stays stable under filter combinations.

6. **Rollout**
   - Update docs and notify users.

## Validation Checklist
- Counts match between MV v2 and `grading_tasks` for a known disease.
- All filters produce expected results (including consensus=no clearing behavior).
- Exports match on row count and key columns.
- Dataset curation queries match previous results for a known disease.

## Notes
- Per-disease MV v2 rows are task-scoped only.
- New diseases are auto-created daily; refresh runs every 30 minutes.
