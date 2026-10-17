"""api_metadata stage: original Remidio API / IIIT-K source data behind the exported encounters."""
from __future__ import annotations

from sqlalchemy import select

from iitk_api_integration.models import IITKApiSessionLink
from models import EncounterSetAttachment, RemidioExam, RemidioImage, RemidioReport, RemidioSite
from project_sync.inventory import KIND_ENCOUNTER_FILE, KIND_ENCOUNTER_SET_IMAGE, _sanitize_metadata_dict
from remidio_api_integration.models import RemidioApiExamEncounter

from .tables import BuildContext, _chunks, _json, redact_files

# Never exported: server file paths; identifiers only with an identifiers grant.
_PATH_KEYS = frozenset({"path", "thumbnailPath"})
_REPORT_IDENTITY_KEYS = frozenset({"patientId", "reportingDoctorId"})


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _links(ctx: BuildContext) -> list:
    """[(exam id, encounter id, binding id)] for exported encounters."""
    if "api_links" not in ctx.cache:
        rows = []
        for chunk in _chunks(list(ctx.encounter_by_id)):
            rows.extend(ctx.db.execute(
                select(
                    RemidioApiExamEncounter.remidio_exam_id,
                    RemidioApiExamEncounter.patient_encounter_id,
                    RemidioApiExamEncounter.remidio_api_binding_id,
                ).where(RemidioApiExamEncounter.patient_encounter_id.in_(chunk))
            ).all())
        ctx.cache["api_links"] = rows
    return ctx.cache["api_links"]


def _by_exam(ctx: BuildContext) -> dict:
    """exam row id -> encounter id (an exam routes into exactly one encounter)."""
    return {exam_id: encounter_id for exam_id, encounter_id, _ in _links(ctx)}


def source_images(ctx: BuildContext) -> dict:
    """Exported image uuid -> its Remidio API image row (used for original-vs-verified comparisons)."""
    if "api_source_images" in ctx.cache:
        return ctx.cache["api_source_images"]
    set_uuid = {row_id: uuid for (kind, row_id), uuid in ctx.image_uuid_by_row.items() if kind == KIND_ENCOUNTER_SET_IMAGE}
    file_uuid = {row_id: uuid for (kind, row_id), uuid in ctx.image_uuid_by_row.items() if kind == KIND_ENCOUNTER_FILE}
    found = {}
    for chunk in _chunks(list(set_uuid)):
        for image in ctx.db.execute(select(RemidioImage).where(RemidioImage.encounter_set_image_id.in_(chunk))).scalars():
            found[set_uuid[image.encounter_set_image_id]] = image
    for chunk in _chunks(list(file_uuid)):
        for image in ctx.db.execute(select(RemidioImage).where(RemidioImage.encounter_file_id.in_(chunk))).scalars():
            found[file_uuid[image.encounter_file_id]] = image
    ctx.cache["api_source_images"] = found
    return found


def _exams(ctx: BuildContext) -> list:
    exams = []
    for chunk in _chunks(list(_by_exam(ctx))):
        exams.extend(ctx.db.execute(select(RemidioExam).where(RemidioExam.id.in_(chunk))).scalars())
    return exams


def _exam_rows(ctx: BuildContext) -> list[dict]:
    exams = _exams(ctx)
    site_names = dict(ctx.db.execute(select(RemidioSite.id, RemidioSite.site_name)).all())
    binding = {exam_id: binding_id for exam_id, _, binding_id in _links(ctx)}
    by_exam = _by_exam(ctx)
    rows = []
    for exam in exams:
        encounter_id = by_exam[exam.id]
        pii = ctx.allows_pii(encounter_id)
        raw = _dict(exam.raw_json)
        details = _dict(raw.get("examDetails"))
        rows.append({
            "encounter_uuid": ctx.encounter_uuid[encounter_id],
            "remidio_exam_row_id": exam.id,
            "remidio_exam_id": exam.remidio_exam_id,
            "site_name": site_names.get(exam.remidio_site_id),
            "site_custom_identifier": exam.site_custom_identifier,
            "exam_local_id": exam.exam_local_id,
            "exam_custom_id": exam.exam_custom_id,
            "exam_state": exam.exam_state,
            "exam_date": exam.exam_date,
            "device_types": _json(exam.device_types),
            "pull_source": exam.pull_source,
            "pulled_at": exam.pulled_at,
            "route_binding_id": binding.get(exam.id),
            "patient_gender": _dict(raw.get("patientDetails")).get("gender"),
            "has_ai_report": "aiReport" in raw,
            "has_medios_ai_report": "mediosAIReport" in raw,
            "has_gma_report": "gmaReport" in raw,
            "has_doctor_report": "report" in raw,
            "remidio_patient_id": exam.remidio_patient_id if pii else None,
            "patient_mrn": exam.remidio_patient_mrn if pii else None,
            "custom_fields_data": (details.get("customFieldsData") or None) if pii else None,
        })
    return rows


