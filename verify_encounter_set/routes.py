from flask import after_this_request, render_template, abort, current_app, flash, make_response, redirect, url_for, request, jsonify
from flask_login import login_required, current_user
from auth.roles import roles_required
from auth.utils import utcnow
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from verify_encounter_set.models import EncounterVerificationHistory  # noqa: F401 - registers table with Base.metadata

from models import (
    AMDReport,
    DiabeticRetinopathyReport,
    Disease,
    EncounterSetGradingScope,
    EncounterSetGradingPackage,
    GlaucomaReport,
    GlaucomaResultsCleaned,
    GradingTask,
    PatientEncounters,
    EncounterSetImage,
    ImageMetadata,
    ImagePiiVerification,
    User,
)
from encounter_sets.models import EncounterSetAttachment
from encounter_sets.permissions import (
    apply_classical_or_project_permission_scope,
)
from encounter_sets.grading_policy import (
    EncounterSetPackagePolicyDTO,
    EncounterSetScopePolicyDTO,
    freeze_policy_snapshot,
    package_policy_from_model,
)
from services.encounter_referral_suggestion import (
    normalize_referral_positive_diseases,
    normalize_referral_suggestion,
    update_encounter_referral_suggestion_from_attachments,
)
from services.encounter_set_ai_inference import create_wadhwani_task_ids_for_encounter, enqueue_wadhwani_for_task_ids
from upload_profiles.models import PatientEncounterTargetDisease
from upload_profiles.models import UploadProfile, UploadProfileEncounterSetType, UploadProfileEncounterSetTypeImageGradingScheme
from upload_profiles.image_task_routing import (
    image_metadata_matches_rule,
    missing_image_task_routing_fields,
    required_image_task_routing_fields,
)
from db_transaction_manager import transaction_scope
from authz import access_context, role_scoped_rows
from services.uploads.access import encounter_columns
from utils.utils import with_session
from marshmallow import Schema, fields, validate, ValidationError
from . import bp
from services.project_referral_diseases import (
    canonicalize_project_positive_diseases,
    list_project_positive_disease_options,
)

VERIFY_ROLES = frozenset(
    {
        "verifier",
        "local_admin",
        "data_manager",
        "fileUploader",
        "optometrist",
        "field_optometrist",
        "field_ophthalmologist",
    }
)


def _apply_verification_scope(query):
    return apply_classical_or_project_permission_scope(
        query,
        PatientEncounters,
        current_user,
        VERIFY_ROLES,
        classical_operation="upload",
    )


def _apply_verification_mutation_scope(query):
    """Mutations use the same exact classical/project scope as reads."""
    return _apply_verification_scope(query)


# =========================================================================
# REQUEST SCHEMAS (P1.4: Input Validation)
# =========================================================================

class CropCoordinatesSchema(Schema):
    """Validate crop coordinates for image editing"""
    x = fields.Integer(required=False, validate=validate.Range(min=0))
    y = fields.Integer(required=False, validate=validate.Range(min=0))
    width = fields.Integer(required=False, validate=validate.Range(min=1))
    height = fields.Integer(required=False, validate=validate.Range(min=1))


class SaveEditRequestSchema(Schema):
    """Validate save_edit request data"""
    crop = fields.Nested(CropCoordinatesSchema, required=False)
    image_data = fields.String(required=False)
    # Shared with the Direct Upload editor. EncounterSet authorization does
    # not use this override, but a valid shared payload must not be rejected.
    allow_graded_edit = fields.Boolean(required=False, load_default=False)


# =========================================================================
# UTILITY FUNCTIONS (P1.3: S3 Hospital Scoping)
# =========================================================================

def validate_s3_config_access(image, current_user, db):
    """
    Validate that user has access to image's S3 config (if used).

    P1.3: Prevents cross-hospital S3 access

    Args:
        image: EncounterSetImage model instance
        current_user: Current user
        db: Database session

    Returns:
        (is_valid, error_message) tuple
    """
    if not image.s3_config_id:
        # Image uses local storage, not S3
        return True, None

    from models import S3Config

    s3_config = db.query(S3Config).filter_by(id=image.s3_config_id).first()
    if not s3_config:
        # S3 config not found (data inconsistency)
        return False, "S3 configuration not found"

    # Verify S3 config belongs to user's hospital
    if s3_config.hospital_id != current_user.hospital_id:
        import logging
        logger = logging.getLogger("verify_encounter_set")
        logger.warning(
            "Cross-hospital S3 access attempt blocked",
            extra={
                'user_id': current_user.id,
                'user_hospital': current_user.hospital_id,
                'image_uuid': image.uuid,
                's3_hospital': s3_config.hospital_id
            }
        )
        return False, "Access denied to S3 storage"

    return True, None

@bp.route("/")
@login_required
def index():
    """List encounter sets pending verification."""
    with transaction_scope() as db:
        # Get encounters that are set-based and NOT yet verified
        # Apply hospital scoping to prevent cross-hospital access
        encounters = db.query(PatientEncounters).filter(
            PatientEncounters.is_set_based == True,
            or_(
                PatientEncounters.encounter_verified_status == 'pending',
                PatientEncounters.encounter_verified_status.is_(None),
            ),
        )

        # Apply hospital scoping (operation='upload' for hospital-bound)
        encounters = _apply_verification_scope(encounters)

        encounters = encounters.order_by(PatientEncounters.id.desc()).all()

        return render_template("verify_encounter_set/index.html", encounters=encounters)

@bp.route("/verify/<uuid>")
@login_required
def verify_encounter(uuid):
    """View and manage a specific encounter set for verification."""
    with transaction_scope() as db:
        context = _verification_context(db, uuid)
        if not context["encounter"].is_set_based:
            flash("This encounter is not set-based.", "warning")
            return redirect(url_for("verify_encounter_set.index"))

        response = make_response(render_template(
            "verify_encounter_set/verify.html",
            **context,
        ))
        response.headers["Cache-Control"] = "no-store, private"
        return response


@bp.route("/verify/<uuid>/panel/<panel>")
@login_required
def verify_panel(uuid, panel):
    """Render one EncounterSet verification panel for HTMX loading."""
    if panel not in {"patient", "image", "document", "summary"}:
        abort(404)
    with transaction_scope() as db:
        context = _verification_context(db, uuid)
        selected_image = None
        selected_attachment = None
        selected_image_index = None
        if panel == "image":
            image_uuid = request.args.get("image_uuid")
            selected_image = next((image for image in context["images"] if image.uuid == image_uuid), None)
            if selected_image is None:
                abort(404)
            selected_image_index = context["images"].index(selected_image) + 1
        if panel == "document":
            attachment_uuid = request.args.get("attachment_uuid")
            selected_attachment = next(
                (attachment for attachment in context["attachments"] if attachment.uuid == attachment_uuid),
                None,
            )
            if selected_attachment is None:
                abort(404)

        response = make_response(render_template(
            "verify_encounter_set/_verify_panel.html",
            panel=panel,
            selected_image=selected_image,
            selected_image_index=selected_image_index,
            selected_attachment=selected_attachment,
            **context,
        ))
        response.headers["Cache-Control"] = "no-store, private"
        return response


