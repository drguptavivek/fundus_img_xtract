"""Content of the package's ``guide`` and ``relationships`` tables.

Every example query is executed by the test-suite against a freshly built package, so the guide cannot rot.
"""
from __future__ import annotations

# (section, title, text)
GUIDE: tuple[tuple[str, str, str], ...] = (
    ("overview", "What this file is",
     "A DuckDB database with one table per capture stage of a project's data: encounters and images as created "
     "(by upload, Remidio ZIP/API or IIIT-K), the original API metadata, what verifiers recorded, OCR results, remote "
     "AI results, grading tasks, every grade, and the final decisions. Open it with `duckdb file.duckdb` or "
     "`duckdb.connect('file.duckdb', read_only=True)`. Read `manifest` first, then `data_dictionary` (every column), "
     "`relationships` (joins) and the example queries below."),
    ("overview", "Image and PDF files",
     "No image or PDF file is inside this package. Images are referenced by `image_uuid`; report documents by "
     "attachment uuid. Rows for images the PII scan flagged are present (see `images.pii_detected`); only the file "
     "itself is sensitive."),
    ("stages", "creation: encounters, images",
     "`encounters` (one row per encounter, project/source metadata in `metadata`) and `images` (one row per image, "
     "including direct uploads). `encounter_metadata` and `image_metadata_values` are typed, flattened copies of the "
     "`metadata` JSON (one column per key, nested keys joined with '.'); they exist only when the project has metadata."),
    ("stages", "api_metadata: api_exams, api_images, api_reports, iitk_sessions",
     "The original Remidio API exam, image and report data for API-sourced encounters, and IIIT-K session data. "
     "`api_images.laterality` / `field` / `quality` are the API's own values, before any verification."),
    ("stages", "verification: verification_encounters, verification_images, verification_history",
     "What verifiers recorded: encounter status, exclusion and reason, observations; per image the effective laterality, "
     "centre, gradability and reason, next to the original API values (`source_laterality`, `laterality_corrected`)."),
    ("stages", "ocr: ocr_reports, report_documents",
     "`ocr_reports`: OCR-extracted DR, AMD and glaucoma results (ZIP/PDF OCR). `report_documents`: the primary Remidio report "
     "PDFs with the API JSON (AI and GMA fields, raw OCR block); duplicate PDFs are left out. `ocr_reports.document_uuid` joins to it."),
    ("stages", "remote_ai: ai_runs, ai_image_results, ai_target_results",
     "Remote AI inference. `ai_runs` has task-level (single image) and encounter-level (Wadhwani DR/DME) runs; "
     "encounter runs have per-image results and per-target results whose `grade_id` joins to `grades`."),
    ("stages", "tasks and grades: tasks, grades, consensus",
     "`tasks` (every grading task, also those without grades), `grades` (every submission by every grader, human or AI), "
     "`consensus` (final decision per task)."),
    ("stages", "annotations: coco_annotations, coco_categories, coco_images",
     "One row per annotation instance in COCO terms (bbox, area, segmentation) with the image fields repeated on every row, "
     "so it loads straight into an ML pipeline. `source_*` columns say which grade, grader and role drew it; filter on "
     "`source_role_slot` to choose labels. `coco_images` also lists images with no annotations (negatives). Geometry that "
     "could not be converted keeps its row with `warning` set and empty bbox."),
    ("stages", "grading_timing: grading_sessions, grading_session_targets",
     "Workbench sessions and per-task holds. `hold_seconds` is an upper bound (idle time counts); holds with "
     "`submitted` = true are the closest measure of grading time. Use it to fill in grades whose `time_taken_seconds` is empty."),
    ("stages", "discrepancy_review: review_history, regrade_tasks, review_corrections",
     "Discrepancy-review submissions (before/after), regrade assignments, and the archive of grades replaced by a bulk "
     "review correction. Review and regrade_adj grades themselves are in `grades`."),
    ("stages", "intra_rater: intra_rater_batches, intra_rater_tasks, intra_rater_grades",
     "Self-agreement checks: a grader re-grades an image they graded before. `intra_rater_tasks.source_task_uuid` points to "
     "the original task, whose original grade is in `grades` (same grader); the repeat grade is in `intra_rater_grades`."),
    ("stages", "lookup: dim_lab_units, dim_grade_labels, dim_ai_models",
     "Small tables to resolve ids and labels offline. Fact tables keep readable names too."),
    ("rules", "Identifiers",
     "Without an identifiers grant, patient id/name, original file names, MRN, Remidio patient ids and report file names "
     "are empty, identifier keys are removed from every metadata JSON, and patient/file identifiers are removed from AI "
     "request payloads. `manifest.identifier_lab_unit_ids` lists the labs for which identifiers were included "
     "(empty = none). Free text written by staff (remarks, observations, reasons, comments) is exported as entered."),
    ("rules", "Scope",
     "A project export contains encounters of the project in every lab mapped to it (including labs whose mapping was "
     "later deactivated). A no-project export contains encounters that belong to no project for the chosen hospitals and "
     "lab units. `manifest` records the scope."),
    ("rules", "Joins",
     "`encounter_uuid` and `image_uuid` are the stable keys; `task_uuid` links tasks, grades, consensus and task-level AI "
     "runs; `run_id` links encounter-level AI runs to their image and target results. See `relationships`."),
    ("caveats", "Verification edits",
     "`images.metadata` and `verification_images.laterality` hold the current values, which verifiers may have corrected. "
     "The original API values are in `api_images` (and `verification_images.source_*`). Images without an API source "
     "(ZIP uploads, direct uploads) have no original value."),
    ("caveats", "Grades",
     "`role_slot`: resident, resident2, arbitrator, regrade_adj, review, ai. `time_taken_seconds` is recorded for only part of "
     "the human grades and is empty for regrade_adj and review. `annotation_count` counts annotation instances; "
     "annotation geometry is not part of this package. AI grades carry `ai_model`; an `ai_review_status` is set when a "
     "human reviewed that AI grade."),
    ("caveats", "Tasks",
     "Tasks created before task levels existed have empty `target_level` and `task_source`. `is_negative_control` marks "
     "negative-control tasks, which should usually be excluded from prevalence statistics. A task with no grades is "
     "still listed (state tells you why)."),
    ("caveats", "Empty and text-typed values",
     "Timestamps inside metadata JSON stay text in the typed metadata tables (JSON has no timestamp type). A value that "
     "could not be converted to its column type is empty rather than failing the export."),
    ("caveats", "Point in time",
     "Everything reflects the database at `manifest.exported_at`; the package is a snapshot, not a live view."),
    ("example_query", "Final grade per image with the grader grades",
     "SELECT c.image_uuid, c.final_grade, c.method, string_agg(g.role_slot || ':' || g.grade_name, ', ' ORDER BY g.role_slot) "
     "AS submitted FROM consensus c JOIN grades g USING (task_uuid) WHERE c.image_uuid IS NOT NULL "
     "GROUP BY c.image_uuid, c.final_grade, c.method ORDER BY c.image_uuid LIMIT 20"),
    ("example_query", "Resident disagreements",
     "SELECT t.disease, count(*) AS disagreements FROM grades a JOIN grades b ON a.task_uuid = b.task_uuid "
     "AND a.role_slot = 'resident' AND b.role_slot = 'resident2' AND a.grade_name <> b.grade_name "
     "JOIN tasks t ON t.task_uuid = a.task_uuid GROUP BY t.disease ORDER BY disagreements DESC"),
    ("example_query", "AI grade against the final decision",
     "SELECT g.ai_model, g.grade_name AS ai_grade, c.final_grade, count(*) AS n FROM grades g "
     "JOIN consensus c USING (task_uuid) WHERE g.role_slot = 'ai' GROUP BY ALL ORDER BY n DESC LIMIT 20"),
    ("example_query", "Images whose laterality was corrected during verification",
     "SELECT image_uuid, source_laterality, laterality FROM verification_images WHERE laterality_corrected"),
    ("example_query", "Excluded encounters with reasons",
     "SELECT encounter_uuid, excluded_reason, excluded_by, excluded_at FROM verification_encounters WHERE excluded"),
    ("example_query", "Not-gradable images with reasons",
     "SELECT image_uuid, not_gradable_reason FROM verification_images WHERE is_not_gradable"),
    ("example_query", "Annotation counts per category and labeller role",
     "SELECT category_name, source_role_slot, count(*) AS annotations FROM coco_annotations GROUP BY ALL ORDER BY annotations DESC"),
    ("example_query", "Median submitted hold per role (upper bound of grading time)",
     "SELECT role_slot, count(*) AS holds, median(hold_seconds) AS median_seconds FROM grading_session_targets "
     "WHERE submitted GROUP BY role_slot ORDER BY holds DESC"),
    ("example_query", "Intra-rater agreement per disease (repeat grade equals the grader's original grade)",
     "SELECT t.disease, count(*) AS pairs, avg((r.grade_name = o.grade_name)::INTEGER) AS agreement "
     "FROM intra_rater_grades r JOIN intra_rater_tasks it USING (intra_task_uuid) "
     "JOIN grades o ON o.task_uuid = it.source_task_uuid AND o.grader_user_id = it.grader_user_id "
     "JOIN tasks t ON t.task_uuid = it.source_task_uuid GROUP BY t.disease"),
    ("example_query", "Encounters by source and lab",
     "SELECT e.source_path, l.lab_unit_name, count(*) AS encounters FROM encounters e "
     "LEFT JOIN dim_lab_units l USING (lab_unit_id) GROUP BY ALL ORDER BY encounters DESC"),
    ("example_query", "Tasks by level, source and state (negative controls separate)",
     "SELECT target_level, task_source, is_negative_control, state, count(*) AS tasks FROM tasks GROUP BY ALL ORDER BY tasks DESC"),
)

