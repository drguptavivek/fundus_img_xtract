"""seed core upload metadata fields

Revision ID: e4f3a2b1c0d9
Revises: d9e8c7b6a5f4
Create Date: 2026-05-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import json
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "e4f3a2b1c0d9"
down_revision: Union[str, Sequence[str], None] = "d9e8c7b6a5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "upload_metadata_field_definitions"


FIELDS = [
    {
        "scope": "patient",
        "key": "patient_name",
        "label": "Patient Name",
        "field_type": "text",
        "is_pii_default": True,
    },
    {
        "scope": "patient",
        "key": "patient_age_yrs",
        "label": "Age of Patient (years)",
        "field_type": "integer",
        "validation_regex": r"^(?:[0-9]|[1-9][0-9]|1[0-4][0-9]|150)$",
        "validation_error_message": "Enter age in completed years from 0 to 150.",
        "is_pii_default": True,
    },
    {
        "scope": "patient",
        "key": "patient_dob",
        "label": "Date of Birth",
        "field_type": "date",
        "is_pii_default": True,
    },
    {
        "scope": "patient",
        "key": "sex",
        "label": "Sex",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": [
            {"label": "Female", "value": "female"},
            {"label": "Male", "value": "male"},
            {"label": "Other", "value": "other"},
            {"label": "Unknown", "value": "unknown"},
        ],
        "is_pii_default": True,
    },
    {
        "scope": "patient",
        "key": "hospital_UHID",
        "label": "Hospital UHID/MRN",
        "field_type": "text",
        "required_for_verification_default": True,
        "is_pii_default": True,
    },
    {
        "scope": "patient",
        "key": "project_unique_id_patient",
        "label": "Project Specific Unique ID for Patient",
        "field_type": "text",
        "is_pii_default": False,
    },
    {
        "scope": "patient",
        "key": "patient_phone",
        "label": "Patient Phone",
        "field_type": "phone",
        "validation_regex": r"^[0-9+\-\s()]{7,20}$",
        "validation_error_message": "Enter a valid phone number.",
        "is_pii_default": True,
    },
    {
        "scope": "patient",
        "key": "patient_email",
        "label": "Patient Email",
        "field_type": "email",
        "validation_regex": r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        "validation_error_message": "Enter a valid email address.",
        "is_pii_default": True,
    },
    {
        "scope": "patient",
        "key": "patient_remarks",
        "label": "Patient Remarks",
        "field_type": "textarea",
        "is_pii_default": True,
    },
    {
        "scope": "encounter",
        "key": "date_of_visit",
        "label": "Date of Visit",
        "field_type": "date",
    },
    {
        "scope": "encounter",
        "key": "patient_diagnosis",
        "label": "Diagnosis",
        "field_type": "textarea",
        "visible_to_grader_default": False,
        "is_pii_default": False,
    },
    {
        "scope": "encounter",
        "key": "clinic_id",
        "label": "Clinic ID",
        "field_type": "text",
        "is_pii_default": True,
    },
    {
        "scope": "encounter",
        "key": "normal_abnormal_status",
        "label": "Normal/Abnormal Status",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": [
            {"label": "Normal", "value": "normal"},
            {"label": "Abnormal", "value": "abnormal"},
            {"label": "Unknown / Not Assessed", "value": "unknown"},
        ],
        "visible_to_grader_default": False,
    },
    {
        "scope": "encounter",
        "key": "encounter_remarks",
        "label": "Encounter Remarks",
        "field_type": "textarea",
        "is_pii_default": True,
    },
    {
        "scope": "encounter",
        "key": "visual_acuity_snellen_od",
        "label": "Visual Acuity Snellen OD",
        "field_type": "text",
        "validation_regex": r"^(?:[0-9]{1,2}/[0-9]{1,3}|CF|HM|PL|NPL|CFCF|Unknown)$",
        "validation_error_message": "Enter Snellen acuity such as 6/6 or 20/40, or CF/HM/PL/NPL/Unknown.",
    },
    {
        "scope": "encounter",
        "key": "visual_acuity_snellen_os",
        "label": "Visual Acuity Snellen OS",
        "field_type": "text",
        "validation_regex": r"^(?:[0-9]{1,2}/[0-9]{1,3}|CF|HM|PL|NPL|CFCF|Unknown)$",
        "validation_error_message": "Enter Snellen acuity such as 6/6 or 20/40, or CF/HM/PL/NPL/Unknown.",
    },
    {
        "scope": "encounter",
        "key": "visual_acuity_etdrs_od",
        "label": "Visual Acuity ETDRS OD",
        "field_type": "integer",
        "validation_regex": r"^(?:[0-9]|[1-9][0-9]|1[0-1][0-9]|120)$",
        "validation_error_message": "Enter ETDRS letter score from 0 to 120.",
    },
    {
        "scope": "encounter",
        "key": "visual_acuity_etdrs_os",
        "label": "Visual Acuity ETDRS OS",
        "field_type": "integer",
        "validation_regex": r"^(?:[0-9]|[1-9][0-9]|1[0-1][0-9]|120)$",
        "validation_error_message": "Enter ETDRS letter score from 0 to 120.",
    },
    {
        "scope": "encounter",
        "key": "visual_acuity_logmar_od",
        "label": "Visual Acuity LogMAR OD",
        "field_type": "decimal",
        "validation_regex": r"^-?[0-9](?:\.[0-9]{1,2})?$",
        "validation_error_message": "Enter LogMAR as a decimal, for example 0.0, 0.3, or 1.0.",
    },
    {
        "scope": "encounter",
        "key": "visual_acuity_logmar_os",
        "label": "Visual Acuity LogMAR OS",
        "field_type": "decimal",
        "validation_regex": r"^-?[0-9](?:\.[0-9]{1,2})?$",
        "validation_error_message": "Enter LogMAR as a decimal, for example 0.0, 0.3, or 1.0.",
    },
    {
        "scope": "encounter",
        "key": "is_post_operative_patient",
        "label": "Is Post-operative Patient",
        "field_type": "boolean",
    },
    {
        "scope": "encounter",
        "key": "post_operative_eye",
        "label": "Post-operative Eye",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": [
            {"label": "OD / Right", "value": "OD"},
            {"label": "OS / Left", "value": "OS"},
            {"label": "OU / Both", "value": "OU"},
            {"label": "Unknown", "value": "unknown"},
        ],
    },
    {
        "scope": "encounter",
        "key": "surgery_type",
        "label": "Surgery Type",
        "field_type": "text",
    },
    {
        "scope": "encounter",
        "key": "surgery_date",
        "label": "Surgery Date",
        "field_type": "date",
    },
    {
        "scope": "encounter",
        "key": "post_operative_remarks",
        "label": "Post-operative Remarks",
        "field_type": "textarea",
    },
    {
        "scope": "image",
        "key": "laterality",
        "label": "Laterality",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": [
            {"label": "OD / Right", "value": "OD"},
            {"label": "OS / Left", "value": "OS"},
            {"label": "OU / Both", "value": "OU"},
            {"label": "Unknown", "value": "unknown"},
        ],
        "required_at_upload_default": True,
        "required_for_verification_default": True,
    },
    {
        "scope": "image",
        "key": "eye",
        "label": "Eye",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": [
            {"label": "OD / Right", "value": "OD"},
            {"label": "OS / Left", "value": "OS"},
            {"label": "OU / Both", "value": "OU"},
            {"label": "Unknown", "value": "unknown"},
        ],
    },
    {
        "scope": "image",
        "key": "image_modality",
        "label": "Image Modality",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": [
            {"label": "Color fundus photo", "value": "color_fundus"},
            {"label": "Anterior segment photo", "value": "anterior_segment_photo"},
            {"label": "External eye photo", "value": "external_eye_photo"},
            {"label": "OCT", "value": "oct"},
            {"label": "Other", "value": "other"},
            {"label": "Unknown", "value": "unknown"},
        ],
    },
    {
        "scope": "image",
        "key": "fundus_image_view",
        "label": "Fundus Image View",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": [
            {"label": "Disc-centered", "value": "disc_centered"},
            {"label": "Macula-centered", "value": "macula_centered"},
            {"label": "Peripheral", "value": "peripheral"},
            {"label": "Montage", "value": "montage"},
            {"label": "Red-free", "value": "red_free"},
            {"label": "Unknown", "value": "unknown"},
        ],
    },
    {
        "scope": "image",
        "key": "external_eye_image_view",
        "label": "External Eye Image View",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": [
            {"label": "Primary gaze", "value": "primary_gaze"},
            {"label": "Up gaze", "value": "up_gaze"},
            {"label": "Down gaze", "value": "down_gaze"},
            {"label": "Left gaze", "value": "left_gaze"},
            {"label": "Right gaze", "value": "right_gaze"},
            {"label": "Close-up", "value": "close_up"},
            {"label": "Distance", "value": "distance"},
            {"label": "Lid eversion", "value": "lid_eversion"},
            {"label": "Fluorescein", "value": "fluorescein"},
            {"label": "Unknown", "value": "unknown"},
        ],
    },
    {
        "scope": "image",
        "key": "strabismus_gaze_position",
        "label": "Strabismus Gaze Position",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": [
            {"label": "Primary", "value": "primary"},
            {"label": "Up", "value": "up"},
            {"label": "Down", "value": "down"},
            {"label": "Left", "value": "left"},
            {"label": "Right", "value": "right"},
            {"label": "Up-left", "value": "up_left"},
            {"label": "Up-right", "value": "up_right"},
            {"label": "Down-left", "value": "down_left"},
            {"label": "Down-right", "value": "down_right"},
        ],
    },
    {
        "scope": "image",
        "key": "anterior_segment_view",
        "label": "Anterior Segment View",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": [
            {"label": "Diffuse illumination", "value": "diffuse_illumination"},
            {"label": "Slit beam", "value": "slit_beam"},
            {"label": "Retroillumination", "value": "retroillumination"},
            {"label": "Fluorescein staining", "value": "fluorescein_staining"},
            {"label": "Cobalt blue", "value": "cobalt_blue"},
            {"label": "Unknown", "value": "unknown"},
        ],
    },
    {
        "scope": "image",
        "key": "oct_scan_type",
        "label": "OCT Scan Type",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": [
            {"label": "Macula cube", "value": "macula_cube"},
            {"label": "RNFL circle", "value": "rnfl_circle"},
            {"label": "Optic disc cube", "value": "optic_disc_cube"},
            {"label": "Line scan", "value": "line_scan"},
            {"label": "Raster scan", "value": "raster_scan"},
            {"label": "Unknown", "value": "unknown"},
        ],
    },
    {
        "scope": "image",
        "key": "distance_or_near",
        "label": "Distance or Near",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": [
            {"label": "Distance", "value": "distance"},
            {"label": "Near", "value": "near"},
            {"label": "Unknown", "value": "unknown"},
        ],
    },
    {
        "scope": "image",
        "key": "with_glasses",
        "label": "With Glasses",
        "field_type": "boolean",
    },
    {
        "scope": "image",
        "key": "image_quality",
        "label": "Image Quality",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": [
            {"label": "Good", "value": "good"},
            {"label": "Fair", "value": "fair"},
            {"label": "Poor", "value": "poor"},
            {"label": "Not gradable", "value": "not_gradable"},
            {"label": "Unknown", "value": "unknown"},
        ],
    },
    {
        "scope": "image",
        "key": "image_remarks",
        "label": "Image Remarks",
        "field_type": "textarea",
    },
    {
        "scope": "document",
        "key": "document_category",
        "label": "Document Category",
        "field_type": "select",
        "selection_mode": "single",
        "options_json": [
            {"label": "Referral", "value": "referral"},
            {"label": "Consent", "value": "consent"},
            {"label": "Report", "value": "report"},
            {"label": "Label", "value": "label"},
            {"label": "Other", "value": "other"},
        ],
        "is_pii_default": True,
    },
    {
        "scope": "document",
        "key": "report_type",
        "label": "Report Type",
        "field_type": "text",
        "is_pii_default": True,
    },
    {
        "scope": "document",
        "key": "document_remarks",
        "label": "Document Remarks",
        "field_type": "textarea",
        "is_pii_default": True,
    },
    {
        "scope": "upload",
        "key": "source_system",
        "label": "Source System",
        "field_type": "text",
    },
    {
        "scope": "upload",
        "key": "operator_notes",
        "label": "Operator Notes",
        "field_type": "textarea",
    },
    {
        "scope": "upload",
        "key": "import_batch",
        "label": "Import Batch",
        "field_type": "text",
    },
    {
        "scope": "upload",
        "key": "acquisition_method",
        "label": "Acquisition Method",
        "field_type": "text",
    },
]


def _table_exists(conn) -> bool:
    return TABLE_NAME in inspect(conn).get_table_names()


def _columns(conn) -> set[str]:
    if not _table_exists(conn):
        return set()
    return {column["name"] for column in inspect(conn).get_columns(TABLE_NAME)}


def _field_values(field: dict) -> dict:
    return {
        "scope": field["scope"],
        "key": field["key"],
        "label": field["label"],
        "sctid": field.get("sctid"),
        "field_type": field["field_type"],
        "selection_mode": field.get("selection_mode"),
        "options_json": field.get("options_json"),
        "description": field.get("description"),
        "validation_regex": field.get("validation_regex"),
        "validation_error_message": field.get("validation_error_message"),
        "required_at_upload_default": field.get("required_at_upload_default", False),
        "required_for_verification_default": field.get("required_for_verification_default", False),
        "visible_to_grader_default": field.get("visible_to_grader_default", False),
        "is_pii_default": field.get("is_pii_default", False),
        "active": True,
    }


def upgrade() -> None:
    conn = op.get_bind()
    if not _table_exists(conn):
        return
    existing_columns = _columns(conn)
    if "validation_regex" not in existing_columns:
        op.add_column(TABLE_NAME, sa.Column("validation_regex", sa.Text(), nullable=True))
    if "validation_error_message" not in existing_columns:
        op.add_column(TABLE_NAME, sa.Column("validation_error_message", sa.String(length=255), nullable=True))
    has_sctid = "sctid" in _columns(conn)
    for field in FIELDS:
        values = _field_values(field)
        if not has_sctid:
            values.pop("sctid", None)
        conn.execute(
            sa.text(
                f"""
                INSERT INTO {TABLE_NAME} (
                    scope, key, label, {'' if not has_sctid else 'sctid,'}
                    field_type, selection_mode, options_json, description,
                    validation_regex, validation_error_message,
                    required_at_upload_default, required_for_verification_default,
                    visible_to_grader_default, is_pii_default, active
                )
                VALUES (
                    :scope, :key, :label, {'' if not has_sctid else ':sctid,'}
                    :field_type, :selection_mode, CAST(:options_json AS jsonb), :description,
                    :validation_regex, :validation_error_message,
                    :required_at_upload_default, :required_for_verification_default,
                    :visible_to_grader_default, :is_pii_default, :active
                )
                ON CONFLICT (key) DO UPDATE SET
                    label = EXCLUDED.label,
                    field_type = EXCLUDED.field_type,
                    selection_mode = EXCLUDED.selection_mode,
                    options_json = COALESCE(NULLIF({TABLE_NAME}.options_json, '[]'::jsonb), EXCLUDED.options_json),
                    description = COALESCE({TABLE_NAME}.description, EXCLUDED.description),
                    validation_regex = COALESCE({TABLE_NAME}.validation_regex, EXCLUDED.validation_regex),
                    validation_error_message = COALESCE(
                        {TABLE_NAME}.validation_error_message,
                        EXCLUDED.validation_error_message
                    ),
                    required_at_upload_default = {TABLE_NAME}.required_at_upload_default OR EXCLUDED.required_at_upload_default,
                    required_for_verification_default = {TABLE_NAME}.required_for_verification_default OR EXCLUDED.required_for_verification_default,
                    visible_to_grader_default = {TABLE_NAME}.visible_to_grader_default OR EXCLUDED.visible_to_grader_default,
                    is_pii_default = {TABLE_NAME}.is_pii_default OR EXCLUDED.is_pii_default,
                    active = TRUE
                """
            ),
            {
                **values,
                "options_json": json.dumps(values.get("options_json")) if values.get("options_json") is not None else None,
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    if not _table_exists(conn):
        return
    keys = [field["key"] for field in FIELDS]
    op.execute(
        sa.text(f"DELETE FROM {TABLE_NAME} WHERE key = ANY(:keys)").bindparams(
            sa.bindparam("keys", value=keys, type_=sa.ARRAY(sa.String()))
        )
    )
    columns = _columns(conn)
    if "validation_error_message" in columns:
        op.drop_column(TABLE_NAME, "validation_error_message")
    if "validation_regex" in columns:
        op.drop_column(TABLE_NAME, "validation_regex")