@bp.route("/metadata/<uuid>", methods=["POST"])
@login_required
def update_metadata(uuid):
    """Persist EncounterSet verification metadata fields allowed by the EncounterSetType."""
    with transaction_scope() as db:
        query = (
            db.query(PatientEncounters)
            .options(
                selectinload(PatientEncounters.upload_profile)
                .selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.encounter_set_type)
            )
            .filter_by(uuid=uuid)
        )
        query = _apply_verification_scope(query)
        encounter = query.first()
        if not encounter or not encounter.is_set_based:
            abort(404)
        if encounter.encounter_verified_status == "verified":
            return _already_verified_response(encounter)

        was_reopened_for_correction = bool(
            (encounter.metadata_json or {}).get("verification", {}).get("reopened")
        )
        correction_before = None
        if was_reopened_for_correction:
            from verify_encounter_set.reopen_service import snapshot_encounter

            correction_before = snapshot_encounter(db, encounter)

        profile = _encounter_set_verification_profile(db, encounter)
        editable_fields = {
            (field["scope"], field["key"]): field
            for field in profile["metadata_fields"]
            if field.get("editable_during_verification")
        }

        encounter_metadata = dict(encounter.metadata_json or {})
        referral_form_name = "metadata__encounter__referral_suggestion"
        referral_diseases_form_name = "metadata__encounter__referral_positive_diseases"
        manual_referral_suggestion = None
        manual_referral_positive_diseases = None
        if _metadata_form_field_present(request.form, referral_form_name):
            manual_referral_suggestion = normalize_referral_suggestion(request.form.get(referral_form_name))
        if _metadata_form_field_present(request.form, referral_diseases_form_name):
            manual_referral_positive_diseases = normalize_referral_positive_diseases(
                request.form.getlist(referral_diseases_form_name)
            )
            canonical_diseases, invalid_diseases = canonicalize_project_positive_diseases(
                db,
                project_id=encounter.project_id,
                values=manual_referral_positive_diseases,
            )
            if invalid_diseases:
                return _verification_validation_response(
                    "Positive diseases must come from this project's grading or referral disease options. "
                    f"Invalid value(s): {', '.join(invalid_diseases)}.",
                    encounter_uuid=encounter.uuid,
                )
            manual_referral_positive_diseases = list(canonical_diseases)

        # A manual positive-disease selection is itself a referral-positive decision.
        # Without this, checking a disease while the Referral Suggestion dropdown is
        # left untouched (e.g. because there is no OCR report or prior AI assessment
        # to imply a value) silently fails to persist as a referral and never reaches
        # the "yes" branch below that drives task creation.
        if manual_referral_positive_diseases and manual_referral_suggestion is None:
            manual_referral_suggestion = "yes"

        effective_referral_suggestion = manual_referral_suggestion or encounter.referral_suggestion
        effective_positive_diseases = (
            manual_referral_positive_diseases
            if manual_referral_positive_diseases is not None
            else list(encounter.referral_positive_diseases_json or [])
        )
        referral_fields_touched = (
            manual_referral_suggestion is not None
            or manual_referral_positive_diseases is not None
        )
        if referral_fields_touched and effective_referral_suggestion == "yes":
            canonical_diseases, invalid_diseases = canonicalize_project_positive_diseases(
                db,
                project_id=encounter.project_id,
                values=effective_positive_diseases,
            )
            if invalid_diseases or not canonical_diseases:
                return _verification_validation_response(
                    "Select at least one positive disease from this project's grading or referral disease options "
                    "before saving a referral-positive EncounterSet.",
                    encounter_uuid=encounter.uuid,
                )
            effective_positive_diseases = list(canonical_diseases)
        for scope in ("patient", "encounter"):
            section = dict(encounter_metadata.get(scope) or {})
            for (field_scope, key), field in editable_fields.items():
                if field_scope != scope:
                    continue
                form_name = f"metadata__{scope}__{key}"
                if not _metadata_form_field_present(request.form, form_name):
                    continue
                section[key] = _metadata_form_value(request.form, form_name, field)
            if section:
                encounter_metadata[scope] = section
        encounter.metadata_json = encounter_metadata
        if (encounter_metadata.get("upload") or {}).get("source_kind") == "iitk_api":
            from iitk_api_integration.service import remap_iitk_encounter_site

            remap_iitk_encounter_site(db, encounter)

        images = {
            str(image.id): image
            for image in db.query(EncounterSetImage).filter_by(patient_encounter_id=encounter.id).all()
        }
        image_fields = [field for (scope, _key), field in editable_fields.items() if scope == "image"]
        for image_id, image in images.items():
            image_referral_form_name = f"metadata__image__{image_id}__referral_needed_or_positive_image"
            image_referral_alias_name = f"metadata__image__{image_id}__refrralneed_or_positive_image"
            if _metadata_form_field_present(request.form, image_referral_form_name):
                image.referral_needed_or_positive_image = normalize_referral_suggestion(request.form.get(image_referral_form_name))
                image.referral_needed_or_positive_image_updated_at = utcnow()
            elif _metadata_form_field_present(request.form, image_referral_alias_name):
                image.referral_needed_or_positive_image = normalize_referral_suggestion(request.form.get(image_referral_alias_name))
                image.referral_needed_or_positive_image_updated_at = utcnow()
            metadata = dict(image.metadata_json or {})
            image_laterality_form_name = f"metadata__image__{image_id}__laterality"
            if _metadata_form_field_present(request.form, image_laterality_form_name):
                laterality_value = request.form.get(image_laterality_form_name) or None
                if laterality_value:
                    metadata["laterality"] = laterality_value
                else:
                    metadata.pop("laterality", None)
            image_focus_form_name = f"metadata__image__{image_id}__focus"
            if _metadata_form_field_present(request.form, image_focus_form_name):
                focus_value = request.form.get(image_focus_form_name) or None
                if focus_value:
                    metadata["focus"] = focus_value
                else:
                    metadata.pop("focus", None)
            image_gaze_form_name = f"metadata__image__{image_id}__gaze_position"
            if _metadata_form_field_present(request.form, image_gaze_form_name):
                gaze_value = request.form.get(image_gaze_form_name) or None
                if gaze_value:
                    metadata["gaze_position"] = gaze_value
                else:
                    metadata.pop("gaze_position", None)
            for field in image_fields:
                form_name = f"metadata__image__{image_id}__{field['key']}"
                if not _metadata_form_field_present(request.form, form_name):
                    continue
                metadata[field["key"]] = _metadata_form_value(
                    request.form,
                    form_name,
                    field,
                )
            image.metadata_json = metadata

        from copy import deepcopy

        attachments = {
            str(attachment.id): attachment
            for attachment in db.query(EncounterSetAttachment).filter_by(patient_encounter_id=encounter.id).all()
        }
        ocr_fields = {
            "dr_result": ("ocr", "dr_report", "dr_data", "result"),
            "dr_qualitative_result": ("ocr", "dr_report", "dr_data", "qualitative_result"),
            "amd_result": ("ocr", "amd_report", "amd_data", "result"),
            "amd_qualitative_result": ("ocr", "amd_report", "amd_data", "qualitative_result"),
            "glaucoma_result": ("ocr", "glaucoma_report", "glaucoma_data", "result"),
            "glaucoma_qualitative_result": ("ocr", "glaucoma_report", "glaucoma_data", "qualitative_result"),
            "vcdr_right": ("ocr", "glaucoma_report", "glaucoma_data", "vcdr_right"),
            "vcdr_left": ("ocr", "glaucoma_report", "glaucoma_data", "vcdr_left"),
        }
        for attachment_id, attachment in attachments.items():
            metadata = deepcopy(attachment.metadata_json or {})
            for field_key, path in ocr_fields.items():
                form_name = f"metadata__attachment__{attachment_id}__ocr__{field_key}"
                if not _metadata_form_field_present(request.form, form_name):
                    continue
                _set_nested_metadata_value(metadata, path, request.form.get(form_name, "").strip())
            attachment.metadata_json = metadata
            _sync_attachment_ocr_clinical_reports(db, attachment)

        if attachments:
            from services.encounter_referral_suggestion import update_encounter_referral_suggestion_from_attachments

            update_encounter_referral_suggestion_from_attachments(db, encounter.id)
        if manual_referral_suggestion is not None:
            encounter.referral_suggestion = manual_referral_suggestion
            encounter.referral_suggestion_updated_at = utcnow()
        if manual_referral_positive_diseases is not None:
            encounter.referral_positive_diseases_json = manual_referral_positive_diseases
        elif manual_referral_suggestion == "no":
            encounter.referral_positive_diseases_json = []
        elif manual_referral_suggestion == "yes":
            encounter.referral_positive_diseases_json = effective_positive_diseases

        if was_reopened_for_correction:
            from verify_encounter_set.models import EncounterVerificationHistory
            from verify_encounter_set.reopen_service import snapshot_encounter

            db.flush()
            db.add(EncounterVerificationHistory(
                patient_encounter_id=encounter.id,
                action_type="metadata_corrected",
                actor_user_id=current_user.id,
                before_json=correction_before,
                after_json=snapshot_encounter(db, encounter),
            ))

        flash("Verification metadata updated.", "success")
        if request.headers.get("X-EncounterSet-Async") == "1":
            return jsonify({"success": True})
        return redirect(url_for("verify_encounter_set.verify_encounter", uuid=encounter.uuid))


@bp.route("/mark_reviewed/<uuid>", methods=["POST"])
@login_required
def mark_reviewed(uuid):
    """Mark an EncounterSet image as reviewed without implying anonymization."""
    with transaction_scope() as db:
        img = db.query(EncounterSetImage).filter_by(uuid=uuid).first()
        if not img:
            return jsonify({"success": False, "message": "Image not found"}), 404

        query = db.query(PatientEncounters).filter_by(id=img.patient_encounter_id)
        query = _apply_verification_scope(query)
        encounter = query.first()
        if not encounter:
            return jsonify({"success": False, "message": "Image not found"}), 404
        if encounter.encounter_verified_status == "verified":
            return _already_verified_json_response(encounter)

        missing_fields = missing_image_task_routing_fields(
            img,
            _active_encounter_set_type_config(encounter),
        )
        if missing_fields:
            return _missing_routing_metadata_response(missing_fields)

        img.is_reviewed = True
        return jsonify({"success": True})


def _verification_context(db, uuid: str) -> dict:
    query = (
        db.query(PatientEncounters)
        .options(
            selectinload(PatientEncounters.upload_profile)
            .selectinload(UploadProfile.encounter_set_types)
            .selectinload(UploadProfileEncounterSetType.encounter_set_type),
            selectinload(PatientEncounters.upload_profile)
            .selectinload(UploadProfile.encounter_set_types)
            .selectinload(UploadProfileEncounterSetType.encounter_grading_scheme),
            selectinload(PatientEncounters.upload_profile)
            .selectinload(UploadProfile.encounter_set_types)
            .selectinload(UploadProfileEncounterSetType.default_image_grading_scheme),
            selectinload(PatientEncounters.upload_profile)
            .selectinload(UploadProfile.encounter_set_types)
            .selectinload(UploadProfileEncounterSetType.image_grading_schemes)
            .selectinload(UploadProfileEncounterSetTypeImageGradingScheme.disease),
            selectinload(PatientEncounters.encounter_set_attachments),
        )
        .filter_by(uuid=uuid)
    )
    query = _apply_verification_scope(query)
    encounter = query.first()
    if not encounter:
        abort(404)

    images = (
        db.query(EncounterSetImage)
        .filter_by(patient_encounter_id=encounter.id)
        .order_by(EncounterSetImage.spatial_position)
        .all()
    )
    attachments = sorted(
        encounter.encounter_set_attachments or [],
        key=lambda item: (item.asset_kind or "", item.original_filename or "", item.id),
    )
    image_descriptors = {image.uuid: _image_descriptor(image) for image in images}
    return {
        "encounter": encounter,
        "images": images,
        "attachments": attachments,
        "ocr_summaries": _encounter_set_ocr_summaries(attachments),
        "verification_profile": _encounter_set_verification_profile(db, encounter),
        "verification_read_only": encounter.encounter_verified_status == "verified",
        "back_url": _encounter_set_browser_url(encounter),
        "image_descriptors": image_descriptors,
        "image_descriptor_vocabulary": IMAGE_DESCRIPTOR_VOCABULARY,
        "summary_eye_groups": _summary_eye_groups(images, image_descriptors),
        "can_reopen": _can_reopen_verification(db, encounter),
        "verification_history": _recent_verification_history(db, encounter),
    }


def _can_reopen_verification(db, encounter: PatientEncounters) -> bool:
    query = role_scoped_rows(
        select(PatientEncounters.id).where(PatientEncounters.id == encounter.id),
        access_context(db, current_user),
        encounter_columns(PatientEncounters),
        lab_roles={"verifier"},
        project_roles={"verifier"},
        allow_admin=True,
    )
    return db.execute(query).scalar_one_or_none() is not None


def _recent_verification_history(db, encounter: PatientEncounters, limit: int = 5) -> list[dict]:
    from verify_encounter_set.models import EncounterVerificationHistory

    rows = (
        db.query(EncounterVerificationHistory, User.username)
        .outerjoin(User, User.id == EncounterVerificationHistory.actor_user_id)
        .filter(EncounterVerificationHistory.patient_encounter_id == encounter.id)
        .order_by(EncounterVerificationHistory.occurred_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "action_type": entry.action_type,
            "actor_username": username,
            "occurred_at": entry.occurred_at,
            "note": entry.note,
        }
        for entry, username in rows
    ]


# Laterality/focus live in EncounterSetImage.metadata_json, and the key used depends on the
# ingestion path: Remidio writes fundus_field/image_segment (remidio_api_integration/mapper.py)
# while the seeded verification schema uses fundus_image_view. Read every known spelling.
IMAGE_LATERALITY_KEYS = ("laterality", "eye", "eye_side")
IMAGE_FOCUS_KEYS = ("focus", "fundus_image_view", "fundus_field", "field", "image_segment", "centering")
IMAGE_GAZE_KEYS = ("gaze_position", "strabismus_gaze_position", "gaze")

IMAGE_LATERALITY_LABELS = {
    "od": "OD", "right": "OD", "r": "OD", "re": "OD", "right eye": "OD",
    "os": "OS", "left": "OS", "l": "OS", "le": "OS", "left eye": "OS",
    "ou": "OU", "both": "OU", "bilateral": "OU",
}

IMAGE_FOCUS_LABELS = {
    "macula": "Macula", "macular": "Macula", "macula centred": "Macula",
    "macula centered": "Macula", "macula centred image": "Macula",
    "posterior pole": "Macula", "posterior": "Macula",
    "disc": "Disc", "disk": "Disc", "onh": "Disc", "optic disc": "Disc",
    "optic nerve head": "Disc", "disc centered": "Disc", "disc centred": "Disc",
}

IMAGE_GAZE_LABELS = {
    "primary": "Primary",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "up left": "Up Left",
    "up right": "Up Right",
    "down left": "Down Left",
    "down right": "Down Right",
    "composite": "Composite",
}

# Shared with the browser so nav labels can be recomputed after an inline metadata edit
# without duplicating the vocabulary in JavaScript.
IMAGE_DESCRIPTOR_VOCABULARY = {
    "laterality_keys": list(IMAGE_LATERALITY_KEYS),
    "focus_keys": list(IMAGE_FOCUS_KEYS),
    "gaze_keys": list(IMAGE_GAZE_KEYS),
    "laterality_labels": IMAGE_LATERALITY_LABELS,
    "focus_labels": IMAGE_FOCUS_LABELS,
    "gaze_labels": IMAGE_GAZE_LABELS,
    "other_label": "Other",
}


def _normalize_descriptor_value(value) -> str:
    return str(value or "").strip().lower().replace("_", " ")


def _first_metadata_value(metadata: dict, keys: tuple[str, ...]):
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return value
    return None


