"""Table contracts for the staged project export package (DuckDB).

One place defines every table, column, DuckDB type and description. The
builders in ``tables`` return dict rows keyed by these column names, the writer
creates the DuckDB tables from them, and the ``data_dictionary`` table is
generated from them, so the three cannot drift apart.
"""
from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    description: str


@dataclass(frozen=True)
class Table:
    name: str
    stage: str
    description: str
    columns: tuple[Column, ...]

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)

    def ddl(self) -> str:
        cols = ", ".join(f'"{column.name}" {column.type}' for column in self.columns)
        return f'CREATE TABLE "{self.name}" ({cols})'


C = Column

ENCOUNTERS = Table(
    "encounters",
    "creation",
    "One row per project encounter (classical or set based), as created by upload, Remidio ZIP/API or IIIT-K.",
    (
        C("encounter_uuid", "VARCHAR", "Stable encounter id; join key for every other table."),
        C("project_id", "INTEGER", "Owning project."),
        C("lab_unit_id", "INTEGER", "Lab unit that owns the encounter."),
        C("lab_unit_name", "VARCHAR", "Lab unit name."),
        C("disease", "VARCHAR", "Primary disease on the encounter, if one is set."),
        C("source_path", "VARCHAR", "remidio_api | remidio_zip | iitk_api | other."),
        C("upload_profile_id", "INTEGER", "Upload profile that defined the metadata schema."),
        C("capture_date", "DATE", "Capture date."),
        C("is_set_based", "BOOLEAN", "True for EncounterSet encounters."),
        C("image_count", "INTEGER", "Images exported for this encounter."),
        C("referral_suggestion", "VARCHAR", "Encounter referral suggestion (missing when unset)."),
        C("referral_positive_diseases", "JSON", "Diseases marked referral positive."),
        C("identifiers_included", "BOOLEAN", "False when patient_id/patient_name were withheld."),
        C("patient_id", "VARCHAR", "Patient id; only with an identifiers grant."),
        C("patient_name", "VARCHAR", "Patient name; only with an identifiers grant."),
        C("sex", "VARCHAR", "Patient sex (male | female | other), from the API or the ZIP/PDF OCR import."),
        C("patient_age_years", "INTEGER", "Patient age in years at capture, from the API or the ZIP/PDF OCR import."),
        C("date_of_birth", "VARCHAR", "Date of birth, when the source gave one (API); only with an identifiers grant."),
        C("mrn", "VARCHAR", "Hospital MRN / UHID; only with an identifiers grant."),
        C("remarks", "VARCHAR", "Free-text encounter remarks, exported as entered."),
        C("metadata", "JSON", "Project-defined and source metadata. Identifier keys removed without an identifiers "
                              "grant. May still contain the verification block (see verification tables)."),
    ),
)

IMAGES = Table(
    "images",
    "creation",
    "One row per exported image (encounter files, EncounterSet images, direct uploads). Files are referenced, not included.",
    (
        C("image_uuid", "VARCHAR", "Stable image id; also the media reference."),
        C("kind", "VARCHAR", "encounter_file | encounter_set_image | direct_image_upload."),
        C("encounter_uuid", "VARCHAR", "Parent encounter; null for direct uploads."),
        C("lab_unit_id", "INTEGER", "Lab unit that owns the image."),
        C("spatial_position", "INTEGER", "Order of the image within the encounter."),
        C("ext", "VARCHAR", "File extension."),
        C("source_md5", "VARCHAR", "MD5 of the original file, when recorded."),
        C("created_at", "TIMESTAMPTZ", "Row creation time."),
        C("is_pii", "BOOLEAN", "Image manually flagged as containing PII."),
        C("pii_detected", "BOOLEAN", "The PII scan found identifying content in the image. The row is still exported; "
                                    "only the image file (never part of this package) is sensitive."),
        C("has_edited", "BOOLEAN", "An edited (e.g. anonymised) version exists."),
        C("original_filename", "VARCHAR", "Original file name; only with an identifiers grant."),
        C("width", "INTEGER", "Pixel width of the original."),
        C("height", "INTEGER", "Pixel height of the original."),
        C("format", "VARCHAR", "Image format of the original."),
        C("file_size_bytes", "BIGINT", "File size of the original."),
        C("remarks", "VARCHAR", "Free-text image remarks, exported as entered."),
        C("metadata", "JSON", "Current image metadata. Laterality/focus here may have been corrected during "
                              "verification; original API values are in api_metadata_images."),
    ),
)