def _image_rows(ctx: BuildContext) -> list[dict]:
    by_exam = _by_exam(ctx)
    set_uuid = {row_id: uuid for (kind, row_id), uuid in ctx.image_uuid_by_row.items() if kind == KIND_ENCOUNTER_SET_IMAGE}
    file_uuid = {row_id: uuid for (kind, row_id), uuid in ctx.image_uuid_by_row.items() if kind == KIND_ENCOUNTER_FILE}
    rows = []
    for chunk in _chunks(list(by_exam)):
        for image in ctx.db.execute(select(RemidioImage).where(RemidioImage.remidio_exam_id.in_(chunk))).scalars():
            raw = _dict(image.raw_json)
            quality = _dict(raw.get("discQualityResults"))
            rows.append({
                "encounter_uuid": ctx.encounter_uuid[by_exam[image.remidio_exam_id]],
                "image_uuid": set_uuid.get(image.encounter_set_image_id) or file_uuid.get(image.encounter_file_id),
                "remidio_exam_row_id": image.remidio_exam_id,
                "remidio_image_id": image.remidio_image_id,
                "device_type": image.device_type,
                "image_variant": image.image_variant,
                "laterality": image.laterality,
                "field": image.field,
                "quality": image.quality,
                "image_segment": raw.get("imageSegment"),
                "is_cropped": raw.get("isCropped"),
                "disc_quality_score": quality.get("qualityScore"),
                "disc_present": quality.get("discPresent"),
                "disc_quality_acceptable": quality.get("acceptableQuality"),
                "width": image.width,
                "height": image.height,
                "edit_operations": _json(raw.get("editOperations")),
                "original_image_ids": _json(raw.get("originalImageIds")),
                "download_error": redact_files(image.download_error, ctx.allows_pii(by_exam[image.remidio_exam_id])),
            })
    return rows


def _report_rows(ctx: BuildContext) -> list[dict]:
    by_exam = _by_exam(ctx)
    reports = []
    for chunk in _chunks(list(by_exam)):
        reports.extend(ctx.db.execute(select(RemidioReport).where(RemidioReport.remidio_exam_id.in_(chunk))).scalars())
    attachment_ids = [r.encounter_set_attachment_id for r in reports if r.encounter_set_attachment_id]
    attachment_uuid = {}
    for chunk in _chunks(attachment_ids):
        attachment_uuid.update(ctx.db.execute(
            select(EncounterSetAttachment.id, EncounterSetAttachment.uuid).where(EncounterSetAttachment.id.in_(chunk))
        ).all())
    rows = []
    for report in reports:
        encounter_id = by_exam[report.remidio_exam_id]
        pii = ctx.allows_pii(encounter_id)
        raw = _dict(report.raw_json)
        dr, amd, gma = _dict(raw.get("drResult")), _dict(raw.get("amdResult")), _dict(raw.get("gmaResult"))
        payload = raw if pii else {k: v for k, v in raw.items() if k not in _REPORT_IDENTITY_KEYS}
        rows.append({
            "encounter_uuid": ctx.encounter_uuid[encounter_id],
            "remidio_exam_row_id": report.remidio_exam_id,
            "remidio_report_id": report.remidio_report_id,
            "report_type": report.report_type,
            "generated_at": report.generated_at,
            "attachment_uuid": attachment_uuid.get(report.encounter_set_attachment_id),
            "suggested_refer": raw.get("suggestedRefer"),
            "confidence": raw.get("confidence"),
            "left_eye_cdr": raw.get("leftEyeCdr"),
            "right_eye_cdr": raw.get("rightEyeCdr"),
            "dr_confidence": dr.get("confidence"),
            "dr_input_sufficient": dr.get("inputSufficient"),
            "dr_quality_sufficient": dr.get("qualitySufficient"),
            "dr_heatmap_images": dr.get("numberOfHeatmapImages"),
            "dr_suggested_refer": dr.get("suggestedRefer"),
            "amd_confidence": amd.get("confidence"),
            "amd_input_sufficient": amd.get("inputSufficient"),
            "amd_quality_sufficient": amd.get("qualitySufficient"),
            "amd_heatmap_images": amd.get("numberOfHeatmapImages"),
            "amd_suggested_refer": amd.get("suggestedRefer"),
            "gma_left_eye_cdr": gma.get("leftEyeCdr"),
            "gma_right_eye_cdr": gma.get("rightEyeCdr"),
            "gma_patient_level_result": gma.get("patientLevelResult"),
            "gma_suggested_refer": gma.get("suggestedRefer"),
            "refer_required": raw.get("referRequired"),
            "left_eye_diagnosis": _json(raw.get("leftEyeDiagnosis")),
            "right_eye_diagnosis": _json(raw.get("rightEyeDiagnosis")),
            "payload": _json({k: v for k, v in payload.items() if k not in _PATH_KEYS}),
        })
    return rows


def _iitk_rows(ctx: BuildContext) -> list[dict]:
    rows = []
    for chunk in _chunks(list(ctx.encounter_by_id)):
        for link in ctx.db.execute(
            select(IITKApiSessionLink).where(IITKApiSessionLink.patient_encounter_id.in_(chunk))
        ).scalars():
            pii = ctx.allows_pii(link.patient_encounter_id)
            rows.append({
                "encounter_uuid": ctx.encounter_uuid[link.patient_encounter_id],
                "source_status": link.source_status,
                "source_image_count": link.source_image_count,
                "local_image_count": link.local_image_count,
                "first_seen_at": link.first_seen_at,
                "last_synced_at": link.last_synced_at,
                "last_error": redact_files(link.last_error, pii),
                "source_session_id": link.source_session_id if pii else None,
                "source_metadata": _json(_sanitize_metadata_dict(link.source_metadata_json, pii=pii)),
            })
    return rows


def build(ctx: BuildContext) -> dict[str, list[dict]]:
    return {
        "api_exams": _exam_rows(ctx),
        "api_images": _image_rows(ctx),
        "api_reports": _report_rows(ctx),
        "iitk_sessions": _iitk_rows(ctx),
    }