def _image_descriptor(image: EncounterSetImage) -> dict:
    """Resolve display-only laterality, retinal focus, and gaze for an image.

    Unknown values stay unknown: a verification screen must not present a guess as
    recorded fact, so anything unrecognised renders as an em dash rather than a default.
    """
    metadata = image.metadata_json if isinstance(image.metadata_json, dict) else {}

    laterality_raw = _first_metadata_value(metadata, IMAGE_LATERALITY_KEYS)
    laterality = IMAGE_LATERALITY_LABELS.get(_normalize_descriptor_value(laterality_raw))

    focus_raw = _first_metadata_value(metadata, IMAGE_FOCUS_KEYS)
    normalized_focus = _normalize_descriptor_value(focus_raw)
    focus = IMAGE_FOCUS_LABELS.get(normalized_focus)
    if focus is None and normalized_focus:
        focus = "Other"

    gaze_raw = _first_metadata_value(metadata, IMAGE_GAZE_KEYS)
    gaze = IMAGE_GAZE_LABELS.get(_normalize_descriptor_value(gaze_raw))

    return {
        "laterality": laterality,
        "focus": focus,
        "gaze": gaze,
        "label": " · ".join(part for part in (laterality, focus, gaze) if part) or "—",
    }


# Macula shots are graded first in most workflows, so they sort ahead of disc shots;
# anything unrecognised (or unset) sorts last within its eye.
_FOCUS_SORT_ORDER = {"Macula": 0, "Disc": 1}


def _summary_eye_groups(
    images: list[EncounterSetImage], image_descriptors: dict[str, dict]
) -> dict[str, list]:
    """Group gradable images by eye (OD/OS/Other) for the summary panel, macula-then-disc."""
    groups: dict[str, list] = {"OD": [], "OS": [], "other": []}
    for position, image in enumerate(images):
        if image.is_not_gradable:
            continue
        descriptor = image_descriptors.get(image.uuid) or {}
        eye = descriptor.get("laterality")
        bucket = eye if eye in ("OD", "OS") else "other"
        groups[bucket].append((position, image, descriptor))
    for bucket in groups:
        groups[bucket].sort(
            key=lambda row: (_FOCUS_SORT_ORDER.get(row[2].get("focus"), 2), row[0])
        )
        groups[bucket] = [
            {"image": image, "descriptor": descriptor, "display_index": position + 1}
            for position, image, descriptor in groups[bucket]
        ]
    return groups


def _encounter_set_ocr_summaries(attachments: list[EncounterSetAttachment]) -> list[dict]:
    summaries: list[dict] = []
    for attachment in attachments:
        metadata = attachment.metadata_json or {}
        if not isinstance(metadata, dict):
            continue
        ocr = metadata.get("ocr") if isinstance(metadata.get("ocr"), dict) else {}
        attachment_label = metadata.get("remidio_report_type") or attachment.original_filename or attachment.asset_kind
        dr_report = ocr.get("dr_report") if isinstance(ocr.get("dr_report"), dict) else None
        if dr_report:
            dr_data = dr_report.get("dr_data") if isinstance(dr_report.get("dr_data"), dict) else {}
            summaries.append(
                {
                    "kind": "DR",
                    "disease_code": "dr",
                    "attachment_label": attachment_label,
                    "result": dr_data.get("result") or "",
                    "qualitative_result": dr_data.get("qualitative_result") or "",
                    "metrics": [],
                }
            )
        amd_report = ocr.get("amd_report") if isinstance(ocr.get("amd_report"), dict) else None
        if amd_report:
            amd_data = amd_report.get("amd_data") if isinstance(amd_report.get("amd_data"), dict) else {}
            summaries.append(
                {
                    "kind": "AMD",
                    "disease_code": "amd",
                    "attachment_label": attachment_label,
                    "result": amd_data.get("result") or "",
                    "qualitative_result": amd_data.get("qualitative_result") or "",
                    "metrics": [],
                }
            )
        glaucoma_report = ocr.get("glaucoma_report") if isinstance(ocr.get("glaucoma_report"), dict) else None
        if glaucoma_report:
            glaucoma_data = glaucoma_report.get("glaucoma_data") if isinstance(glaucoma_report.get("glaucoma_data"), dict) else {}
            metrics = []
            if glaucoma_data.get("vcdr_right"):
                metrics.append({"label": "VCDR OD", "value": glaucoma_data.get("vcdr_right")})
            if glaucoma_data.get("vcdr_left"):
                metrics.append({"label": "VCDR OS", "value": glaucoma_data.get("vcdr_left")})
            summaries.append(
                {
                    "kind": "Glaucoma",
                    "disease_code": "glaucoma",
                    "attachment_label": attachment_label,
                    "result": glaucoma_data.get("result") or "",
                    "qualitative_result": glaucoma_data.get("qualitative_result") or "",
                    "metrics": metrics,
                }
            )
    return summaries


def _encounter_set_verification_profile(db, encounter: PatientEncounters) -> dict:
    """Return the EncounterSetType/profile contract used by verification UI."""
    profile_config = _active_encounter_set_type_config(encounter)
    encounter_set_type = profile_config.encounter_set_type if profile_config else None
    fields = _metadata_fields_by_display_order(
        (encounter_set_type.metadata_schema_json or {}).get("fields", []) if encounter_set_type else []
    )
    routing_field_keys = {
        field.key for field in required_image_task_routing_fields(profile_config)
    }
    fields = [
        {**field, "required_for_task_routing": field["key"] in routing_field_keys}
        for field in fields
    ]
    image_schemes = []
    if profile_config:
        image_schemes = [
            {
                "name": scheme.disease.name if scheme.disease else f"Disease #{scheme.disease_id}",
                "is_default": scheme.is_default or scheme.disease_id == profile_config.default_image_grading_scheme_id,
            }
            for scheme in sorted(
                [scheme for scheme in profile_config.image_grading_schemes if scheme.active],
                key=lambda item: (item.display_order, item.disease.name if item.disease else "", item.disease_id),
            )
        ]
    positive_disease_options = list_project_positive_disease_options(
        db,
        project_id=encounter.project_id,
    )
    selected_positive_diseases, _invalid_values = canonicalize_project_positive_diseases(
        db,
        project_id=encounter.project_id,
        values=list(encounter.referral_positive_diseases_json or []),
    )
    return {
        "encounter_set_type": encounter_set_type,
        "profile_config": profile_config,
        "metadata_fields": fields,
        "fields_by_scope": {
            scope: [field for field in fields if field["scope"] == scope]
            for scope in ("patient", "encounter", "image", "document", "upload")
        },
        "editable_fields_by_scope": {
            scope: [
                field for field in fields
                if field["scope"] == scope and field.get("editable_during_verification")
            ]
            for scope in ("patient", "encounter", "image", "document", "upload")
        },
        "asset_rules": encounter_set_type.asset_rules_json if encounter_set_type else {},
        "image_grading_schemes": image_schemes,
        "encounter_grading_scheme": profile_config.encounter_grading_scheme if profile_config else None,
        "default_image_grading_scheme": profile_config.default_image_grading_scheme if profile_config else None,
        "positive_disease_options": [
            {
                "disease_id": option.disease_id,
                "name": option.name,
                "selected": option.name in selected_positive_diseases,
            }
            for option in positive_disease_options
        ],
    }


def _active_encounter_set_type_config(encounter: PatientEncounters) -> UploadProfileEncounterSetType | None:
    if not encounter.upload_profile:
        return None
    active_configs = [
        config
        for config in encounter.upload_profile.encounter_set_types
        if config.active and config.encounter_set_type and config.encounter_set_type.active
    ]
    if not active_configs:
        return None
    if len(active_configs) == 1:
        return active_configs[0]
    metadata = encounter.metadata_json or {}
    type_id = metadata.get("encounter_set_type_id")
    if type_id:
        for config in active_configs:
            if config.encounter_set_type_id == type_id:
                return config
    return active_configs[0]


def _verification_validation_response(message: str, *, encounter_uuid: str, status: int = 400):
    if request.headers.get("X-EncounterSet-Async") == "1":
        return jsonify({
            "success": False,
            "message": message,
            "redirect_url": url_for(
                "verify_encounter_set.verify_encounter",
                uuid=encounter_uuid,
            ),
        }), status
    flash(message, "warning")
    return redirect(url_for("verify_encounter_set.verify_encounter", uuid=encounter_uuid))


def _missing_routing_metadata_response(missing_fields, *, image_count: int = 1):
    labels = [field.label for field in missing_fields]
    label_text = ", ".join(labels)
    if image_count == 1:
        message = f"Select {label_text} before marking this image reviewed."
    else:
        message = (
            f"Cannot complete this action: {image_count} applicable image(s) are missing "
            f"required task-routing metadata: {label_text}."
        )
    return jsonify({
        "success": False,
        "message": message,
        "missing_fields": [field.key for field in missing_fields],
    }), 409


def _metadata_fields_by_display_order(fields: list[dict]) -> list[dict]:
    normalized = [field for field in fields if isinstance(field, dict) and field.get("key") and field.get("scope")]
    return sorted(
        normalized,
        key=lambda field: (
            field.get("scope") or "",
            int(field.get("display_order") or 0),
            field.get("label") or field.get("key") or "",
        ),
    )


def _metadata_form_value(form, name: str, field: dict):
    field_type = field.get("type")
    if field_type == "boolean":
        if f"__present__{name}" in form and form.get(name) in {None, "", "0", "false", "False"}:
            return False
        return name in form
    if field_type == "select" and field.get("selection_mode") == "multiple":
        return [value for value in form.getlist(name) if value != ""]
    value = form.get(name)
    if value == "":
        return None
    return value


def _metadata_form_field_present(form, name: str) -> bool:
    return name in form or f"__present__{name}" in form


def _set_nested_metadata_value(metadata: dict, path: tuple[str, ...], value):
    target = metadata
    for key in path[:-1]:
        child = target.get(key)
        if not isinstance(child, dict):
            child = {}
            target[key] = child
        target = child
    target[path[-1]] = value


def _sync_attachment_ocr_clinical_reports(db, attachment: EncounterSetAttachment) -> None:
    metadata = attachment.metadata_json or {}
    ocr = metadata.get("ocr") if isinstance(metadata.get("ocr"), dict) else {}
    dr_report = ocr.get("dr_report") if isinstance(ocr.get("dr_report"), dict) else {}
    dr_data = dr_report.get("dr_data") if isinstance(dr_report.get("dr_data"), dict) else {}
    dr_report_id = dr_report.get("diabetic_retinopathy_report_id")
    if dr_report_id:
        row = db.get(DiabeticRetinopathyReport, dr_report_id)
        if row is not None:
            row.result = dr_data.get("result") or ""
            row.qualitative_result = dr_data.get("qualitative_result") or None

    amd_report = ocr.get("amd_report") if isinstance(ocr.get("amd_report"), dict) else {}
    amd_data = amd_report.get("amd_data") if isinstance(amd_report.get("amd_data"), dict) else {}
    amd_report_id = amd_report.get("amd_report_id")
    if amd_report_id:
        row = db.get(AMDReport, amd_report_id)
        if row is not None:
            row.result = amd_data.get("result") or None
            row.qualitative_result = amd_data.get("qualitative_result") or None

    glaucoma_report = ocr.get("glaucoma_report") if isinstance(ocr.get("glaucoma_report"), dict) else {}
    glaucoma_data = glaucoma_report.get("glaucoma_data") if isinstance(glaucoma_report.get("glaucoma_data"), dict) else {}
    glaucoma_report_id = glaucoma_report.get("glaucoma_report_id")
    if glaucoma_report_id:
        row = db.get(GlaucomaReport, glaucoma_report_id)
        if row is not None:
            row.result = glaucoma_data.get("result") or ""
            row.qualitative_result = glaucoma_data.get("qualitative_result") or None
            row.vcdr_right = glaucoma_data.get("vcdr_right") or None
            row.vcdr_left = glaucoma_data.get("vcdr_left") or None

    cleaned_id = glaucoma_report.get("glaucoma_results_cleaned_id")
    if cleaned_id:
        cleaned = db.get(GlaucomaResultsCleaned, cleaned_id)
        if cleaned is not None:
            cleaned.result = glaucoma_data.get("result") or None
            cleaned.qualitative_result = glaucoma_data.get("qualitative_result") or None
            cleaned.original_vcdr_right = glaucoma_data.get("vcdr_right") or None
            cleaned.original_vcdr_left = glaucoma_data.get("vcdr_left") or None
            cleaned.vcdr_right_num = _parse_first_float(glaucoma_data.get("vcdr_right"))
            cleaned.vcdr_left_num = _parse_first_float(glaucoma_data.get("vcdr_left"))