API_EXAMS = Table(
    "api_exams", "api_metadata",
    "One row per Remidio API exam routed into an exported encounter (original source data, before verification).",
    (
        C("encounter_uuid", "VARCHAR", "Encounter the exam was routed into."),
        C("remidio_exam_row_id", "INTEGER", "Local mirror row id of the exam."),
        C("remidio_exam_id", "VARCHAR", "Remidio exam id."),
        C("site_name", "VARCHAR", "Remidio site name."),
        C("site_custom_identifier", "VARCHAR", "Remidio site custom identifier used for routing."),
        C("exam_local_id", "VARCHAR", "Remidio exam local id."),
        C("exam_custom_id", "VARCHAR", "Remidio exam custom id."),
        C("exam_state", "VARCHAR", "Remidio exam state (ACTIVE / GRADED)."),
        C("exam_date", "TIMESTAMPTZ", "Exam date."),
        C("device_types", "JSON", "Camera device types on the exam."),
        C("pull_source", "VARCHAR", "How the exam was pulled from the API."),
        C("pulled_at", "TIMESTAMPTZ", "When the exam was last pulled."),
        C("route_binding_id", "INTEGER", "Project route (binding) that imported the exam."),
        C("patient_gender", "VARCHAR", "Gender recorded in Remidio."),
        C("has_ai_report", "BOOLEAN", "Remidio AI report present."),
        C("has_medios_ai_report", "BOOLEAN", "Medios AI report present."),
        C("has_gma_report", "BOOLEAN", "GMA (glaucoma) report present."),
        C("has_doctor_report", "BOOLEAN", "Doctor report present."),
        C("remidio_patient_id", "VARCHAR", "Remidio patient id; only with an identifiers grant."),
        C("patient_mrn", "VARCHAR", "Patient MRN; only with an identifiers grant."),
        C("custom_fields_data", "VARCHAR", "Remidio custom-field text; only with an identifiers grant."),
    ),
)

API_IMAGES = Table(
    "api_images", "api_metadata",
    "One row per Remidio API image of an exported exam, with the API's own laterality/field/quality (original values).",
    (
        C("encounter_uuid", "VARCHAR", "Encounter."),
        C("image_uuid", "VARCHAR", "Local image once downloaded; null if the image was never imported."),
        C("remidio_exam_row_id", "INTEGER", "Local mirror row id of the exam."),
        C("remidio_image_id", "VARCHAR", "Remidio image id."),
        C("device_type", "VARCHAR", "FOP | PRISTINE."),
        C("image_variant", "VARCHAR", "STANDARD | EDITED."),
        C("laterality", "VARCHAR", "LEFT | RIGHT as reported by the API."),
        C("field", "VARCHAR", "MACULA | DISC | OTHER as reported by the API (FOP only)."),
        C("quality", "VARCHAR", "SUFFICIENT | INSUFFICIENT as reported by the API (FOP only)."),
        C("image_segment", "VARCHAR", "API image segment, when given."),
        C("is_cropped", "BOOLEAN", "Image was cropped."),
        C("disc_quality_score", "DOUBLE", "API disc quality score."),
        C("disc_present", "BOOLEAN", "API says the disc is present."),
        C("disc_quality_acceptable", "BOOLEAN", "API says disc quality is acceptable."),
        C("width", "INTEGER", "Width in pixels."),
        C("height", "INTEGER", "Height in pixels."),
        C("edit_operations", "JSON", "Edit operations for EDITED images."),
        C("original_image_ids", "JSON", "Source image ids for EDITED images."),
        C("download_error", "VARCHAR", "Why the image was not imported (e.g. no active route for site/device/date)."),
    ),
)

API_REPORTS = Table(
    "api_reports", "api_metadata",
    "One row per Remidio API report (AI, Medios AI, GMA, doctor) of an exported exam.",
    (
        C("encounter_uuid", "VARCHAR", "Encounter."),
        C("remidio_exam_row_id", "INTEGER", "Local mirror row id of the exam."),
        C("remidio_report_id", "VARCHAR", "Remidio report id."),
        C("report_type", "VARCHAR", "aiReport | mediosAIReport | gmaReport | report | previousReports."),
        C("generated_at", "TIMESTAMPTZ", "Report generation time."),
        C("attachment_uuid", "VARCHAR", "Imported report document (reference only); null if not imported."),
        C("suggested_refer", "BOOLEAN", "Report-level suggested referral."),
        C("confidence", "DOUBLE", "Report-level AI confidence."),
        C("left_eye_cdr", "DOUBLE", "Report-level left cup/disc ratio."),
        C("right_eye_cdr", "DOUBLE", "Report-level right cup/disc ratio."),
        C("dr_confidence", "DOUBLE", "DR result confidence."),
        C("dr_input_sufficient", "BOOLEAN", "DR input sufficient."),
        C("dr_quality_sufficient", "BOOLEAN", "DR image quality sufficient."),
        C("dr_heatmap_images", "INTEGER", "DR heatmap image count."),
        C("dr_suggested_refer", "BOOLEAN", "DR suggested referral."),
        C("amd_confidence", "DOUBLE", "AMD result confidence."),
        C("amd_input_sufficient", "BOOLEAN", "AMD input sufficient."),
        C("amd_quality_sufficient", "BOOLEAN", "AMD image quality sufficient."),
        C("amd_heatmap_images", "INTEGER", "AMD heatmap image count."),
        C("amd_suggested_refer", "BOOLEAN", "AMD suggested referral."),
        C("gma_left_eye_cdr", "DOUBLE", "GMA left cup/disc ratio."),
        C("gma_right_eye_cdr", "DOUBLE", "GMA right cup/disc ratio."),
        C("gma_patient_level_result", "VARCHAR", "GMA patient-level result."),
        C("gma_suggested_refer", "BOOLEAN", "GMA suggested referral."),
        C("refer_required", "BOOLEAN", "Doctor report: referral required."),
        C("left_eye_diagnosis", "JSON", "Doctor report: left eye diagnoses and comments."),
        C("right_eye_diagnosis", "JSON", "Doctor report: right eye diagnoses and comments."),
        C("payload", "JSON", "Full report JSON from the API without identifying ids and file paths."),
    ),
)