# (from_table, from_column, to_table, to_column, note)
RELATIONSHIPS: tuple[tuple[str, str, str, str, str], ...] = (
    ("images", "encounter_uuid", "encounters", "encounter_uuid", "Image belongs to an encounter (null for direct uploads)."),
    ("api_exams", "encounter_uuid", "encounters", "encounter_uuid", "Remidio exam routed into the encounter."),
    ("api_images", "encounter_uuid", "encounters", "encounter_uuid", "API image of the encounter's exam."),
    ("api_images", "image_uuid", "images", "image_uuid", "Imported local image (null if never imported)."),
    ("api_reports", "encounter_uuid", "encounters", "encounter_uuid", "API report of the encounter's exam."),
    ("iitk_sessions", "encounter_uuid", "encounters", "encounter_uuid", "IIIT-K session behind the encounter."),
    ("verification_encounters", "encounter_uuid", "encounters", "encounter_uuid", "One row per encounter."),
    ("verification_images", "image_uuid", "images", "image_uuid", "One row per image."),
    ("verification_images", "encounter_uuid", "encounters", "encounter_uuid", "Parent encounter."),
    ("verification_history", "encounter_uuid", "encounters", "encounter_uuid", "Audit trail of the encounter."),
    ("ocr_reports", "encounter_uuid", "encounters", "encounter_uuid", "OCR report rows of the encounter."),
    ("ocr_reports", "document_uuid", "report_documents", "document_uuid", "Primary report PDF the result came from."),
    ("report_documents", "encounter_uuid", "encounters", "encounter_uuid", "Report PDFs of the encounter."),
    ("ai_runs", "encounter_uuid", "encounters", "encounter_uuid", "Encounter the run belongs to."),
    ("ai_runs", "task_uuid", "tasks", "task_uuid", "Task-level runs only."),
    ("ai_runs", "image_uuid", "images", "image_uuid", "Task-level runs only."),
    ("ai_image_results", "run_id", "ai_runs", "run_id", "Encounter-level run that produced it."),
    ("ai_image_results", "image_uuid", "images", "image_uuid", "Image analysed."),
    ("ai_target_results", "run_id", "ai_runs", "run_id", "Encounter-level run that produced it."),
    ("ai_target_results", "grade_id", "grades", "grade_id", "AI grade created from this result."),
    ("tasks", "encounter_uuid", "encounters", "encounter_uuid", "Encounter being graded."),
    ("tasks", "image_uuid", "images", "image_uuid", "Image being graded (image-level tasks)."),
    ("grades", "task_uuid", "tasks", "task_uuid", "Task the grade was submitted for."),
    ("grades", "encounter_uuid", "encounters", "encounter_uuid", "Encounter graded."),
    ("grades", "image_uuid", "images", "image_uuid", "Image graded (image-level tasks)."),
    ("consensus", "task_uuid", "tasks", "task_uuid", "Final decision for the task."),
    ("encounter_metadata", "encounter_uuid", "encounters", "encounter_uuid", "Typed copy of encounters.metadata."),
    ("image_metadata_values", "image_uuid", "images", "image_uuid", "Typed copy of images.metadata."),
    ("coco_annotations", "image_uuid", "images", "image_uuid", "Annotated image."),
    ("coco_annotations", "category_id", "coco_categories", "category_id", "Category."),
    ("coco_annotations", "source_grade_id", "grades", "grade_id", "Grade that carries the annotation."),
    ("coco_annotations", "source_task_uuid", "tasks", "task_uuid", "Task of that grade."),
    ("coco_images", "image_uuid", "images", "image_uuid", "Image (all exported images)."),
    ("grading_session_targets", "session_uuid", "grading_sessions", "session_uuid", "Session of the hold."),
    ("grading_session_targets", "task_uuid", "tasks", "task_uuid", "Task held."),
    ("grading_sessions", "root_task_uuid", "tasks", "task_uuid", "Task the session was opened on."),
    ("review_history", "task_uuid", "tasks", "task_uuid", "Reviewed task."),
    ("regrade_tasks", "source_task_uuid", "tasks", "task_uuid", "Task being regraded."),
    ("review_corrections", "task_uuid", "tasks", "task_uuid", "Task of the replaced grade."),
    ("review_corrections", "original_grade_id", "grades", "grade_id", "Soft join: the replaced grade may no longer exist."),
    ("intra_rater_tasks", "batch_id", "intra_rater_batches", "batch_id", "Batch of the repeat task."),
    ("intra_rater_tasks", "source_task_uuid", "tasks", "task_uuid", "Original task the grader re-graded."),
    ("intra_rater_tasks", "image_uuid", "images", "image_uuid", "Image graded again."),
    ("intra_rater_grades", "intra_task_uuid", "intra_rater_tasks", "intra_task_uuid", "Repeat task of the grade."),
    ("encounters", "lab_unit_id", "dim_lab_units", "lab_unit_id", "Lab unit lookup."),
    ("images", "lab_unit_id", "dim_lab_units", "lab_unit_id", "Lab unit lookup."),
    ("tasks", "lab_unit_id", "dim_lab_units", "lab_unit_id", "Lab unit lookup."),
    ("grades", "grade_name", "dim_grade_labels", "grade_name", "Soft join: also match disease."),
    ("grades", "ai_model", "dim_ai_models", "ai_model", "Soft join: also match ai_model_version."),
)