def _parse_first_float(value) -> float | None:
    if value is None:
        return None
    import re

    match = re.search(r"\d+(?:\.\d+)?", str(value))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


@bp.route("/update_position", methods=["POST"])
@login_required
def update_position():
    """Update the spatial position of an image in an encounter set."""
    data = request.json
    image_uuid = data.get("image_uuid")
    new_position = data.get("position")
    
    if not image_uuid or new_position is None:
        return jsonify({"success": False, "message": "Missing image_uuid or position"}), 400
        
    try:
        new_position = int(new_position)
        if new_position < 1:
            raise ValueError()
    except ValueError:
        return jsonify({"success": False, "message": "Position must be a positive integer"}), 400

    from encounter_sets.position_service import PositionMutationError, move_encounter_set_image
    try:
        with transaction_scope() as db:
            move_encounter_set_image(
                db, user=current_user, image_uuid=image_uuid, new_position=new_position
            )
    except PositionMutationError as exc:
        return jsonify({"success": False, "message": str(exc)}), exc.status_code
    return jsonify({"success": True})

@bp.route("/exclude/<uuid>", methods=["POST"])
@login_required
def exclude_encounter_set(uuid):
    """Exclude an EncounterSet from verification and downstream task creation."""
    from auth.utils import utcnow

    with transaction_scope() as db:
        encounter_query = (
            db.query(PatientEncounters)
            .filter_by(uuid=uuid, is_set_based=True)
            .with_for_update()
        )
        encounter = _apply_verification_mutation_scope(encounter_query).first()
        if not encounter:
            abort(404)

        if encounter.encounter_verified_status == "verified":
            return _already_verified_response(encounter)

        payload = request.get_json(silent=True) or {}
        reason = (payload.get("reason") or request.form.get("reason") or "").strip()
        excluded_at = utcnow()
        metadata = dict(encounter.metadata_json or {})
        verification_metadata = dict(metadata.get("verification") or {})
        verification_metadata.update({
            "status": "excluded",
            "excluded": True,
            "excluded_by": current_user.username,
            "excluded_at": excluded_at.isoformat(),
        })
        if reason:
            verification_metadata["excluded_reason"] = reason
        metadata["verification"] = verification_metadata

        encounter.metadata_json = metadata
        encounter.encounter_verified_status = "excluded"
        encounter.encounter_verified_by = current_user.username
        encounter.encounter_verified_at = excluded_at

        next_uuid = _next_pending_encounter_uuid(db, encounter=encounter)
        redirect_url = (
            url_for("verify_encounter_set.verify_encounter", uuid=next_uuid)
            if next_uuid
            else _encounter_set_browser_url(encounter)
        )
        flash(f"Encounter set {encounter.name} excluded from verification.", "warning")
        if request.headers.get("X-EncounterSet-Async") == "1" or request.is_json:
            return jsonify({"success": True, "redirect_url": redirect_url})
        return redirect(redirect_url)


@bp.route("/reopen/<uuid>", methods=["POST"])
@login_required
def reopen_verification(uuid):
    """Reopen a verified EncounterSet for correction, if no grading has started."""
    from verify_encounter_set.models import EncounterVerificationHistory
    from verify_encounter_set.reopen_service import check_reopen_guard, snapshot_encounter

    with transaction_scope() as db:
        encounter_query = (
            db.query(PatientEncounters)
            .filter_by(uuid=uuid, is_set_based=True)
            .with_for_update()
        )
        encounter_query = role_scoped_rows(
            encounter_query,
            access_context(db, current_user),
            encounter_columns(PatientEncounters),
            lab_roles={"verifier"},
            project_roles={"verifier"},
            allow_admin=True,
        )
        encounter = encounter_query.first()
        if not encounter:
            abort(404)

        if encounter.encounter_verified_status != "verified":
            message = "Only a verified EncounterSet can be reopened."
            if request.headers.get("X-EncounterSet-Async") == "1" or request.is_json:
                return jsonify({"success": False, "message": message}), 409
            flash(message, "warning")
            return redirect(url_for("verify_encounter_set.verify_encounter", uuid=uuid))

        blockers = check_reopen_guard(db, encounter)
        if blockers:
            message = (
                f"Cannot reopen: {len(blockers)} grading task(s) already have grader "
                "progress. Reopening would destroy in-progress or completed grading work."
            )
            payload = {"success": False, "message": message, "blocking_tasks": blockers}
            if request.headers.get("X-EncounterSet-Async") == "1" or request.is_json:
                return jsonify(payload), 409
            flash(message, "danger")
            return redirect(url_for("verify_encounter_set.verify_encounter", uuid=uuid))

        before = snapshot_encounter(db, encounter)
        payload = request.get_json(silent=True) or {}
        reason = (payload.get("reason") or request.form.get("reason") or "").strip()

        # The guard above already proved zero *human* grading progress exists anywhere
        # on this encounter (state transitions and Grade rows with a human role_slot
        # are both human-only signals - see HUMAN_GRADE_ROLE_SLOTS), so it is safe to
        # delete every task/package and let a subsequent finalize rebuild from scratch.
        # _get_or_create_package_task is purely additive (it never removes a task for a
        # disease no longer selected) and _restore_frozen_runtime_config replays the
        # *original* frozen policy snapshot rather than recomputing from the corrected
        # selection - partial reconciliation would leave stale/orphaned tasks if the
        # correction changes which diseases are positive. Deleting AI inference results
        # and any 'ai'-role Grade rows for these tasks (via ON DELETE CASCADE on
        # AIInferenceRun.task_id and Grade.task_id) is intentional: AI grading is
        # automated and cheap to re-run, unlike human grader work.
        stale_tasks = db.query(GradingTask).filter(
            or_(
                GradingTask.patient_encounter_id == encounter.id,
                GradingTask.encounter_set_image_id.in_(
                    select(EncounterSetImage.id).where(
                        EncounterSetImage.patient_encounter_id == encounter.id
                    )
                ),
            )
        ).all()
        for task in stale_tasks:
            db.delete(task)
        packages = (
            db.query(EncounterSetGradingPackage)
            .filter_by(patient_encounter_id=encounter.id)
            .all()
        )
        for package in packages:
            db.delete(package)

        # enqueue_automatic_encounters() (remote_inference/encounter_service.py) treats
        # any EncounterAIInferenceRun in these statuses as "already handled" and skips
        # re-queuing. That row is a durable request/response record, not deleted like
        # the per-task rows above, but its now-orphaned success/queued status would
        # silently prevent re-finalize from ever regenerating the AI grading this
        # reopen just deleted. 'failed' is the existing retry-eligible status
        # (dr_dme_service.py already retries a run in this state) and satisfies the
        # ck_encounter_ai_run_source status CheckConstraint.
        from remote_inference.models import EncounterAIInferenceRun

        stale_ai_runs = db.query(EncounterAIInferenceRun).filter(
            EncounterAIInferenceRun.patient_encounter_id == encounter.id,
            EncounterAIInferenceRun.status.in_(
                ("queued", "presigning", "uploading", "submitting", "success", "partial")
            ),
        ).all()
        for ai_run in stale_ai_runs:
            ai_run.status = "failed"
            ai_run.error_code = "reopened_for_correction"
            ai_run.error_message = (
                f"Superseded: EncounterSet reopened for correction by {current_user.username} "
                f"on {utcnow().isoformat()}; grading tasks were deleted and will be regenerated "
                "on re-finalize."
            )

        metadata = dict(encounter.metadata_json or {})
        verification_metadata = dict(metadata.get("verification") or {})
        verification_metadata["reopened"] = True
        verification_metadata["reopened_by"] = current_user.username
        verification_metadata["reopened_at"] = utcnow().isoformat()
        metadata["verification"] = verification_metadata
        encounter.metadata_json = metadata
        encounter.encounter_verified_status = "pending"
        encounter.encounter_verified_by = None
        encounter.encounter_verified_at = None
        db.flush()

        after = snapshot_encounter(db, encounter)
        db.add(EncounterVerificationHistory(
            patient_encounter_id=encounter.id,
            action_type="reopened",
            actor_user_id=current_user.id,
            before_json=before,
            after_json=after,
            note=reason or None,
        ))

        assignees = before.get("grading_package_assignees") or []
        redirect_url = url_for("verify_encounter_set.verify_encounter", uuid=uuid)
        message = f"Encounter set {encounter.name} reopened for correction."
        if assignees:
            message += f" Grader assignment(s) cleared and need reassignment: {', '.join(assignees)}."
        flash(message, "warning")
        if request.headers.get("X-EncounterSet-Async") == "1" or request.is_json:
            return jsonify({"success": True, "redirect_url": redirect_url})
        return redirect(redirect_url)