IITK_SESSIONS = Table(
    "iitk_sessions", "api_metadata",
    "One row per IIIT-K API session routed into an exported encounter.",
    (
        C("encounter_uuid", "VARCHAR", "Encounter."),
        C("source_status", "VARCHAR", "complete | partial."),
        C("source_image_count", "INTEGER", "Images the source reported."),
        C("local_image_count", "INTEGER", "Images imported locally."),
        C("first_seen_at", "TIMESTAMPTZ", "First time the session was seen."),
        C("last_synced_at", "TIMESTAMPTZ", "Last successful sync."),
        C("last_error", "VARCHAR", "Last sync error."),
        C("source_session_id", "VARCHAR", "Source session id; only with an identifiers grant."),
        C("source_metadata", "JSON", "Session metadata; raw upstream payloads and identifiers only with an identifiers grant."),
    ),
)

VERIFICATION_ENCOUNTERS = Table(
    "verification_encounters", "verification",
    "Verification outcome per encounter (status, who/when, exclusion, observation).",
    (
        C("encounter_uuid", "VARCHAR", "Encounter."),
        C("status", "VARCHAR", "pending | verified | excluded; empty for encounters that never entered verification."),
        C("verified_by", "VARCHAR", "Verifier username."),
        C("verified_at", "TIMESTAMPTZ", "Verification time."),
        C("dr_verified_status", "VARCHAR", "Disease-specific (DR) verification status, legacy."),
        C("dr_verified_by", "VARCHAR", "DR verifier."),
        C("dr_verified_at", "TIMESTAMPTZ", "DR verification time."),
        C("glaucoma_verified_status", "VARCHAR", "Disease-specific (glaucoma) verification status, legacy."),
        C("glaucoma_verified_by", "VARCHAR", "Glaucoma verifier."),
        C("glaucoma_verified_at", "TIMESTAMPTZ", "Glaucoma verification time."),
        C("task_diseases", "JSON", "Diseases the encounter creates grading tasks for (list of names)."),
        C("default_task_disease", "VARCHAR", "The default one of those diseases, when marked."),
        C("excluded", "BOOLEAN", "Encounter excluded from grading and task creation."),
        C("excluded_reason", "VARCHAR", "Exclusion reason, exported as entered."),
        C("excluded_by", "VARCHAR", "Who excluded it."),
        C("excluded_at", "TIMESTAMPTZ", "When it was excluded."),
        C("observation", "VARCHAR", "Verifier observation (includes any quick-add tag text), exported as entered."),
        C("observation_by", "VARCHAR", "Who wrote the observation."),
        C("observation_at", "TIMESTAMPTZ", "When the observation was written."),
        C("referral_suggestion", "VARCHAR", "Encounter referral suggestion (missing when unset)."),
        C("referral_suggestion_updated_at", "TIMESTAMPTZ", "When the referral suggestion last changed."),
        C("referral_positive_diseases", "JSON", "Diseases the verifier marked positive (Positive Diseases checkboxes); "
          "positive diseases drive negative-control task creation."),
        C("verification", "JSON", "Full verification block from the encounter metadata."),
    ),
)

VERIFICATION_IMAGES = Table(
    "verification_images", "verification",
    "Verification outcome per image: effective laterality/centre/gaze next to the original API values, gradability, flags.",
    (
        C("image_uuid", "VARCHAR", "Image."),
        C("encounter_uuid", "VARCHAR", "Parent encounter; null for direct uploads."),
        C("kind", "VARCHAR", "encounter_file | encounter_set_image | direct_image_upload."),
        C("laterality", "VARCHAR", "Effective laterality now (may be verifier-corrected)."),
        C("centering", "VARCHAR", "Effective centre/focus now (may be verifier-corrected)."),
        C("gaze_position", "VARCHAR", "Gaze position, if recorded."),
        C("source_laterality", "VARCHAR", "Original laterality from the Remidio API; null if the image has no API source."),
        C("source_field", "VARCHAR", "Original field (MACULA/DISC/OTHER) from the Remidio API."),
        C("laterality_corrected", "BOOLEAN", "Effective laterality differs from the API value; null when either is unknown."),
        C("is_reviewed", "BOOLEAN", "Image reviewed during verification."),
        C("is_not_gradable", "BOOLEAN", "Image marked not gradable."),
        C("not_gradable_reason", "VARCHAR", "Reason it is not gradable, exported as entered."),
        C("visible_to_grader", "BOOLEAN", "Graders can see the image."),
        C("creates_task", "BOOLEAN", "Image generates grading tasks."),
        C("referral_needed_or_positive", "VARCHAR", "Image-level referral flag (missing when unset)."),
        C("referral_updated_at", "TIMESTAMPTZ", "When the image referral flag last changed."),
        C("observation", "VARCHAR", "Verifier observation (includes any quick-add tag text), exported as entered."),
        C("observation_by", "VARCHAR", "Who wrote the observation."),
        C("direct_verification_status", "VARCHAR", "Direct uploads only: verified | unverified | not_gradable."),
        C("direct_verification_remarks", "VARCHAR", "Direct uploads only: verifier remarks, exported as entered."),
        C("direct_verified_by_user_id", "INTEGER", "Direct uploads only: verifier user id."),
        C("direct_verified_at", "TIMESTAMPTZ", "Direct uploads only: verification time."),
    ),
)

