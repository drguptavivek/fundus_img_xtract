# Pre-Graded Grade Ingestion – Implementation Notes

## Workbook Template
- Format: `.xlsx`, single sheet (default name acceptable).
- Required headers (case-insensitive):
  - `image_name`
  - `resident_grade` (resident load only; optional for faculty run)
  - `resident_remarks`
  - `faculty_grade` (faculty load only; optional for resident run)
  - `faculty_remarks`
- Provide downloadable template with those columns plus instructions that valid grade labels must match the active `DiseaseGrading.impression` list for the chosen disease (e.g., Glaucoma → `Glaucoma`, `Normal`, `Not Gradable`, `Other Retinal`, `Suspect`).
- Treat `"-"` or blank remarks as empty.

## Grade Attribution
- Each upload requires the operator to choose the grader whose ID will be stamped on every imported row.
  - Resident ingest dropdown: users with `resident` or `ophthalmologist` role.
  - Faculty ingest dropdown: users with `ophthalmologist` role (or designated faculty role).
- Persist selection as `grader_user_id` on new/updated `Grade` objects.
- If the workbook mixes graders, operators must split the file and run multiple imports.

## Data Intake & Validation
- Load via `pandas.read_excel`; normalise headers to lower-case snake_case.
- Reject the workbook if:
  - Required columns missing.
  - `image_name` blank or not found among pre-graded uploads (match on `original_filename`, scoped by hospital/lab/disease).
  - Grade value doesn’t map to `DiseaseGrading` for the disease.
- After parsing, compute the unique grade strings present in the workbook. Then open a modal prompting the user to map each unique string to an available grading (dropdown populated from `DiseaseGrading` for the disease). Persist the mapping in lcoalStorage in that session for that disease and user so repeat uploads skip the prompt within that session for that disease for that user.
- Warn (job item entry) when duplicate image rows appear; keep last occurrence for now.

## Job Flow Structure
- New Upload submenu page (`templates/direct_uploads/pregraded_grades.html`) with two sections:
  1. Resident grades upload
  2. Faculty grades upload
- Each submission spawns a `Job` (types: `pregraded_resident_grades`, `pregraded_faculty_grades`) and leverages the existing Jobs status UI.

## Row Processing Logic
- Resolve pre-graded `DirectImageUpload` and corresponding `GradingTask`.
- Resident run:
  - Insert or overwrite `Grade(role_slot='resident')`.
  - Update denormalised fields (disease/grade names, description).
  - Call `update_task_state_based_on_grades`.
- Faculty run:
  - Insert or overwrite `Grade(role_slot='faculty')`.
  - Recalculate task state and invoke `create_or_update_consensus`.
- Record per-row failures in `JobItem` (missing task, invalid grade, etc.) and continue processing.

## Idempotency & Safety
- Allow repeat uploads to fix data; overwriting the existing grade is acceptable while logging the change.
- Mark job `status` as `error` when any row fails; include aggregated message in `job.error`.

## Testing & Logging
- Unit tests for the parser/validator (valid/invalid files, duplicate detection).
- Integration test covering end-to-end resident load → faculty load → consensus update.
- Add structured logging for missing images, grade mismatches, and user attribution.