@bp.route("/finalize/<uuid>", methods=["POST"])
@login_required
def finalize_verification(uuid):
    """Mark an encounter set as verified and trigger task creation."""
    from auth.utils import utcnow
    # Potential task creation import
    # from tasks.taskCreationServices import create_grading_task_for_encounter_set

    with transaction_scope() as db:
        # P0.5: Use row-level locking for atomic finalization
        # Lock the encounter for update (prevents concurrent modifications)
        encounter_query = (
            db.query(PatientEncounters)
            .filter_by(uuid=uuid, is_set_based=True)
            .with_for_update()
        )
        encounter = _apply_verification_mutation_scope(encounter_query).first()

        if not encounter:
            abort(404)

        if encounter.encounter_verified_status == "verified":
            return _already_verified_response(encounter)

        # Lock all images while checking (atomic transaction)
        images = db.query(EncounterSetImage)\
            .filter_by(patient_encounter_id=encounter.id)\
            .with_for_update()\
            .all()

        profile_config = _active_encounter_set_type_config(encounter)
        required_routing_fields = required_image_task_routing_fields(profile_config)
        routing_violations = [
            {
                "image_uuid": image.uuid,
                "spatial_position": image.spatial_position,
                "missing_fields": [field.key for field in missing],
            }
            for image in images
            if (missing := missing_image_task_routing_fields(image, profile_config))
        ]
        if routing_violations:
            missing_field_keys = {
                field_key
                for violation in routing_violations
                for field_key in violation["missing_fields"]
            }
            missing_routing_fields = tuple(
                field for field in required_routing_fields if field.key in missing_field_keys
            )
            labels = ", ".join(field.label for field in missing_routing_fields)
            message = (
                f"Cannot finalize: {len(routing_violations)} applicable image(s) are missing "
                f"required task-routing metadata: {labels}. Complete image metadata before verification."
            )
            if request.headers.get("X-EncounterSet-Async") == "1":
                return jsonify({
                    "success": False,
                    "message": message,
                    "missing_fields": [field.key for field in missing_routing_fields],
                    "images": routing_violations,
                    "redirect_url": url_for("verify_encounter_set.verify_encounter", uuid=uuid),
                }), 409
            flash(message, "warning")
            return redirect(url_for("verify_encounter_set.verify_encounter", uuid=uuid))

        # Check all images are reviewed (safe - images are locked)
        unreviewed_count = sum(1 for img in images if not img.is_reviewed)

        if unreviewed_count > 0:
            message = f"Cannot finalize: {unreviewed_count} image(s) not yet reviewed. Please review all images before verifying."
            if request.headers.get("X-EncounterSet-Async") == "1":
                return jsonify({
                    "success": False,
                    "message": message,
                    "redirect_url": url_for("verify_encounter_set.verify_encounter", uuid=uuid),
                }), 409
            flash(message, "warning")
            return redirect(url_for("verify_encounter_set.verify_encounter", uuid=uuid))

        # Preserve an explicit verifier decision. OCR is only the fallback when
        # no referral decision has been stored yet.
        if normalize_referral_suggestion(encounter.referral_suggestion) == "missing":
            update_encounter_referral_suggestion_from_attachments(
                db,
                encounter.id,
                preserve_existing_when_missing=True,
            )

        if encounter.referral_suggestion == "yes":
            canonical_diseases, invalid_diseases = canonicalize_project_positive_diseases(
                db,
                project_id=encounter.project_id,
                values=list(encounter.referral_positive_diseases_json or []),
            )
            if invalid_diseases or not canonical_diseases:
                return _verification_validation_response(
                    "Cannot finalize: select at least one positive disease from this project's "
                    "grading or referral disease options for a referral-positive EncounterSet.",
                    encounter_uuid=encounter.uuid,
                    status=409,
                )
            encounter.referral_positive_diseases_json = list(canonical_diseases)
        elif encounter.referral_suggestion == "no":
            encounter.referral_positive_diseases_json = []

        was_reopened_for_correction = bool(
            (encounter.metadata_json or {}).get("verification", {}).get("reopened")
        )
        reverify_before = None
        if was_reopened_for_correction:
            from verify_encounter_set.reopen_service import snapshot_encounter

            reverify_before = snapshot_encounter(db, encounter)

        # Finalize (atomic - encounter and images locked until commit)
        encounter.encounter_verified_status = 'verified'
        encounter.encounter_verified_by = current_user.username
        encounter.encounter_verified_at = utcnow()

        if was_reopened_for_correction:
            from verify_encounter_set.models import EncounterVerificationHistory
            from verify_encounter_set.reopen_service import snapshot_encounter

            metadata = dict(encounter.metadata_json or {})
            verification_metadata = dict(metadata.get("verification") or {})
            verification_metadata["reopened"] = False
            metadata["verification"] = verification_metadata
            encounter.metadata_json = metadata
            db.flush()
            db.add(EncounterVerificationHistory(
                patient_encounter_id=encounter.id,
                action_type="reverified",
                actor_user_id=current_user.id,
                before_json=reverify_before,
                after_json=snapshot_encounter(db, encounter),
            ))

        created_tasks = _create_verified_encounter_set_tasks(db, encounter)
        wadhwani_task_ids = create_wadhwani_task_ids_for_encounter(db, encounter, trigger_timing="after_verification")
        if wadhwani_task_ids:
            _enqueue_wadhwani_after_commit(
                tuple(wadhwani_task_ids),
                user_id=current_user.id,
                username=current_user.username,
                remote_addr=request.remote_addr,
                lab_unit_id=encounter.lab_unit_id,
                project_id=encounter.project_id,
                upload_profile_id=encounter.upload_profile_id,
            )
        _enqueue_madhunetra_after_commit(encounter.id, user_id=current_user.id)
        close_url = _encounter_set_browser_url(encounter)
        next_uuid = _next_pending_encounter_uuid(db, encounter=encounter)

        task_message = f" Created {created_tasks} grading task(s)." if created_tasks else ""
        flash(f"Encounter set {encounter.name} verified successfully.{task_message}", "success")
        if request.form.get("after") == "next" and next_uuid:
            redirect_url = url_for("verify_encounter_set.verify_encounter", uuid=next_uuid)
        else:
            redirect_url = close_url
        if request.headers.get("X-EncounterSet-Async") == "1":
            return jsonify({"success": True, "redirect_url": redirect_url})
        response = redirect(redirect_url)
        response.headers["X-EncounterSet-Verified"] = "1"
        return response


def _already_verified_response(encounter: PatientEncounters):
    message = "This EncounterSet is already verified and is read-only."
    if request.headers.get("X-EncounterSet-Async") == "1" or request.is_json:
        return _already_verified_json_response(encounter)
    flash(message, "warning")
    return redirect(
        url_for("verify_encounter_set.verify_encounter", uuid=encounter.uuid)
    )


def _already_verified_json_response(encounter: PatientEncounters):
    return jsonify({
        "success": False,
        "message": "This EncounterSet is already verified and is read-only.",
        "redirect_url": url_for(
            "verify_encounter_set.verify_encounter",
            uuid=encounter.uuid,
        ),
    }), 409


def _encounter_set_browser_url(encounter: PatientEncounters) -> str:
    params = {}
    if encounter.project_id:
        params["project_id"] = encounter.project_id
    capture_date = encounter.capture_date_dt
    if capture_date is None and encounter.capture_date:
        from datetime import datetime
        try:
            capture_date = datetime.strptime(str(encounter.capture_date), "%Y-%m-%d").date()
        except ValueError:
            capture_date = None
    if capture_date:
        params["month"] = capture_date.strftime("%Y-%m")
        params["date"] = capture_date.isoformat()
    params["encounter_id"] = encounter.id
    return url_for("remidio_api_uploads.encounter_set_browser", **params)


def _next_pending_encounter_uuid(db, *, encounter: PatientEncounters) -> str | None:
    query = db.query(PatientEncounters).filter(
        PatientEncounters.is_set_based == True,
        PatientEncounters.id != encounter.id,
        or_(
            PatientEncounters.encounter_verified_status == 'pending',
            PatientEncounters.encounter_verified_status.is_(None),
        ),
    )
    if encounter.project_id:
        query = query.filter(PatientEncounters.project_id == encounter.project_id)
    if encounter.capture_date_dt:
        query = query.filter(PatientEncounters.capture_date_dt == encounter.capture_date_dt)
    query = _apply_verification_scope(query)
    ordered = query.order_by(
        PatientEncounters.name.asc(),
        PatientEncounters.patient_id.asc(),
        PatientEncounters.id.asc(),
    ).all()
    current_key = (
        encounter.name or "",
        encounter.patient_id or "",
        encounter.id,
    )
    next_encounter = next(
        (
            candidate for candidate in ordered
            if (candidate.name or "", candidate.patient_id or "", candidate.id) > current_key
        ),
        None,
    )
    if next_encounter is None and ordered:
        next_encounter = ordered[0]
    return next_encounter.uuid if next_encounter else None


def _create_verified_encounter_set_tasks(
    db,
    encounter: PatientEncounters,
    *,
    create_negative_controls: bool = True,
    adopt_unscoped_task_ids: frozenset[int] | None = None,
) -> int:
    """Create package-scoped grading tasks for a verified EncounterSet."""
    if encounter.encounter_verified_status == "excluded":
        return 0

    config = _active_encounter_set_type_config(encounter)
    images = (
        db.query(EncounterSetImage)
        .filter(EncounterSetImage.patient_encounter_id == encounter.id)
        .order_by(EncounterSetImage.spatial_position)
        .all()
    )
    eligible_images = [
        image for image in images
        if image.asset_kind == "clinical_image"
        and image.creates_task
        and image.visible_to_grader
        and image.is_reviewed
        and not image.is_not_gradable
    ]
    report_evidence = _encounter_set_report_evidence(encounter)
    package_configs = _encounter_set_package_configs(db, config, encounter)

    created = 0
    for package_config in package_configs:
        existing_package = (
            db.query(EncounterSetGradingPackage)
            .filter(
                EncounterSetGradingPackage.patient_encounter_id == encounter.id,
                EncounterSetGradingPackage.code == package_config["code"],
            )
            .first()
        )
        if existing_package is not None:
            _restore_frozen_runtime_config(existing_package, package_config)
        sampling_scheme_ids = {
            disease_id
            for disease_id, policy in package_config["image_scheme_policies"].items()
            if policy == "positive_plus_negative_controls"
        }
        # Check every sampling-gated disease's own positivity independently - a linked
        # child (for example DME) must be able to trigger task creation on its own, not
        # only when the root (DR) is separately marked positive.
        positive_control_scheme_ids = sorted(
            disease_id
            for disease_id in sampling_scheme_ids
            if _encounter_is_positive_for_disease(db, encounter, disease_id)
        )
        image_scheme_ids = sorted(
            {
                disease_id
                for disease_id, policy in package_config["image_scheme_policies"].items()
                if _image_scheme_policy_applies(policy, report_evidence)
            }
        ) + positive_control_scheme_ids
        image_scheme_ids = sorted(set(image_scheme_ids))
        root_scope_disease_id = package_config.get("root_scope_disease_id")
        if package_config["grading_mode"] == "disease_specific" and (
            root_scope_disease_id in image_scheme_ids or positive_control_scheme_ids
        ):
            # Linked scopes are one allocation unit. If any disease in the package
            # applies - the root (DR) or a linked child (DME) - every linked image
            # scheme is created for the same constituent images.
            image_scheme_ids = sorted({
                disease_id
                for scope in package_config["scopes"]
                for disease_id in scope["image_grading_scheme_ids"]
            })
        encounter_scheme_ids = sorted(set(package_config["encounter_scheme_ids"]))
        if sampling_scheme_ids and not image_scheme_ids:
            # A sampled negative remains dormant until a positive EncounterSet
            # explicitly selects it as a control. Do not expose an orphaned
            # encounter-only package while its image tasks are deferred.
            continue
        if not encounter_scheme_ids and (not image_scheme_ids or not eligible_images):
            continue

        package = _get_or_create_runtime_package(db, encounter, package_config)
        if package_config.get("_created"):
            created += 1
            package_config.pop("_created", None)

        scope_by_encounter_scheme_id = {
            scope["encounter_grading_scheme_id"]: scope
            for scope in package_config["scopes"]
        }
        for disease_id in encounter_scheme_ids:
            scope = scope_by_encounter_scheme_id[disease_id]
            if _get_or_create_package_task(
                db,
                package=package,
                encounter=encounter,
                disease_id=disease_id,
                target_level="encounter",
                source=package_config["source"],
                scope=_runtime_scope(package, scope),
                adopt_unscoped_task_ids=adopt_unscoped_task_ids,
            ):
                created += 1

        for image in eligible_images:
            for disease_id in image_scheme_ids:
                scope = next(
                    scope
                    for scope in package_config["scopes"]
                    if disease_id in scope["image_grading_scheme_ids"]
                )
                routing_disease_id = (
                    package_config.get("root_scope_disease_id")
                    if package_config["grading_mode"] == "disease_specific"
                    else disease_id
                ) or disease_id
                if not image_metadata_matches_rule(
                    image.metadata_json,
                    package_config["image_scheme_metadata_rules"].get(routing_disease_id),
                ):
                    continue
                if _get_or_create_package_task(
                    db,
                    package=package,
                    encounter=encounter,
                    disease_id=disease_id,
                    target_level="image",
                    source=package_config["source"],
                    image=image,
                    scope=_runtime_scope(package, scope),
                    adopt_unscoped_task_ids=adopt_unscoped_task_ids,
                ):
                    created += 1
        if create_negative_controls:
            for disease_id in positive_control_scheme_ids:
                created += _create_negative_control_tasks_for_positive(
                    db,
                    positive_encounter=encounter,
                    disease_id=disease_id,
                    package_config=package_config,
                    controls_per_positive=package_config[
                        "image_scheme_negative_controls_per_positive"
                    ].get(disease_id, 0),
                )
    if created:
        db.flush()
    return created