VERIFICATION_HISTORY = Table(
    "verification_history", "verification",
    "Audit trail of encounter verification actions (reopened, reverified, metadata corrected).",
    (
        C("encounter_uuid", "VARCHAR", "Encounter."),
        C("action_type", "VARCHAR", "reopened | reverified | metadata_corrected."),
        C("actor_username", "VARCHAR", "Who acted."),
        C("occurred_at", "TIMESTAMPTZ", "When."),
        C("note", "VARCHAR", "Note, exported as entered."),
        C("before", "JSON", "State before the action."),
        C("after", "JSON", "State after the action."),
    ),
)

OCR_REPORTS = Table(
    "ocr_reports", "ocr",
    "OCR-extracted DR / AMD / glaucoma results per encounter (ZIP/PDF OCR), one row per canonical report.",
    (
        C("encounter_uuid", "VARCHAR", "Encounter."),
        C("source", "VARCHAR", "dr_report | amd_report | glaucoma_report."),
        C("disease", "VARCHAR", "DR | AMD | Glaucoma."),
        C("source_path", "VARCHAR", "How the encounter arrived: remidio_api | remidio_zip | iitk_api | other. "
          "ZIP-upload reports have no report_documents row; their PDF name is in report_file_name (identifiers grant)."),
        C("report_uuid", "VARCHAR", "Report row id."),
        C("document_uuid", "VARCHAR", "Primary report PDF (report_documents.document_uuid) this result was created from, when known."),
        C("result", "VARCHAR", "Extracted result."),
        C("qualitative_result", "VARCHAR", "Extracted qualitative result."),
        C("vcdr_right", "VARCHAR", "Glaucoma: right vertical CDR as extracted."),
        C("vcdr_left", "VARCHAR", "Glaucoma: left vertical CDR as extracted."),
        C("vcdr_right_num", "DOUBLE", "Glaucoma: cleaned numeric right VCDR."),
        C("vcdr_left_num", "DOUBLE", "Glaucoma: cleaned numeric left VCDR."),
        C("report_file_name", "VARCHAR", "Report file name; only with an identifiers grant."),
        C("updated_at", "VARCHAR", "Last update of the cleaned glaucoma row."),
    ),
)

REPORT_DOCUMENTS = Table(
    "report_documents", "ocr",
    "Remidio report PDFs and the API JSON that came with them. Only primary documents: a PDF whose every report was "
    "a duplicate of an earlier one (promotion status not_promoted_duplicate) is left out.",
    (
        C("encounter_uuid", "VARCHAR", "Encounter."),
        C("source_path", "VARCHAR", "How the encounter arrived (remidio_api | remidio_zip | iitk_api | other)."),
        C("document_uuid", "VARCHAR", "Report PDF (attachment) id."),
        C("report_type", "VARCHAR", "Remidio report type."),
        C("report_datetime", "VARCHAR", "report date/time."),
        C("camera_type", "VARCHAR", "camera type."),
        C("source_kind", "VARCHAR", "how it arrived (ZIP, API ...)."),
        C("refer_required", "VARCHAR", "refer required."),
        C("left_eye_diagnosis", "VARCHAR", "left eye diagnosis."),
        C("left_eye_report_comments", "VARCHAR", "left eye comments."),
        C("right_eye_diagnosis", "VARCHAR", "right eye diagnosis."),
        C("right_eye_report_comments", "VARCHAR", "right eye comments."),
        C("ai_confidence", "VARCHAR", "AI confidence."),
        C("ai_input_sufficient", "VARCHAR", "AI input sufficient."),
        C("ai_quality_sufficient", "VARCHAR", "AI quality sufficient."),
        C("ai_suggested_refer", "VARCHAR", "AI suggested referral."),
        C("number_of_heatmap_images", "VARCHAR", "heatmap image count."),
        C("gma_left_eye_cdr", "VARCHAR", "GMA left CDR."),
        C("gma_right_eye_cdr", "VARCHAR", "GMA right CDR."),
        C("gma_suggested_refer", "VARCHAR", "GMA suggested referral."),
        C("gma_patient_level_result", "VARCHAR", "GMA patient-level result."),
        C("report_file_name", "VARCHAR", "Report file name; only with an identifiers grant."),
        C("ocr", "JSON", "Raw OCR block of the PDF, including per-report promotion status."),
    ),
)

AI_RUNS = Table(
    "ai_runs", "remote_ai",
    "One row per remote AI inference run: task-level (single image) and encounter-level (Wadhwani) runs.",
    (
        C("run_scope", "VARCHAR", "task | encounter."),
        C("run_id", "VARCHAR", "Run uuid (encounter runs) or run row id (task runs)."),
        C("encounter_uuid", "VARCHAR", "Encounter, when known."),
        C("task_uuid", "VARCHAR", "Task (task-level runs)."),
        C("image_uuid", "VARCHAR", "Image (task-level runs)."),
        C("ai_model", "VARCHAR", "Model name."),
        C("ai_model_version", "VARCHAR", "Model version."),
        C("source", "VARCHAR", "internal | manual | automatic."),
        C("status", "VARCHAR", "queued | running | success | partial | failed."),
        C("request_id", "VARCHAR", "Provider request id."),
        C("prediction_id", "VARCHAR", "Provider prediction id (task-level runs)."),
        C("report_id", "VARCHAR", "Provider report id (encounter runs)."),
        C("http_status", "INTEGER", "HTTP status of the last provider call."),
        C("error_code", "VARCHAR", "Error code."),
        C("error_message", "VARCHAR", "Error message."),
        C("retry_count", "INTEGER", "Retries (task-level runs)."),
        C("created_at", "TIMESTAMPTZ", "Created."),
        C("started_at", "TIMESTAMPTZ", "Started."),
        C("finished_at", "TIMESTAMPTZ", "Finished."),
        C("request_manifest", "JSON", "What was sent; patient id and file names only with an identifiers grant."),
        C("response", "JSON", "What the provider returned (execute / submit response)."),
        C("config_snapshot", "JSON", "Encounter runs: thresholds and mapping versions in force."),
    ),
)

