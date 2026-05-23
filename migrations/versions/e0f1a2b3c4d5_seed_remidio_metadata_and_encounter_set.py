"""seed remidio metadata fields and encounter set type

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-05-23 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import json
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "e0f1a2b3c4d5"
down_revision: Union[str, Sequence[str], None] = "d9e0f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FIELDS_TABLE = "upload_metadata_field_definitions"
EST_TABLE = "encounter_set_types"
EST_CODE = "remidio_api_standard"


def _opts(*values: tuple[str, str]) -> list[dict[str, str]]:
    return [{"value": value, "label": label} for value, label in values]


REMEDIO_FIELDS: list[dict] = [
    # Patient source/routing fields.
    {"scope": "patient", "key": "remidio_patient_id", "label": "Remidio Patient ID", "field_type": "text"},
    {"scope": "patient", "key": "remidio_site_id", "label": "Remidio Site ID", "field_type": "text"},
    {"scope": "patient", "key": "remidio_site_custom_identifier", "label": "Remidio Site Custom Identifier", "field_type": "text"},
    {
        "scope": "patient",
        "key": "remidio_patient_raw_metadata",
        "label": "Raw Remidio Patient Metadata",
        "field_type": "json",
        "is_pii_default": True,
        "description": "Source-only catch-all patient payload from Remidio.",
    },
    # Encounter source and operational fields.
    {"scope": "encounter", "key": "remidio_exam_id", "label": "Remidio Exam ID", "field_type": "text"},
    {"scope": "encounter", "key": "remidio_exam_local_id", "label": "Remidio Exam Local ID", "field_type": "text"},
    {"scope": "encounter", "key": "exam_code", "label": "Exam Code", "field_type": "text"},
    {
        "scope": "encounter",
        "key": "capture_datetime",
        "label": "Capture Date/Time",
        "field_type": "datetime",
        "required_for_verification_default": True,
    },
    {"scope": "encounter", "key": "remidio_exam_report_datetime", "label": "Remidio Exam Report Date/Time", "field_type": "datetime"},
    {
        "scope": "encounter",
        "key": "device_type",
        "label": "Device Type",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": _opts(("FOP", "FOP"), ("PRISTINE", "PRISTINE"), ("unknown", "Unknown")),
        "required_for_verification_default": True,
    },
    {
        "scope": "encounter",
        "key": "exam_state",
        "label": "Remidio Exam State",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": _opts(("ACTIVE", "ACTIVE"), ("GRADED", "GRADED"), ("unknown", "Unknown")),
    },
    {"scope": "encounter", "key": "medical_history", "label": "Medical History", "field_type": "textarea", "is_pii_default": True},
    {"scope": "encounter", "key": "has_doctor_report", "label": "Doctor Report Present", "field_type": "boolean"},
    {"scope": "encounter", "key": "has_ai_report", "label": "AI Report Present", "field_type": "boolean"},
    {"scope": "encounter", "key": "has_gma_report", "label": "GMA Report Present", "field_type": "boolean"},
    {"scope": "encounter", "key": "has_medios_ai_report", "label": "Medios AI Report Present", "field_type": "boolean"},
    {"scope": "encounter", "key": "clinical_image_count", "label": "Clinical Image Count", "field_type": "integer"},
    {"scope": "encounter", "key": "report_document_count", "label": "Report Document Count", "field_type": "integer"},
    {
        "scope": "encounter",
        "key": "remidio_encounter_raw_metadata",
        "label": "Raw Remidio Encounter Metadata",
        "field_type": "json",
        "is_pii_default": True,
        "description": "Source-only catch-all encounter payload from Remidio.",
    },
    # Image source/common fields.
    {"scope": "image", "key": "remidio_image_id", "label": "Remidio Image ID", "field_type": "text"},
    {"scope": "image", "key": "remidio_image_local_id", "label": "Remidio Image Local ID", "field_type": "text"},
    {"scope": "image", "key": "remidio_image_exam_id", "label": "Remidio Image Exam ID", "field_type": "text"},
    {
        "scope": "image",
        "key": "image_bucket",
        "label": "Remidio Image Bucket",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": _opts(
            ("fopImages", "FOP Images"),
            ("pristineImages", "PRISTINE Images"),
            ("pristine1Point5Images", "PRISTINE 1.5 Images"),
            ("aimImages", "AIM Images"),
            ("pslImages", "PSL Images"),
            ("instaKCImages", "Insta KC Images"),
            ("instaZImages", "Insta Z Images"),
            ("obmImages", "OBM Images"),
            ("otherImages", "Other Images"),
            ("unknown", "Unknown"),
        ),
    },
    {
        "scope": "image",
        "key": "image_variant",
        "label": "Image Variant",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": _opts(("STANDARD", "STANDARD"), ("EDITED", "EDITED"), ("unknown", "Unknown")),
        "required_for_verification_default": True,
    },
    {"scope": "image", "key": "image_capture_datetime", "label": "Image Capture Date/Time", "field_type": "datetime"},
    {
        "scope": "image",
        "key": "image_device_type",
        "label": "Image Device Type",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": _opts(("FOP", "FOP"), ("PRISTINE", "PRISTINE"), ("unknown", "Unknown")),
    },
    {
        "scope": "image",
        "key": "fundus_field",
        "label": "Fundus Field",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": _opts(("MACULA", "MACULA"), ("DISC", "DISC"), ("OTHER", "OTHER"), ("unknown", "Unknown")),
        "visible_to_grader_default": True,
    },
    {
        "scope": "image",
        "key": "image_segment",
        "label": "Image Segment",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": _opts(("POSTERIOR", "POSTERIOR"), ("unknown", "Unknown")),
        "visible_to_grader_default": True,
    },
    {
        "scope": "image",
        "key": "remidio_image_quality",
        "label": "Remidio Image Quality",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": _opts(("SUFFICIENT", "SUFFICIENT"), ("INSUFFICIENT", "INSUFFICIENT"), ("unknown", "Unknown")),
    },
    {"scope": "image", "key": "is_cropped", "label": "Cropped", "field_type": "boolean"},
    {"scope": "image", "key": "is_montage", "label": "Montage", "field_type": "boolean", "visible_to_grader_default": True},
    {"scope": "image", "key": "edit_operations", "label": "Edit Operations", "field_type": "json"},
    {"scope": "image", "key": "original_remidio_image_ids", "label": "Original Remidio Image IDs", "field_type": "json"},
    {"scope": "image", "key": "width_px", "label": "Width Pixels", "field_type": "integer"},
    {"scope": "image", "key": "height_px", "label": "Height Pixels", "field_type": "integer"},
    {"scope": "image", "key": "source_path_present", "label": "Source Path Present", "field_type": "boolean"},
    {"scope": "image", "key": "thumbnail_path_present", "label": "Thumbnail Path Present", "field_type": "boolean"},
    {"scope": "image", "key": "disc_present", "label": "Disc Present", "field_type": "boolean"},
    {"scope": "image", "key": "disc_quality_acceptable", "label": "Disc Quality Acceptable", "field_type": "boolean"},
    {"scope": "image", "key": "disc_quality_score", "label": "Disc Quality Score", "field_type": "decimal"},
    {"scope": "image", "key": "disc_roi_x", "label": "Disc ROI X", "field_type": "decimal"},
    {"scope": "image", "key": "disc_roi_y", "label": "Disc ROI Y", "field_type": "decimal"},
    {
        "scope": "image",
        "key": "remidio_image_exif_metadata",
        "label": "Remidio Image EXIF Metadata",
        "field_type": "json",
        "is_pii_default": True,
    },
    {
        "scope": "image",
        "key": "remidio_image_raw_metadata",
        "label": "Raw Remidio Image Metadata",
        "field_type": "json",
        "is_pii_default": True,
        "description": "Source-only catch-all image payload from Remidio.",
    },
    # Report/document fields.
    {"scope": "document", "key": "remidio_report_id", "label": "Remidio Report ID", "field_type": "text"},
    {
        "scope": "document",
        "key": "remidio_report_type",
        "label": "Remidio Report Type",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": _opts(
            ("doctor_report", "Doctor Report"),
            ("aiReport", "AI Report"),
            ("gmaReport", "GMA Report"),
            ("mediosAIReport", "Medios AI Report"),
            ("unknown", "Unknown"),
        ),
    },
    {"scope": "document", "key": "remidio_report_exam_id", "label": "Remidio Report Exam ID", "field_type": "text"},
    {"scope": "document", "key": "remidio_report_patient_id", "label": "Remidio Report Patient ID", "field_type": "text"},
    {"scope": "document", "key": "remidio_report_local_id", "label": "Remidio Report Local ID", "field_type": "text"},
    {"scope": "document", "key": "remidio_report_datetime", "label": "Remidio Report Date/Time", "field_type": "datetime"},
    {"scope": "document", "key": "report_path_present", "label": "Report Path Present", "field_type": "boolean"},
    {"scope": "document", "key": "linked_remidio_image_ids", "label": "Linked Remidio Image IDs", "field_type": "json"},
    {"scope": "document", "key": "refer_required", "label": "Refer Required", "field_type": "boolean"},
    {"scope": "document", "key": "left_eye_diagnosis", "label": "Left Eye Diagnosis", "field_type": "json"},
    {"scope": "document", "key": "left_eye_report_comments", "label": "Left Eye Report Comments", "field_type": "textarea", "is_pii_default": True},
    {"scope": "document", "key": "right_eye_diagnosis", "label": "Right Eye Diagnosis", "field_type": "json"},
    {"scope": "document", "key": "right_eye_report_comments", "label": "Right Eye Report Comments", "field_type": "textarea", "is_pii_default": True},
    {"scope": "document", "key": "reporting_doctor_id", "label": "Reporting Doctor ID", "field_type": "text"},
    {"scope": "document", "key": "ai_confidence", "label": "AI Confidence", "field_type": "decimal"},
    {"scope": "document", "key": "ai_input_sufficient", "label": "AI Input Sufficient", "field_type": "boolean"},
    {"scope": "document", "key": "ai_quality_sufficient", "label": "AI Quality Sufficient", "field_type": "boolean"},
    {"scope": "document", "key": "ai_suggested_refer", "label": "AI Suggested Refer", "field_type": "boolean"},
    {"scope": "document", "key": "number_of_heatmap_images", "label": "Heatmap Image Count", "field_type": "integer"},
    {"scope": "document", "key": "gma_left_eye_cdr", "label": "GMA Left Eye CDR", "field_type": "decimal"},
    {"scope": "document", "key": "gma_right_eye_cdr", "label": "GMA Right Eye CDR", "field_type": "decimal"},
    {"scope": "document", "key": "gma_suggested_refer", "label": "GMA Suggested Refer", "field_type": "boolean"},
    {"scope": "document", "key": "gma_patient_level_result", "label": "GMA Patient Result", "field_type": "text"},
    {
        "scope": "document",
        "key": "remidio_report_raw_metadata",
        "label": "Raw Remidio Report Metadata",
        "field_type": "json",
        "is_pii_default": True,
        "description": "Source-only catch-all report payload from Remidio.",
    },
]


SCHEMA_KEYS = [
    "hospital_UHID",
    "remidio_patient_id",
    "patient_name",
    "patient_dob",
    "patient_age_yrs",
    "sex",
    "remidio_site_id",
    "remidio_site_custom_identifier",
    "remidio_patient_raw_metadata",
    "remidio_exam_id",
    "remidio_exam_local_id",
    "exam_code",
    "capture_datetime",
    "remidio_exam_report_datetime",
    "device_type",
    "exam_state",
    "medical_history",
    "has_doctor_report",
    "has_ai_report",
    "has_gma_report",
    "has_medios_ai_report",
    "clinical_image_count",
    "report_document_count",
    "remidio_encounter_raw_metadata",
    "remidio_image_id",
    "remidio_image_local_id",
    "remidio_image_exam_id",
    "image_bucket",
    "image_variant",
    "image_capture_datetime",
    "image_device_type",
    "laterality",
    "fundus_field",
    "image_segment",
    "remidio_image_quality",
    "is_cropped",
    "is_montage",
    "edit_operations",
    "original_remidio_image_ids",
    "width_px",
    "height_px",
    "source_path_present",
    "thumbnail_path_present",
    "disc_present",
    "disc_quality_acceptable",
    "disc_quality_score",
    "disc_roi_x",
    "disc_roi_y",
    "remidio_image_exif_metadata",
    "remidio_image_raw_metadata",
    "remidio_report_id",
    "remidio_report_type",
    "remidio_report_exam_id",
    "remidio_report_patient_id",
    "remidio_report_local_id",
    "remidio_report_datetime",
    "report_path_present",
    "linked_remidio_image_ids",
    "refer_required",
    "left_eye_diagnosis",
    "left_eye_report_comments",
    "right_eye_diagnosis",
    "right_eye_report_comments",
    "reporting_doctor_id",
    "ai_confidence",
    "ai_input_sufficient",
    "ai_quality_sufficient",
    "ai_suggested_refer",
    "number_of_heatmap_images",
    "gma_left_eye_cdr",
    "gma_right_eye_cdr",
    "gma_suggested_refer",
    "gma_patient_level_result",
    "remidio_report_raw_metadata",
]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    if FIELDS_TABLE not in tables:
        return
    _seed_fields(conn)
    if EST_TABLE in tables:
        _seed_encounter_set_type(conn)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    if EST_TABLE in tables:
        _delete_standard_encounter_set_type_if_unlinked(conn, tables)
    if FIELDS_TABLE in tables:
        conn.execute(
            sa.text(
                """
                UPDATE upload_metadata_field_definitions
                SET active = false
                WHERE key = ANY(:keys)
                """
            ),
            {"keys": [field["key"] for field in REMEDIO_FIELDS]},
        )


def _seed_fields(conn) -> None:
    for field in REMEDIO_FIELDS:
        existing = conn.execute(
            sa.text(f"SELECT id FROM {FIELDS_TABLE} WHERE key = :key LIMIT 1"),
            {"key": field["key"]},
        ).scalar()
        if existing:
            conn.execute(
                sa.text(
                    f"""
                    UPDATE {FIELDS_TABLE}
                    SET active = true,
                        updated_at = now()
                    WHERE id = :id
                    """
                ),
                {"id": existing},
            )
            continue
        conn.execute(
            sa.text(
                f"""
                INSERT INTO {FIELDS_TABLE}
                    (scope, key, label, sctid, field_type, selection_mode, options_json, description,
                     validation_regex, validation_error_message, required_at_upload_default,
                     required_for_verification_default, visible_to_grader_default, is_pii_default,
                     active, created_at, updated_at)
                VALUES
                    (:scope, :key, :label, NULL, :field_type, :selection_mode, CAST(:options_json AS JSONB),
                     :description, NULL, NULL, :required_at_upload_default,
                     :required_for_verification_default, :visible_to_grader_default, :is_pii_default,
                     true, now(), now())
                """
            ),
            {
                "scope": field["scope"],
                "key": field["key"],
                "label": field["label"],
                "field_type": field["field_type"],
                "selection_mode": field.get("selection_mode"),
                "options_json": json.dumps(field.get("options_json")) if field.get("options_json") is not None else None,
                "description": field.get("description"),
                "required_at_upload_default": field.get("required_at_upload_default", False),
                "required_for_verification_default": field.get("required_for_verification_default", False),
                "visible_to_grader_default": field.get("visible_to_grader_default", False),
                "is_pii_default": field.get("is_pii_default", False),
            },
        )


def _seed_encounter_set_type(conn) -> None:
    fields_by_key = {}
    for row in conn.execute(
            sa.text(
                f"""
                SELECT id, scope, key, label, sctid, field_type, selection_mode, options_json, description,
                       validation_regex, validation_error_message, required_at_upload_default,
                       required_for_verification_default, visible_to_grader_default, is_pii_default
                FROM {FIELDS_TABLE}
                WHERE key = ANY(:keys)
                """
            ),
            {"keys": SCHEMA_KEYS},
    ):
        mapping = row._mapping
        fields_by_key[mapping["key"]] = mapping
    schema = {"fields": []}
    scope_order = {"patient": 0, "encounter": 0, "image": 0, "document": 0, "upload": 0}
    for key in SCHEMA_KEYS:
        row = fields_by_key.get(key)
        if row is None:
            continue
        scope = row["scope"]
        scope_order[scope] += 1
        schema["fields"].append(
            {
                "field_definition_id": row["id"],
                "key": row["key"],
                "label": row["label"],
                "sctid": row["sctid"],
                "scope": scope,
                "type": row["field_type"],
                "display_order": scope_order[scope],
                "selection_mode": row["selection_mode"] if row["field_type"] == "select" else None,
                "options": row["options_json"] if row["field_type"] == "select" else None,
                "description": row["description"],
                "validation_regex": row["validation_regex"],
                "validation_error_message": row["validation_error_message"],
                "required_at_upload": False,
                "required_for_verification": bool(row["required_for_verification_default"]),
                "visible_to_grader": bool(row["visible_to_grader_default"]),
                "is_pii": bool(row["is_pii_default"]),
            }
        )
    asset_rules = {
        "allow_clinical_images": True,
        "min_clinical_images": None,
        "max_clinical_images": None,
        "allow_document_uploads": True,
        "allow_pdf_uploads": True,
        "allow_document_image_uploads": False,
        "max_documents": None,
        "max_pdfs": None,
        "max_document_images": None,
        "allow_report_uploads": True,
        "allow_report_pdfs": True,
        "allow_report_images": False,
        "max_reports": None,
    }
    existing = conn.execute(sa.text(f"SELECT id FROM {EST_TABLE} WHERE code = :code"), {"code": EST_CODE}).scalar()
    if existing:
        conn.execute(
            sa.text(
                f"""
                UPDATE {EST_TABLE}
                SET name = :name,
                    description = :description,
                    metadata_schema_json = CAST(:schema AS JSONB),
                    asset_rules_json = CAST(:asset_rules AS JSONB),
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {
                "id": existing,
                "name": "Remidio API Standard Encounter Set",
                "description": "Standard Remidio FOP/PRISTINE encounter-set contract seeded from live API payloads.",
                "schema": json.dumps(schema),
                "asset_rules": json.dumps(asset_rules),
            },
        )
        return
    conn.execute(
        sa.text(
            f"""
            INSERT INTO {EST_TABLE}
                (name, code, description, encounter_grading_scheme_id, metadata_schema_json,
                 asset_rules_json, active, created_at, updated_at)
            VALUES
                (:name, :code, :description, NULL, CAST(:schema AS JSONB),
                 CAST(:asset_rules AS JSONB), false, now(), now())
            """
        ),
        {
            "name": "Remidio API Standard Encounter Set",
            "code": EST_CODE,
            "description": "Standard Remidio FOP/PRISTINE encounter-set contract seeded from live API payloads.",
            "schema": json.dumps(schema),
            "asset_rules": json.dumps(asset_rules),
        },
    )


def _delete_standard_encounter_set_type_if_unlinked(conn, tables: set[str]) -> None:
    est_id = conn.execute(sa.text(f"SELECT id FROM {EST_TABLE} WHERE code = :code"), {"code": EST_CODE}).scalar()
    if not est_id:
        return
    if "upload_profile_encounter_set_types" in tables:
        linked = conn.execute(
            sa.text(
                """
                SELECT 1
                FROM upload_profile_encounter_set_types
                WHERE encounter_set_type_id = :est_id
                LIMIT 1
                """
            ),
            {"est_id": est_id},
        ).scalar()
        if linked:
            conn.execute(sa.text(f"UPDATE {EST_TABLE} SET active = false WHERE id = :est_id"), {"est_id": est_id})
            return
    conn.execute(sa.text(f"DELETE FROM {EST_TABLE} WHERE id = :est_id"), {"est_id": est_id})