def _encounter_set_report_evidence(encounter: PatientEncounters) -> set[str]:
    evidence: set[str] = set()
    for attachment in encounter.encounter_set_attachments or []:
        metadata = attachment.metadata_json or {}
        report_type = str(metadata.get("remidio_report_type") or attachment.asset_kind or "").lower()
        ocr = metadata.get("ocr") if isinstance(metadata.get("ocr"), dict) else {}
        if "dr" in report_type or isinstance(ocr.get("dr_report"), dict):
            evidence.add("dr")
        if "amd" in report_type or isinstance(ocr.get("amd_report"), dict):
            evidence.add("amd")
        if "glaucoma" in report_type or isinstance(ocr.get("glaucoma_report"), dict):
            evidence.add("glaucoma")
    return evidence


def _image_scheme_policy_applies(policy: str, evidence: set[str]) -> bool:
    if policy == "always":
        return True
    if policy == "never":
        return False
    if policy == "remidio_dr_report_present":
        return "dr" in evidence
    if policy == "remidio_amd_report_present":
        return "amd" in evidence
    if policy == "remidio_glaucoma_report_present":
        return "glaucoma" in evidence
    if policy == "positive_plus_negative_controls":
        return False
    return False


def _create_negative_control_tasks_for_positive(
    db,
    *,
    positive_encounter: PatientEncounters,
    disease_id: int,
    package_config: dict,
    controls_per_positive: int,
    candidate_encounter_ids: tuple[int, ...] | None = None,
) -> int:
    controls_per_positive = max(0, min(20, int(controls_per_positive or 0)))
    if controls_per_positive <= 0:
        return 0
    config = _active_encounter_set_type_config(positive_encounter)
    if not config:
        return 0
    candidate_query = db.query(PatientEncounters).filter(
        PatientEncounters.id != positive_encounter.id,
        PatientEncounters.is_set_based.is_(True),
        PatientEncounters.encounter_verified_status == "verified",
        PatientEncounters.lab_unit_id == positive_encounter.lab_unit_id,
        PatientEncounters.project_id == positive_encounter.project_id,
        PatientEncounters.upload_profile_id == positive_encounter.upload_profile_id,
    )
    if candidate_encounter_ids is None:
        candidates = (
            candidate_query.order_by(func.random())
            .limit(controls_per_positive * 4)
            .all()
        )
    else:
        candidates = (
            candidate_query.filter(
                PatientEncounters.id.in_(candidate_encounter_ids)
            )
            .order_by(PatientEncounters.id)
            .all()
        )
    created = 0
    selected = 0
    for candidate in candidates:
        if selected >= controls_per_positive:
            break
        candidate_config = _active_encounter_set_type_config(candidate)
        if not candidate_config or candidate_config.encounter_set_type_id != config.encounter_set_type_id:
            continue
        if not _encounter_is_negative_for_disease(db, candidate, disease_id):
            continue
        if _encounter_has_incompatible_runtime_package(
            db,
            candidate_id=candidate.id,
            package_config=package_config,
        ):
            continue
        eligible_images = _eligible_encounter_set_images(db, candidate)
        matching_images = [
            image
            for image in eligible_images
            if image_metadata_matches_rule(
                image.metadata_json,
                package_config["image_scheme_metadata_rules"].get(disease_id),
            )
        ]
        if not matching_images:
            continue
        if _encounter_has_negative_control_tasks(db, candidate.id, disease_id):
            continue
        package = _get_or_create_runtime_package(db, candidate, package_config)
        selected += 1
        if package_config.get("_created"):
            created += 1
            package_config.pop("_created", None)
        for encounter_scheme_id in sorted(set(package_config.get("encounter_scheme_ids", []))):
            scope_config = next(
                scope
                for scope in package_config["scopes"]
                if scope["encounter_grading_scheme_id"] == encounter_scheme_id
            )
            if _get_or_create_package_task(
                db,
                package=package,
                encounter=candidate,
                disease_id=encounter_scheme_id,
                target_level="encounter",
                source="profile_package_negative_control",
                scope=_runtime_scope(package, scope_config),
            ):
                created += 1
        image_disease_ids = (
            {
                scope_disease_id
                for scope in package_config["scopes"]
                for scope_disease_id in scope["image_grading_scheme_ids"]
            }
            if package_config["grading_mode"] == "disease_specific"
            and disease_id == package_config.get("root_scope_disease_id")
            else {disease_id}
        )
        for image in matching_images:
            for image_disease_id in image_disease_ids:
                scope_config = next(
                    scope
                    for scope in package_config["scopes"]
                    if image_disease_id in scope["image_grading_scheme_ids"]
                )
                if _get_or_create_package_task(
                    db,
                    package=package,
                    encounter=candidate,
                    disease_id=image_disease_id,
                    target_level="image",
                    source="profile_package_negative_control",
                    scope=_runtime_scope(package, scope_config),
                    image=image,
                ):
                    created += 1
    return created


def _encounter_has_incompatible_runtime_package(
    db,
    *,
    candidate_id: int,
    package_config: dict,
) -> bool:
    existing = (
        db.query(EncounterSetGradingPackage)
        .filter(
            EncounterSetGradingPackage.patient_encounter_id == candidate_id,
            EncounterSetGradingPackage.code == package_config["code"],
        )
        .first()
    )
    if existing is None:
        return False
    return (
        existing.upload_profile_est_grading_package_id
        != package_config.get("config_id")
    )


def _encounter_has_negative_control_tasks(db, encounter_id: int, disease_id: int) -> bool:
    return db.query(GradingTask.id).outerjoin(
        EncounterSetImage,
        GradingTask.encounter_set_image_id == EncounterSetImage.id,
    ).filter(
        GradingTask.task_source == "profile_package_negative_control",
        GradingTask.disease_id == disease_id,
        or_(
            GradingTask.patient_encounter_id == encounter_id,
            EncounterSetImage.patient_encounter_id == encounter_id,
        ),
    ).first() is not None


def _eligible_encounter_set_images(db, encounter: PatientEncounters) -> list[EncounterSetImage]:
    return [
        image
        for image in (
            db.query(EncounterSetImage)
            .filter(EncounterSetImage.patient_encounter_id == encounter.id)
            .order_by(EncounterSetImage.spatial_position)
            .all()
        )
        if image.asset_kind == "clinical_image"
        and image.creates_task
        and image.visible_to_grader
        and image.is_reviewed
        and not image.is_not_gradable
    ]


def _encounter_is_positive_for_disease(db, encounter: PatientEncounters, disease_id: int) -> bool:
    if encounter.referral_suggestion != "yes":
        return False
    positive_diseases = encounter.referral_positive_diseases_json or []
    if not positive_diseases:
        return False
    disease = db.get(Disease, disease_id)
    return bool(disease and _positive_disease_list_matches(disease, positive_diseases))


def _encounter_is_negative_for_disease(db, encounter: PatientEncounters, disease_id: int) -> bool:
    if encounter.referral_suggestion == "no":
        return True
    if encounter.referral_suggestion != "yes":
        return False
    positive_diseases = encounter.referral_positive_diseases_json or []
    if not positive_diseases:
        return False
    disease = db.get(Disease, disease_id)
    return bool(disease and not _positive_disease_list_matches(disease, positive_diseases))


def _positive_disease_list_matches(disease: Disease, positive_diseases: list[str]) -> bool:
    values = [str(value or "").strip().lower() for value in positive_diseases if str(value or "").strip()]
    linkage = (disease.remidio_ocr_linkage or "none").lower()
    if linkage == "dr":
        return any(value == "dr" or "diabetic retinopathy" in value for value in values)
    if linkage == "amd":
        return any("amd" in value.split() or "macular degeneration" in value for value in values)
    if linkage == "glaucoma":
        return any("glaucoma" in value for value in values)
    disease_name = disease.name.lower()
    return any(value == disease_name or value in disease_name or disease_name in value for value in values)


def _enqueue_wadhwani_after_commit(
    task_ids: tuple[int, ...],
    *,
    user_id: int,
    username: str,
    remote_addr: str | None,
    lab_unit_id: int | None,
    project_id: int | None,
    upload_profile_id: int | None,
) -> None:
    @after_this_request
    def _enqueue(response):
        try:
            enqueue_wadhwani_for_task_ids(
                task_ids,
                user_id=user_id,
                username=username,
                remote_addr=remote_addr,
                lab_unit_id=lab_unit_id,
                project_id=project_id,
                upload_profile_id=upload_profile_id,
            )
        except Exception as exc:
            current_app.logger.exception("Failed to enqueue EncounterSet Wadhwani inference: %s", exc)
        return response


def _enqueue_madhunetra_after_commit(encounter_id: int, *, user_id: int) -> None:
    """Evaluate the completed EncounterSet after its verification commit."""
    @after_this_request
    def _enqueue(response):
        try:
            from remote_inference.encounter_service import enqueue_automatic_encounters

            enqueue_automatic_encounters([encounter_id], user_id=user_id)
        except Exception as exc:  # noqa: BLE001
            current_app.logger.exception("Failed to enqueue EncounterSet MadhuNetrAI inference: %s", exc)
        return response


def _encounter_set_package_configs(db, config: UploadProfileEncounterSetType | None, encounter: PatientEncounters) -> list[dict]:
    if config and config.grading_packages:
        packages = []
        for package in sorted(
            [package for package in config.grading_packages if package.active],
            key=lambda item: (item.display_order, item.name, item.id),
        ):
            packages.append(
                _policy_config(
                    db,
                    package_policy_from_model(package),
                    encounter_set_type=config.encounter_set_type,
                )
            )
        if packages:
            return packages

    if config:
        image_scheme_ids = [scheme.disease_id for scheme in config.image_grading_schemes if scheme.active]
        encounter_scheme_ids = [config.encounter_grading_scheme_id] if config.encounter_grading_scheme_id else []
        if len(encounter_scheme_ids) != 1:
            return []
        policy = EncounterSetPackagePolicyDTO(
            config_id=None,
            name="Default",
            code="default",
            applicability="always",
            grading_mode="unified",
            policy_revision=None,
            root_scope_disease_id=None,
            scopes=(EncounterSetScopePolicyDTO(
                scope_disease_id=None,
                image_grading_scheme_ids=tuple(image_scheme_ids),
                encounter_grading_scheme_id=encounter_scheme_ids[0],
                parent_scope_disease_id=None,
                link_role="unified",
            ),),
            image_scheme_policies={disease_id: "always" for disease_id in image_scheme_ids},
            image_scheme_negative_controls_per_positive={disease_id: 0 for disease_id in image_scheme_ids},
            image_scheme_metadata_rules={},
            source="profile_default",
        )
        return [
            _policy_config(
                db,
                policy,
                encounter_set_type=config.encounter_set_type,
            )
        ]

    target_disease_ids = {
        row[0]
        for row in db.query(PatientEncounterTargetDisease.disease_id)
        .filter(PatientEncounterTargetDisease.patient_encounter_id == encounter.id)
        .all()
    }
    if not target_disease_ids and encounter.disease_id:
        target_disease_ids = {encounter.disease_id}
    # The legacy fallback cannot express multiple independent set anchors.
    # Preserve its previous behavior only when the target is unambiguous.
    if len(target_disease_ids) != 1:
        return []
    encounter_scheme_id = next(iter(target_disease_ids))
    policy = EncounterSetPackagePolicyDTO(
        config_id=None,
        name="Default",
        code="default",
        applicability="always",
        grading_mode="unified",
        policy_revision=None,
        root_scope_disease_id=None,
        scopes=(EncounterSetScopePolicyDTO(
            scope_disease_id=None,
            image_grading_scheme_ids=(),
            encounter_grading_scheme_id=encounter_scheme_id,
            parent_scope_disease_id=None,
            link_role="unified",
        ),),
        image_scheme_policies={},
        image_scheme_negative_controls_per_positive={},
        image_scheme_metadata_rules={},
        source="legacy_target_disease",
    )
    return [_policy_config(db, policy)]