AI_IMAGE_RESULTS = Table(
    "ai_image_results", "remote_ai",
    "Encounter-level AI: per-image provider output (detected eye, similarity, quality).",
    (
        C("run_id", "VARCHAR", "Encounter run uuid."),
        C("encounter_uuid", "VARCHAR", "Encounter."),
        C("image_uuid", "VARCHAR", "Image."),
        C("remote_key", "VARCHAR", "Provider key for the image."),
        C("submitted_eye", "VARCHAR", "Eye we submitted."),
        C("detected_eye", "VARCHAR", "Eye the model detected."),
        C("laterality_mismatch", "BOOLEAN", "Submitted and detected eye differ."),
        C("is_primary", "BOOLEAN", "Primary image used for the eye."),
        C("similarity_score", "DOUBLE", "Fundus similarity score."),
        C("upload_attempts", "INTEGER", "Upload attempts."),
        C("quality_state", "VARCHAR", "gradable | ungradable | pending | error."),
        C("raw_output", "JSON", "Raw provider output."),
    ),
)

AI_TARGET_RESULTS = Table(
    "ai_target_results", "remote_ai",
    "Encounter-level AI: per-target result (DR, DME ...) mapped to a grade; grade_id joins to grades.",
    (
        C("run_id", "VARCHAR", "Encounter run uuid."),
        C("encounter_uuid", "VARCHAR", "Encounter."),
        C("image_uuid", "VARCHAR", "Image."),
        C("target_key", "VARCHAR", "dr | dme | glaucoma ..."),
        C("raw_label", "VARCHAR", "Provider label."),
        C("raw_score", "DOUBLE", "Provider score."),
        C("mapped_grade", "VARCHAR", "Grade the label was mapped to."),
        C("derivation_reason", "VARCHAR", "provider | similarity_threshold | provider_error."),
        C("grade_id", "INTEGER", "Resulting AI grade; joins to grades.grade_id."),
    ),
)

TASKS = Table(
    "tasks", "tasks",
    "One row per grading task, including tasks with no grades yet.",
    (
        C("task_uuid", "VARCHAR", "Task id."),
        C("encounter_uuid", "VARCHAR", "Encounter; null for direct-image tasks."),
        C("image_uuid", "VARCHAR", "Image for image-level tasks; null for encounter-level tasks."),
        C("target_level", "VARCHAR", "image | encounter; null on legacy tasks."),
        C("disease", "VARCHAR", "Disease being graded."),
        C("task_source", "VARCHAR", "profile_package | profile_package_negative_control | madhunetra_dr_dme | "
                                    "encounter_set_ai_inference | ...; null on legacy tasks."),
        C("is_negative_control", "BOOLEAN", "Negative-control task (task_source ends in _negative_control)."),
        C("state", "VARCHAR", "pending | in progress | final ..."),
        C("lab_unit_id", "INTEGER", "Lab unit."),
        C("package_uuid", "VARCHAR", "Grading package, for package tasks."),
        C("package_code", "VARCHAR", "Grading package code."),
        C("scope_uuid", "VARCHAR", "Grading scope, for scope tasks."),
        C("scope_disease", "VARCHAR", "Scope disease."),
        C("grade_count", "INTEGER", "Grades submitted on this task."),
        C("created_at", "TIMESTAMPTZ", "Created."),
        C("updated_at", "TIMESTAMPTZ", "Updated."),
    ),
)

GRADES = Table(
    "grades", "grades",
    "One row per grade submission by any grader (resident, resident2, arbitrator, regrade_adj, review) or AI.",
    (
        C("grade_id", "INTEGER", "Grade id."),
        C("task_uuid", "VARCHAR", "Task."),
        C("encounter_uuid", "VARCHAR", "Encounter."),
        C("image_uuid", "VARCHAR", "Image for image-level grades."),
        C("disease", "VARCHAR", "Disease graded."),
        C("role_slot", "VARCHAR", "resident | resident2 | arbitrator | regrade_adj | review | ai."),
        C("grade_name", "VARCHAR", "Grade given."),
        C("grade_description", "VARCHAR", "Grade guideline text at the time."),
        C("grader_user_id", "INTEGER", "Grader user id."),
        C("grader_username", "VARCHAR", "Grader username."),
        C("comment", "VARCHAR", "Grader comment, exported as entered."),
        C("selected_features", "JSON", "Selected features."),
        C("feature_geometry", "JSON", "Feature markings."),
        C("annotation_count", "INTEGER", "Annotation instances on the grade."),
        C("time_taken_seconds", "DOUBLE", "Recorded grading time; missing for many grades."),
        C("started_at", "TIMESTAMPTZ", "Grading start (AI grades only)."),
        C("ai_model", "VARCHAR", "AI grades: model name."),
        C("ai_model_version", "VARCHAR", "AI grades: model version."),
        C("ai_probability", "DOUBLE", "AI grades: probability parsed from the comment."),
        C("ai_predicted_class_name", "VARCHAR", "AI grades: predicted class name parsed from the comment."),
        C("ai_review_status", "VARCHAR", "Review of an AI grade: ok | minor_miss | major_miss."),
        C("ai_review_comment", "VARCHAR", "AI review comment, exported as entered."),
        C("ai_reviewed_by_user_id", "INTEGER", "AI reviewer."),
        C("ai_reviewed_at", "TIMESTAMPTZ", "AI review time."),
        C("created_at", "TIMESTAMPTZ", "Created."),
        C("updated_at", "TIMESTAMPTZ", "Updated."),
    ),
)

CONSENSUS = Table(
    "consensus", "grades",
    "Final decision per task (match, adjudication, regrade, task_review).",
    (
        C("task_uuid", "VARCHAR", "Task."),
        C("encounter_uuid", "VARCHAR", "Encounter."),
        C("image_uuid", "VARCHAR", "Image for image-level tasks."),
        C("final_grade", "VARCHAR", "Final grade."),
        C("final_grade_description", "VARCHAR", "Guideline text for the final grade."),
        C("final_disease", "VARCHAR", "Disease of the final grade."),
        C("method", "VARCHAR", "match | adjudication | regrade | task_review."),
        C("scope", "VARCHAR", "image | encounter_set_disease."),
        C("decided_by_user_id", "INTEGER", "Who decided."),
        C("decided_at", "TIMESTAMPTZ", "When."),
    ),
)

DIM_LAB_UNITS = Table(
    "dim_lab_units", "lookup", "Lab units referenced by the package, with their hospital.",
    (
        C("lab_unit_id", "INTEGER", "Lab unit id (encounters.lab_unit_id, images.lab_unit_id, tasks.lab_unit_id)."),
        C("lab_unit_name", "VARCHAR", "Lab unit name."),
        C("hospital_id", "INTEGER", "Hospital id."),
        C("hospital_name", "VARCHAR", "Hospital name."),
    ),
)

DIM_GRADE_LABELS = Table(
    "dim_grade_labels", "lookup", "Every grade label by disease, with its guideline text (join grades on disease + grade_name).",
    (
        C("disease", "VARCHAR", "Disease."),
        C("grade_name", "VARCHAR", "Grade label (impression)."),
        C("display_order", "INTEGER", "Order shown to graders."),
        C("is_active", "BOOLEAN", "Label still offered."),
        C("is_ungradable", "BOOLEAN", "Label means the image cannot be graded."),
        C("guidelines", "VARCHAR", "Grading guideline text."),
    ),
)

DIM_AI_MODELS = Table(
    "dim_ai_models", "lookup", "AI models known to the system (join grades / ai_runs on ai_model + version).",
    (
        C("ai_model", "VARCHAR", "Model name."),
        C("ai_model_version", "VARCHAR", "Model version."),
        C("description", "VARCHAR", "Description."),
    ),
)

GUIDE = Table(
    "guide", "package", "Structure guide: how to read this package. Sections: overview, stages, rules, caveats, example_query.",
    (
        C("section", "VARCHAR", "overview | stages | rules | caveats | example_query."),
        C("title", "VARCHAR", "Topic."),
        C("text", "VARCHAR", "Explanation, or runnable SQL for example_query rows."),
    ),
)

RELATIONSHIPS = Table(
    "relationships", "package", "How tables join. Columns marked soft are matched by value, not a unique key.",
    (
        C("from_table", "VARCHAR", "Child table."),
        C("from_column", "VARCHAR", "Child column."),
        C("to_table", "VARCHAR", "Parent table."),
        C("to_column", "VARCHAR", "Parent column."),
        C("note", "VARCHAR", "Meaning."),
    ),
)

COCO_ANNOTATIONS = Table(
    "coco_annotations", "annotations",
    "One row per annotation instance (COCO-style), image fields repeated on every row for direct ML loading.",
    (
        C("annotation_id", "INTEGER", "Sequential id within this package."),
        C("image_uuid", "VARCHAR", "Annotated image."),
        C("file_name", "VARCHAR", "<image_uuid>.<ext>, the name the image has in a media download."),
        C("width", "INTEGER", "Image width in pixels (bbox/segmentation coordinate space)."),
        C("height", "INTEGER", "Image height in pixels."),
        C("encounter_uuid", "VARCHAR", "Parent encounter."),
        C("category_id", "INTEGER", "Stable id within this package; joins to coco_categories."),
        C("category_name", "VARCHAR", "COCO class name."),
        C("bbox_x", "DOUBLE", "COCO bbox x (pixels); null when the geometry could not be converted."),
        C("bbox_y", "DOUBLE", "COCO bbox y."),
        C("bbox_w", "DOUBLE", "COCO bbox width."),
        C("bbox_h", "DOUBLE", "COCO bbox height."),
        C("area", "DOUBLE", "COCO area."),
        C("iscrowd", "INTEGER", "COCO iscrowd (always 0)."),
        C("segmentation", "JSON", "COCO segmentation: polygon list or RLE; empty list for boxes."),
        C("geometry_type", "VARCHAR", "box | polygon | ellipse | pyramid | mask ..."),
        C("instance_uuid", "VARCHAR", "Annotation instance id."),
        C("source_task_uuid", "VARCHAR", "Task of the grade that carries the annotation; joins to tasks."),
        C("source_grade_id", "INTEGER", "Grade that carries the annotation; joins to grades.grade_id."),
        C("source_role_slot", "VARCHAR", "Role of that grade (filter e.g. adjudicated or human-only labels)."),
        C("source_grader_user_id", "INTEGER", "Grader."),
        C("source_grader_username", "VARCHAR", "Grader username."),
        C("source_grade", "VARCHAR", "Grade name of that grade."),
        C("source_disease", "VARCHAR", "Disease of the task."),
        C("source_graded_at", "TIMESTAMPTZ", "When the grade was last updated."),
        C("warning", "VARCHAR", "Why bbox/segmentation could not be computed, when they could not."),
    ),
)