def _policy_config(
    db,
    policy: EncounterSetPackagePolicyDTO,
    *,
    encounter_set_type=None,
) -> dict:
    policy_snapshot = freeze_policy_snapshot(db, policy)
    if encounter_set_type is not None:
        policy_snapshot["encounter_set_type"] = {
            "id": encounter_set_type.id,
            "name": encounter_set_type.name,
            "code": encounter_set_type.code,
        }
    return {
        "config_id": policy.config_id,
        "name": policy.name,
        "code": policy.code,
        "applicability": policy.applicability,
        "grading_mode": policy.grading_mode,
        "policy_revision": policy.policy_revision,
        "root_scope_disease_id": policy.root_scope_disease_id,
        "policy_snapshot": policy_snapshot,
        "encounter_set_type_id": (
            encounter_set_type.id if encounter_set_type is not None else None
        ),
        "scopes": [
            {
                "scope_disease_id": scope.scope_disease_id,
                "image_grading_scheme_ids": list(scope.image_grading_scheme_ids),
                "encounter_grading_scheme_id": scope.encounter_grading_scheme_id,
                "parent_scope_disease_id": scope.parent_scope_disease_id,
                "link_role": scope.link_role,
            }
            for scope in policy.scopes
        ],
        "image_scheme_policies": dict(policy.image_scheme_policies),
        "image_scheme_negative_controls_per_positive": dict(
            policy.image_scheme_negative_controls_per_positive
        ),
        "image_scheme_metadata_rules": dict(policy.image_scheme_metadata_rules),
        "encounter_scheme_ids": [
            scope.encounter_grading_scheme_id for scope in policy.scopes
        ],
        "source": policy.source,
    }


def _get_or_create_runtime_package(db, encounter: PatientEncounters, package_config: dict) -> EncounterSetGradingPackage:
    package = (
        db.query(EncounterSetGradingPackage)
        .filter(
            EncounterSetGradingPackage.patient_encounter_id == encounter.id,
            EncounterSetGradingPackage.code == package_config["code"],
        )
        .first()
    )
    if package:
        if not package.grading_mode:
            package.grading_mode = package_config.get("grading_mode") or "unified"
        _restore_frozen_runtime_config(package, package_config)
        return package
    package = EncounterSetGradingPackage(
        patient_encounter_id=encounter.id,
        upload_profile_est_grading_package_id=package_config["config_id"],
        encounter_set_type_id=package_config.get("encounter_set_type_id"),
        name=package_config["name"],
        code=package_config["code"],
        applicability=package_config["applicability"],
        grading_mode=package_config.get("grading_mode") or "unified",
        root_scope_disease_id=package_config.get("root_scope_disease_id"),
        policy_schema_version=1,
        policy_revision=package_config.get("policy_revision"),
        policy_snapshot_json=package_config.get("policy_snapshot"),
        record_origin="native",
        state="pending",
        metadata_json={"source": package_config["source"], "grading_mode": package_config.get("grading_mode") or "unified"},
    )
    db.add(package)
    db.flush()
    _ensure_runtime_scopes(db, package, package_config)
    package_config["_created"] = True
    return package


def _restore_frozen_runtime_config(package, package_config: dict) -> None:
    """Make repeat task creation use the package snapshot, never current policy."""
    snapshot_package = (package.policy_snapshot_json or {}).get("package") or {}
    if snapshot_package:
        for key in (
            "applicability",
            "grading_mode",
            "root_scope_disease_id",
            "image_scheme_policies",
            "image_scheme_negative_controls_per_positive",
            "image_scheme_metadata_rules",
            "source",
        ):
            if key in snapshot_package:
                package_config[key] = snapshot_package[key]
        for key in (
            "image_scheme_policies",
            "image_scheme_negative_controls_per_positive",
            "image_scheme_metadata_rules",
        ):
            package_config[key] = {
                int(disease_id): value
                for disease_id, value in (package_config.get(key) or {}).items()
            }
    package_config["scopes"] = [
        dict(scope.scope_snapshot_json or {
            "scope_disease_id": scope.scope_disease_id,
            "image_grading_scheme_ids": (
                [scope.image_grading_scheme_id]
                if scope.image_grading_scheme_id is not None
                else []
            ),
            "encounter_grading_scheme_id": scope.encounter_grading_scheme_id,
            "parent_scope_disease_id": scope.parent_scope_disease_id,
            "link_role": scope.link_role,
        })
        for scope in package.scopes
    ]
    package_config["encounter_scheme_ids"] = [
        scope["encounter_grading_scheme_id"] for scope in package_config["scopes"]
    ]


def _ensure_runtime_scopes(db, package, package_config: dict) -> None:
    scopes_by_disease_id = {scope.scope_disease_id: scope for scope in package.scopes}
    for index, scope_config in enumerate(package_config["scopes"]):
        scope_disease_id = scope_config["scope_disease_id"]
        scope = scopes_by_disease_id.get(scope_disease_id)
        if scope is None:
            image_ids = scope_config["image_grading_scheme_ids"]
            scope = EncounterSetGradingScope(
                package=package,
                scope_disease_id=scope_disease_id,
                image_grading_scheme_id=image_ids[0] if len(image_ids) == 1 else None,
                encounter_grading_scheme_id=scope_config["encounter_grading_scheme_id"],
                parent_scope_disease_id=scope_config["parent_scope_disease_id"],
                link_role=scope_config["link_role"],
                state="pending",
                display_order=index,
                scope_snapshot_json=dict(scope_config),
            )
            db.add(scope)
            db.flush()
            scopes_by_disease_id[scope_disease_id] = scope


def _runtime_scope(
    package: EncounterSetGradingPackage, scope_config: dict
) -> EncounterSetGradingScope:
    scope_disease_id = scope_config["scope_disease_id"]
    return next(
        scope
        for scope in package.scopes
        if scope.scope_disease_id == scope_disease_id
    )


def _get_or_create_package_task(
    db,
    *,
    package: EncounterSetGradingPackage,
    encounter: PatientEncounters,
    disease_id: int,
    target_level: str,
    source: str,
    scope: EncounterSetGradingScope,
    image: EncounterSetImage | None = None,
    adopt_unscoped_task_ids: frozenset[int] | None = None,
) -> bool:
    filters = [
        GradingTask.disease_id == disease_id,
        GradingTask.grading_target_level == target_level,
    ]
    if target_level == "image":
        filters.append(GradingTask.encounter_set_image_id == image.id)
    else:
        filters.append(GradingTask.patient_encounter_id == encounter.id)
    existing = (
        db.query(GradingTask)
        .filter(
            *filters,
            GradingTask.encounter_set_package_id == package.id,
        )
        .first()
    )
    if existing:
        if existing.encounter_set_scope_id is None:
            existing.encounter_set_scope_id = scope.id
        return False

    # Compatibility: adopt one historical task only when it has never belonged
    # to any runtime package. A task owned by another package is never reused.
    unscoped_query = db.query(GradingTask).filter(
        *filters,
        GradingTask.encounter_set_package_id.is_(None),
    )
    if adopt_unscoped_task_ids is not None:
        if not adopt_unscoped_task_ids:
            unscoped_query = None
        else:
            unscoped_query = unscoped_query.filter(
                GradingTask.id.in_(adopt_unscoped_task_ids)
            )
    unscoped = unscoped_query.first() if unscoped_query is not None else None
    if unscoped:
        unscoped.encounter_set_package_id = package.id
        unscoped.encounter_set_scope_id = scope.id
        unscoped.grading_target_level = target_level
        unscoped.task_source = source
        if unscoped.source_upload_profile_id is None:
            unscoped.source_upload_profile_id = encounter.upload_profile_id
        return False

    task = GradingTask(
        encounter_set_package_id=package.id,
        encounter_set_scope_id=scope.id,
        disease_id=disease_id,
        lab_unit_id=encounter.lab_unit_id,
        source_upload_profile_id=encounter.upload_profile_id,
        state="pending",
        grading_target_level=target_level,
        task_source=source,
    )
    if target_level == "image":
        task.encounter_set_image_id = image.id
    else:
        task.patient_encounter_id = encounter.id
    db.add(task)
    return True


@bp.route("/edit/<uuid>", methods=["GET"])
@login_required
def edit_image(uuid):
    """Edit an encounter set image (crop/mask PII)."""
    from models import GradingTask
    from sqlalchemy import select

    with transaction_scope() as db:
        img = db.query(EncounterSetImage).filter_by(uuid=uuid).first()
        if not img:
            abort(404)

        # Query encounter and apply hospital scoping
        query = db.query(PatientEncounters).filter_by(id=img.patient_encounter_id)
        query = _apply_verification_scope(query)
        encounter = query.first()

        if not encounter:
            # Encounter not found or user doesn't have access
            abort(404)
        if encounter.encounter_verified_status == "verified":
            return _already_verified_response(encounter)

        # P1.3: Validate S3 config access (defense-in-depth)
        if img.s3_config_id:
            is_valid, error_msg = validate_s3_config_access(img, current_user, db)
            if not is_valid:
                abort(403)

        # Check if grading tasks exist - block editing if they do
        task_states = db.execute(
            select(GradingTask.state).where(GradingTask.patient_encounter_id == encounter.id)
        ).scalars().all()
        active_tasks = [s for s in task_states if s and s.lower() != 'pending']
        if active_tasks:
            flash(f"Editing blocked. Grading tasks already in progress: {', '.join(set(active_tasks))}.", "danger")
            return redirect(url_for("verify_encounter_set.verify_encounter", uuid=encounter.uuid))

        # Determine which image URL to load (edited or original)
        if img.edited_filename:
            image_url = url_for("media._encounterSetImageEditedByUUID", uuid_str=img.uuid)
        else:
            image_url = url_for("media._encounterSetImageByUUID", uuid_str=img.uuid)

        return render_template(
            "verify_encounter_set/edit_image.html",
            image=img,
            encounter=encounter,
            image_url=image_url,
            has_edited_version=bool(img.edited_filename)
        )


@bp.route("/save_edit/<uuid>", methods=["POST"])
@login_required
def save_edit(uuid):
    """Save edited image data (crop/mask coordinates applied)."""
    from pathlib import Path
    from models import BASE_DIR
    from utils.image_edit_payload import InvalidImageEditPayload, decode_image_edit_payload
    from utils.image_processing import generate_thumbnail, get_thumbnail_filename
    from utils.media_cache import bump_media_cache_version

    # P1.4: Validate request data
    data = request.json or {}
    schema = SaveEditRequestSchema()

    try:
        validated_data = schema.load(data)
    except ValidationError as e:
        return jsonify({
            "success": False,
            "message": "Invalid request data",
            "errors": e.messages
        }), 422

    with transaction_scope() as db:
        img = db.query(EncounterSetImage).filter_by(uuid=uuid).first()
        if not img:
            return jsonify({"success": False, "message": "Image not found"}), 404

        # Query encounter and apply hospital scoping
        query = db.query(PatientEncounters).filter_by(id=img.patient_encounter_id)
        query = _apply_verification_scope(query)
        encounter = query.first()

        if not encounter:
            # Encounter not found or user doesn't have access
            return jsonify({"success": False, "message": "Image not found"}), 404
        if encounter.encounter_verified_status == "verified":
            return _already_verified_json_response(encounter)

        missing_fields = missing_image_task_routing_fields(
            img,
            _active_encounter_set_type_config(encounter),
        )
        if missing_fields:
            return _missing_routing_metadata_response(missing_fields)

        if img.s3_config_id or img.s3_object_key:
            return jsonify({
                "success": False,
                "message": "Image editing is currently available only for locally stored EncounterSet images.",
            }), 409

        image_data = data.get("image_data")
        if not image_data:
            return jsonify({"success": False, "message": "No image data provided."}), 400
        try:
            decoded_image = decode_image_edit_payload(image_data)
            image_bytes = decoded_image.content
        except InvalidImageEditPayload:
            return jsonify({"success": False, "message": "Invalid image data provided."}), 400

        folder = (BASE_DIR / img.folder_rel).resolve()
        base_root = BASE_DIR.resolve()
        try:
            folder.relative_to(base_root)
        except ValueError:
            return jsonify({"success": False, "message": "Invalid image storage path."}), 400

        previous_edited_filename = img.edited_filename
        previous_thumbnail_filename = img.thumbnail_filename if img.edited_filename else None
        edited_basename = f"edited_{Path(img.original_filename).stem}{decoded_image.extension}"
        edited_path = folder / edited_basename
        edited_path.write_bytes(image_bytes)
        if previous_edited_filename and previous_edited_filename != edited_basename:
            (folder / Path(previous_edited_filename).name).unlink(missing_ok=True)

        try:
            from utils.image_metadata import extract_image_metadata, upsert_image_metadata

            upsert_image_metadata(
                db,
                image_uuid=str(img.uuid),
                image_variant="edited",
                metadata=extract_image_metadata(
                    image_bytes=image_bytes,
                    file_size_bytes=len(image_bytes),
                ),
            )
        except Exception as exc:
            current_app.logger.warning(
                "Failed to store edited EncounterSet metadata for %s: %s",
                img.uuid,
                exc,
            )

        # Any OCR/manual decision belongs to the previous edited bytes.
        db.query(ImagePiiVerification).filter(
            ImagePiiVerification.image_uuid == str(img.uuid),
            ImagePiiVerification.image_variant == "edited",
        ).delete(synchronize_session=False)
        try:
            from utils.pii_detection_queue import enqueue_pii_detection_job

            enqueue_pii_detection_job(
                db,
                image_uuid=str(img.uuid),
                image_variant="edited",
                image_path=str(edited_path),
                source="auto",
            )
        except Exception as exc:
            current_app.logger.warning(
                "Failed to enqueue edited EncounterSet OCR for %s: %s",
                img.uuid,
                exc,
            )

        thumbnail_filename = None
        thumbnails_dir = folder / "thumbnails"
        thumbnails_dir.mkdir(parents=True, exist_ok=True)
        try:
            thumbnail_filename = get_thumbnail_filename(edited_basename)
            if not generate_thumbnail(edited_path, thumbnails_dir / thumbnail_filename):
                thumbnail_filename = None
        except Exception as exc:
            current_app.logger.warning("Failed to generate EncounterSet edited thumbnail for %s: %s", img.uuid, exc)

        if previous_thumbnail_filename and previous_thumbnail_filename != thumbnail_filename:
            (thumbnails_dir / Path(previous_thumbnail_filename).name).unlink(missing_ok=True)

        img.edited_filename = edited_basename
        # Never leave an original/stale thumbnail attached to a newly edited image.
        img.thumbnail_filename = thumbnail_filename
        img.is_reviewed = True
        bump_media_cache_version(str(img.uuid))

        return jsonify({"success": True, "message": "Image saved and marked reviewed."})


@bp.route("/mark_anonymized/<uuid>", methods=["POST"])
@login_required
def mark_anonymized(uuid):
    """Mark an image as anonymized (PII masked)."""

    with transaction_scope() as db:
        img = db.query(EncounterSetImage).filter_by(uuid=uuid).first()
        if not img:
            return jsonify({"success": False, "message": "Image not found"}), 404

        # Query encounter and apply hospital scoping
        query = db.query(PatientEncounters).filter_by(id=img.patient_encounter_id)
        query = _apply_verification_scope(query)
        encounter = query.first()

        if not encounter:
            # Encounter not found or user doesn't have access
            return jsonify({"success": False, "message": "Image not found"}), 404
        if encounter.encounter_verified_status == "verified":
            return _already_verified_json_response(encounter)

        # P1.3: Validate S3 config access (defense-in-depth)
        if img.s3_config_id:
            is_valid, error_msg = validate_s3_config_access(img, current_user, db)
            if not is_valid:
                return jsonify({"success": False, "message": "Permission denied"}), 403

        missing_fields = missing_image_task_routing_fields(
            img,
            _active_encounter_set_type_config(encounter),
        )
        if missing_fields:
            return _missing_routing_metadata_response(missing_fields)

        img.is_anonymized = True
        img.is_reviewed = True

        return jsonify({"success": True})


@bp.route("/mark_all_anonymized/<uuid>", methods=["POST"])
@login_required
def mark_all_anonymized(uuid):
    """Mark all images in an encounter set as anonymized."""
    with transaction_scope() as db:
        encounter = _apply_verification_scope(
            db.query(PatientEncounters).filter_by(uuid=uuid)
        ).first()
        if not encounter:
            return jsonify({"success": False, "message": "Encounter not found"}), 404
        if encounter.encounter_verified_status == "verified":
            return _already_verified_json_response(encounter)

        images = db.query(EncounterSetImage).filter_by(patient_encounter_id=encounter.id).all()
        profile_config = _active_encounter_set_type_config(encounter)
        missing_by_image = [
            missing_image_task_routing_fields(image, profile_config)
            for image in images
        ]
        missing_by_image = [missing for missing in missing_by_image if missing]
        if missing_by_image:
            missing_fields = tuple({field.key: field for missing in missing_by_image for field in missing}.values())
            return _missing_routing_metadata_response(
                missing_fields,
                image_count=len(missing_by_image),
            )
        count = 0
        for img in images:
            img.is_anonymized = True
            img.is_reviewed = True
            count += 1

        return jsonify({"success": True, "count": count})


@bp.route("/restore_original/<uuid>", methods=["POST"])
@login_required
def restore_original(uuid):
    """Restore the original image (remove edited version)."""
    from pathlib import Path
    from models import BASE_DIR
    from utils.image_processing import generate_thumbnail, get_thumbnail_filename
    from utils.media_cache import bump_media_cache_version
    from models import GradingTask
    from sqlalchemy import select

    with transaction_scope() as db:
        img = db.query(EncounterSetImage).filter_by(uuid=uuid).first()
        if not img:
            return jsonify({"success": False, "message": "Image not found"}), 404

        encounter = _apply_verification_scope(
            db.query(PatientEncounters).filter_by(id=img.patient_encounter_id)
        ).first()
        if not encounter:
            return jsonify({"success": False, "message": "Encounter not found"}), 404
        if encounter.encounter_verified_status == "verified":
            return _already_verified_json_response(encounter)

        # Check if grading tasks are in progress
        task_states = db.execute(
            select(GradingTask.state).where(GradingTask.patient_encounter_id == encounter.id)
        ).scalars().all()
        if any(s and s.lower() != 'pending' for s in task_states):
            return jsonify({
                "success": False,
                "message": "Cannot modify image while associated grading tasks are in progress."
            }), 409

        if not img.edited_filename:
            return jsonify({"success": True, "message": "No edited version to restore."}), 200

        base_root = BASE_DIR.resolve()
        folder = (base_root / img.folder_rel).resolve()
        try:
            folder.relative_to(base_root)
        except ValueError:
            return jsonify({"success": False, "message": "Invalid image storage path."}), 400

        original_path = (folder / Path(img.original_filename).name).resolve()
        try:
            original_path.relative_to(folder)
        except ValueError:
            return jsonify({"success": False, "message": "Invalid original image path."}), 400
        if not original_path.is_file():
            return jsonify({
                "success": False,
                "message": "The stored original image is unavailable; the current image was not changed.",
            }), 409

        edited_path = (folder / Path(img.edited_filename).name).resolve()
        old_thumbnail = img.thumbnail_filename
        try:
            edited_path.relative_to(folder)
            edited_path.unlink(missing_ok=True)
            if old_thumbnail:
                (folder / "thumbnails" / Path(old_thumbnail).name).unlink(missing_ok=True)
        except Exception as e:
            current_app.logger.warning("Failed to delete EncounterSet edited assets for %s: %s", img.uuid, e)

        img.edited_filename = None
        db.query(ImageMetadata).filter(
            ImageMetadata.image_uuid == str(img.uuid),
            ImageMetadata.image_variant == "edited",
        ).delete(synchronize_session=False)
        db.query(ImagePiiVerification).filter(
            ImagePiiVerification.image_uuid == str(img.uuid),
            ImagePiiVerification.image_variant == "edited",
        ).delete(synchronize_session=False)
        original_thumbnail = get_thumbnail_filename(original_path.name)
        thumbnails_dir = folder / "thumbnails"
        thumbnails_dir.mkdir(parents=True, exist_ok=True)
        try:
            if generate_thumbnail(original_path, thumbnails_dir / original_thumbnail):
                img.thumbnail_filename = original_thumbnail
            else:
                img.thumbnail_filename = None
        except Exception as exc:
            img.thumbnail_filename = None
            current_app.logger.warning(
                "Failed to regenerate original EncounterSet thumbnail for %s: %s",
                img.uuid,
                exc,
            )
        bump_media_cache_version(str(img.uuid))

        return jsonify({"success": True, "message": "Original image restored."})


@bp.route("/mark_not_gradable/<uuid>", methods=["POST"])
@login_required
def mark_not_gradable(uuid):
    """Mark an image as not gradable with a reason."""
    data = request.json
    reason = data.get("reason", "").strip() if data else None

    if not reason:
        return jsonify({"success": False, "message": "Reason is required"}), 400

    with transaction_scope() as db:
        img = db.query(EncounterSetImage).filter_by(uuid=uuid).first()
        if not img:
            return jsonify({"success": False, "message": "Image not found"}), 404

        encounter = _apply_verification_scope(
            db.query(PatientEncounters).filter_by(id=img.patient_encounter_id)
        ).first()
        if not encounter:
            return jsonify({"success": False, "message": "Encounter not found"}), 404
        if encounter.encounter_verified_status == "verified":
            return _already_verified_json_response(encounter)

        img.is_not_gradable = True
        img.not_gradable_reason = reason
        img.is_reviewed = True  # Mark as reviewed even if not gradable

        return jsonify({"success": True})


@bp.route("/undo_not_gradable/<uuid>", methods=["POST"])
@login_required
def undo_not_gradable(uuid):
    """Undo the not gradable status for an image."""
    with transaction_scope() as db:
        img = db.query(EncounterSetImage).filter_by(uuid=uuid).first()
        if not img:
            return jsonify({"success": False, "message": "Image not found"}), 404

        encounter = _apply_verification_scope(
            db.query(PatientEncounters).filter_by(id=img.patient_encounter_id)
        ).first()
        if not encounter:
            return jsonify({"success": False, "message": "Encounter not found"}), 404
        if encounter.encounter_verified_status == "verified":
            return _already_verified_json_response(encounter)

        img.is_not_gradable = False
        img.not_gradable_reason = None
        missing_fields = missing_image_task_routing_fields(
            img,
            _active_encounter_set_type_config(encounter),
        )
        if missing_fields:
            img.is_reviewed = False

        return jsonify({
            "success": True,
            "is_reviewed": img.is_reviewed,
            "message": (
                "Ungradable status removed. Complete the required image metadata and review the image again."
                if missing_fields else "Ungradable status removed."
            ),
        })