COCO_CATEGORIES = Table(
    "coco_categories", "annotations", "COCO categories present in this package (stable ids, sorted by name).",
    (
        C("category_id", "INTEGER", "Category id used in coco_annotations."),
        C("category_name", "VARCHAR", "COCO class name."),
        C("annotation_count", "INTEGER", "Annotation instances in this category."),
    ),
)

COCO_IMAGES = Table(
    "coco_images", "annotations",
    "One row per exported image with its COCO dimensions, including images without annotations (negatives).",
    (
        C("image_uuid", "VARCHAR", "Image."),
        C("file_name", "VARCHAR", "<image_uuid>.<ext>."),
        C("width", "INTEGER", "Width in pixels."),
        C("height", "INTEGER", "Height in pixels."),
        C("encounter_uuid", "VARCHAR", "Parent encounter; null for direct uploads."),
        C("task_count", "INTEGER", "Grading tasks on the image."),
        C("annotation_count", "INTEGER", "Annotation instances on the image (all graders)."),
    ),
)

GRADING_SESSIONS = Table(
    "grading_sessions", "grading_timing",
    "Grading workbench sessions touching exported tasks; use with grading_session_targets to estimate time spent.",
    (
        C("session_uuid", "VARCHAR", "Session id."),
        C("grader_username", "VARCHAR", "Grader."),
        C("role_slot", "VARCHAR", "resident | resident2 | arbitrator ..."),
        C("workflow", "VARCHAR", "package | linked | ordinary."),
        C("status", "VARCHAR", "completed | released | expired | invalidated."),
        C("root_task_uuid", "VARCHAR", "Task the session was opened on."),
        C("acquired_at", "TIMESTAMPTZ", "Session start."),
        C("last_heartbeat_at", "TIMESTAMPTZ", "Last sign of activity."),
        C("completed_at", "TIMESTAMPTZ", "Completion time (completed sessions)."),
        C("released_at", "TIMESTAMPTZ", "Release time."),
        C("invalidated_at", "TIMESTAMPTZ", "Invalidation time."),
        C("close_reason", "VARCHAR", "Why the session ended."),
        C("wall_seconds", "DOUBLE", "completed_at - acquired_at for completed sessions; includes any idle time."),
    ),
)

GRADING_SESSION_TARGETS = Table(
    "grading_session_targets", "grading_timing",
    "Per task hold within a session. hold_seconds is an UPPER BOUND on grading time (idle time counts); "
    "only submitted holds are real work.",
    (
        C("session_uuid", "VARCHAR", "Session."),
        C("task_uuid", "VARCHAR", "Task held."),
        C("role_slot", "VARCHAR", "Role the task was held for."),
        C("target_order", "INTEGER", "Position in the session queue."),
        C("target_purpose", "VARCHAR", "editable | evidence."),
        C("acquired_task_state", "VARCHAR", "Task state when taken."),
        C("acquired_at", "TIMESTAMPTZ", "Taken."),
        C("released_at", "TIMESTAMPTZ", "Released."),
        C("release_reason", "VARCHAR", "submitted | user_release | idle_expiry | absolute_expiry | ..."),
        C("hold_seconds", "DOUBLE", "released_at - acquired_at."),
        C("submitted", "BOOLEAN", "Released because the grade was submitted."),
    ),
)

REVIEW_HISTORY = Table(
    "review_history", "discrepancy_review",
    "Before/after record of every discrepancy-review submission on exported tasks (human review, AI feedback).",
    (
        C("request_id", "VARCHAR", "Submission id."),
        C("task_uuid", "VARCHAR", "Task."),
        C("actor_username", "VARCHAR", "Reviewer."),
        C("action_type", "VARCHAR", "human_review | ai_feedback | combined."),
        C("source", "VARCHAR", "Screen that recorded it."),
        C("recorded_at", "TIMESTAMPTZ", "When."),
        C("before", "JSON", "State before the review."),
        C("after", "JSON", "State after the review."),
        C("note", "VARCHAR", "Note, exported as entered."),
    ),
)

REGRADE_TASKS = Table(
    "regrade_tasks", "discrepancy_review", "Regrade assignments created from exported tasks.",
    (
        C("regrade_uuid", "VARCHAR", "Regrade task id."),
        C("source_task_uuid", "VARCHAR", "Task being regraded."),
        C("disease", "VARCHAR", "Disease."),
        C("lab_unit_id", "INTEGER", "Lab unit."),
        C("assigned_to_username", "VARCHAR", "Assigned adjudicator."),
        C("created_by_username", "VARCHAR", "Who created it."),
        C("status", "VARCHAR", "Status."),
        C("notes", "VARCHAR", "Notes, exported as entered."),
        C("created_at", "TIMESTAMPTZ", "Created."),
        C("updated_at", "TIMESTAMPTZ", "Updated."),
    ),
)

REVIEW_CORRECTIONS = Table(
    "review_corrections", "discrepancy_review",
    "Archive of grades replaced by a bulk review correction (the grades before the correction).",
    (
        C("original_grade_id", "INTEGER", "Grade that was replaced."),
        C("task_uuid", "VARCHAR", "Task."),
        C("migration_id", "VARCHAR", "Correction batch."),
        C("script_name", "VARCHAR", "Script that applied it."),
        C("archived_at", "TIMESTAMPTZ", "When it was archived."),
        C("payload", "JSON", "The archived grade."),
    ),
)

INTRA_RATER_BATCHES = Table(
    "intra_rater_batches", "intra_rater",
    "Intra-rater reliability batches: graders re-grade images they graded before, to measure self-agreement.",
    (
        C("batch_id", "INTEGER", "Batch id."),
        C("disease", "VARCHAR", "Disease."),
        C("lab_unit_id", "INTEGER", "Lab unit."),
        C("created_by_username", "VARCHAR", "Who created the batch."),
        C("cooldown_days_override", "INTEGER", "Days that must pass before an image is shown again."),
        C("target_images_per_grader", "INTEGER", "Images per grader in the batch."),
        C("normal_grade", "VARCHAR", "Grade label treated as normal for the selection."),
        C("selection_snapshot", "JSON", "How images were selected."),
        C("remarks", "VARCHAR", "Remarks, exported as entered."),
        C("created_at", "TIMESTAMPTZ", "Created."),
        C("updated_at", "TIMESTAMPTZ", "Updated."),
    ),
)

INTRA_RATER_TASKS = Table(
    "intra_rater_tasks", "intra_rater",
    "One repeat-grading task: the same grader re-grades an image they graded in source_task_uuid.",
    (
        C("intra_task_uuid", "VARCHAR", "Repeat task id."),
        C("batch_id", "INTEGER", "Batch; joins to intra_rater_batches."),
        C("source_task_uuid", "VARCHAR", "Original task; joins to tasks (the original grade is in grades)."),
        C("image_uuid", "VARCHAR", "Image graded again."),
        C("grader_user_id", "INTEGER", "Grader."),
        C("grader_username", "VARCHAR", "Grader username."),
        C("disease", "VARCHAR", "Disease."),
        C("lab_unit_id", "INTEGER", "Lab unit."),
        C("state", "VARCHAR", "Task state."),
        C("created_at", "TIMESTAMPTZ", "Created."),
        C("updated_at", "TIMESTAMPTZ", "Updated."),
    ),
)

INTRA_RATER_GRADES = Table(
    "intra_rater_grades", "intra_rater", "The repeat grade submitted for an intra-rater task.",
    (
        C("intra_grade_id", "INTEGER", "Repeat grade id."),
        C("intra_task_uuid", "VARCHAR", "Repeat task; joins to intra_rater_tasks."),
        C("batch_id", "INTEGER", "Batch."),
        C("grader_user_id", "INTEGER", "Grader."),
        C("grader_username", "VARCHAR", "Grader username."),
        C("disease", "VARCHAR", "Disease graded."),
        C("grade_name", "VARCHAR", "Grade given."),
        C("grade_description", "VARCHAR", "Guideline text at the time."),
        C("comment", "VARCHAR", "Comment, exported as entered."),
        C("selected_features", "JSON", "Selected features."),
        C("feature_geometry", "JSON", "Feature markings."),
        C("time_taken_seconds", "DOUBLE", "Recorded grading time."),
        C("started_at", "TIMESTAMPTZ", "Grading start."),
        C("created_at", "TIMESTAMPTZ", "Created."),
        C("updated_at", "TIMESTAMPTZ", "Updated."),
    ),
)

# Build order == priority order. New stages are appended as they are implemented.
TABLES: tuple[Table, ...] = (
    ENCOUNTERS, IMAGES,
    API_EXAMS, API_IMAGES, API_REPORTS, IITK_SESSIONS,
    VERIFICATION_ENCOUNTERS, VERIFICATION_IMAGES, VERIFICATION_HISTORY,
    OCR_REPORTS, REPORT_DOCUMENTS,
    AI_RUNS, AI_IMAGE_RESULTS, AI_TARGET_RESULTS,
    TASKS, GRADES, CONSENSUS,
    COCO_ANNOTATIONS, COCO_CATEGORIES, COCO_IMAGES,
    GRADING_SESSIONS, GRADING_SESSION_TARGETS,
    REVIEW_HISTORY, REGRADE_TASKS, REVIEW_CORRECTIONS,
    INTRA_RATER_BATCHES, INTRA_RATER_TASKS, INTRA_RATER_GRADES,
    DIM_LAB_UNITS, DIM_GRADE_LABELS, DIM_AI_MODELS,
)

MANIFEST = Table(
    "manifest",
    "package",
    "Key/value facts about this export.",
    (C("key", "VARCHAR", "Fact name."), C("value", "VARCHAR", "Fact value.")),
)

DATA_DICTIONARY = Table(
    "data_dictionary",
    "package",
    "Every table and column in this package.",
    (
        C("table_name", "VARCHAR", "Table."),
        C("stage", "VARCHAR", "Capture stage."),
        C("column_name", "VARCHAR", "Column (empty row = table description)."),
        C("type", "VARCHAR", "DuckDB type."),
        C("description", "VARCHAR", "Meaning."),
    ),
)

PACKAGE_TABLES: tuple[Table, ...] = (MANIFEST, DATA_DICTIONARY, GUIDE, RELATIONSHIPS)
