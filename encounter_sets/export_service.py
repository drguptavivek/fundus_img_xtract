"""EncounterSet workbook exports for EMR reconciliation."""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from openpyxl import Workbook
from sqlalchemy.orm import Session, selectinload

from encounter_sets.models import EncounterSetAttachment
from authz.behaviors import (
    export_lab_units,
    export_rows,
    identifier_release_lab_units,
    identifier_release_rows,
)
from authz.context import access_context
from authz.scopes import RecordScope, admin_scope, project_scope, require_any
from services.uploads.access import encounter_columns
from models import (
    AMDReport,
    DiabeticRetinopathyReport,
    GlaucomaReport,
    GlaucomaResultsCleaned,
    PatientEncounters,
    RemidioExam,
    LabUnit,
)

@dataclass(frozen=True)
class EncounterSetExportFilters:
    project_id: int | None
    month: str
    lab_unit_id: int | None = None


class EncounterSetExportValidationError(ValueError):
    """Raised when an export filter cannot be parsed."""


BASE_HEADERS = [
    "EncounterID",
    "Type",
    "hospital_UHID",
    "Date of capture",
    "patient_name",
    "patient_age_yrs",
    "sex",
    "remidio_site_custom_identifier",
    "capture_date",
    "capture_time",
    "clinical_image_count",
    "has_DR_PDF",
    "has_glaucoma_PDF",
    "has_AMD_PDF",
]

_OCR_MODELS = (
    ("dr_ocr", DiabeticRetinopathyReport, "dr_reports"),
    ("glaucoma_ocr", GlaucomaReport, "glaucoma_reports"),
    ("glaucoma_cleaned_ocr", GlaucomaResultsCleaned, "glaucoma_results_cleaned"),
    ("amd_ocr", AMDReport, "amd_reports"),
)


def parse_export_month(value: str) -> tuple[date, date]:
    """Return the inclusive month start and exclusive next-month boundary."""

    if not isinstance(value, str) or re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value) is None:
        raise EncounterSetExportValidationError("month must use YYYY-MM format")
    try:
        start = datetime.strptime(value, "%Y-%m").date().replace(day=1)
    except (TypeError, ValueError) as exc:
        raise EncounterSetExportValidationError("month must use YYYY-MM format") from exc
    if start.month == 12:
        end = date(start.year + 1, 1, 1)
    else:
        end = date(start.year, start.month + 1, 1)
    return start, end


def export_encounter_sets_xlsx(
    db: Session,
    *,
    user,
    filters: EncounterSetExportFilters,
    timezone_name: str,
    include_identifiers: bool = False,
) -> bytes:
    """Build a masked sheet unless the explicit PII action was selected."""

    month_start, month_end = parse_export_month(filters.month)
    encounters = _load_encounters(
        db,
        user,
        filters.project_id,
        filters.lab_unit_id,
        month_start,
        month_end,
        include_identifiers=include_identifiers,
    )
    exams = _load_remidio_exams(db, encounters)
    target_timezone = _target_timezone(timezone_name)
    max_rows = {
        prefix: max((len(getattr(encounter, relationship) or []) for encounter in encounters), default=0)
        for prefix, _model, relationship in _OCR_MODELS
    }

    headers = list(BASE_HEADERS)
    for prefix, model, _relationship in _OCR_MODELS:
        for index in range(1, max_rows[prefix] + 1):
            headers.extend(f"{prefix}_{index}_{column.name}" for column in model.__table__.columns)

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("EncounterSet EMR Data")
    rows = (
        _encounter_row(
            encounter,
            exams.get(encounter.id),
            target_timezone,
            max_rows,
            include_identifiers=include_identifiers,
        )
        for encounter in encounters
    )
    _write_sheet(sheet, headers, rows)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _load_encounters(
    db: Session,
    user,
    project_id: int | None,
    lab_unit_id: int | None,
    month_start: date,
    month_end: date,
    *,
    include_identifiers: bool,
) -> list[PatientEncounters]:
    context = access_context(db, user)
    if project_id is not None:
        requested_scope = RecordScope.project(
            project_id=project_id, lab_unit_id=lab_unit_id
        )
        require_any(
            admin_scope(context),
            project_scope(
                context,
                {"pii_exporter"} if include_identifiers else {"data_exporter", "pii_exporter"},
                requested_scope,
            ),
        )
    elif include_identifiers and not context.has_any_global_role(frozenset({"admin"})):
        from authz.exceptions import AuthorizationDenied

        raise AuthorizationDenied("classical_pii_export_requires_admin")

    if lab_unit_id is not None:
        lab_query = db.query(LabUnit.id).filter(LabUnit.id == lab_unit_id)
        lab_query = (
            identifier_release_lab_units(db, lab_query, user)
            if include_identifiers
            else export_lab_units(db, lab_query, user)
        )
        if lab_query.first() is None:
            from authz.exceptions import AuthorizationDenied

            raise AuthorizationDenied("export_lab_unit_unauthorized")

    filters = (
        PatientEncounters.is_set_based.is_(True),
        PatientEncounters.project_id == project_id,
        PatientEncounters.capture_date_dt >= month_start,
        PatientEncounters.capture_date_dt < month_end,
    )
    columns = encounter_columns(PatientEncounters)
    if lab_unit_id is not None:
        filters = (*filters, PatientEncounters.lab_unit_id == lab_unit_id)
    scoped_query = (
        identifier_release_rows if include_identifiers else export_rows
    )(
        db,
        db.query(PatientEncounters.id).filter(*filters),
        user,
        columns,
    )
    scoped_ids = [int(row[0]) for row in scoped_query.all()]
    if not scoped_ids:
        return []
    return (
        db.query(PatientEncounters)
        .filter(PatientEncounters.id.in_(scoped_ids))
        .options(
            selectinload(PatientEncounters.encounter_set_images),
            selectinload(PatientEncounters.encounter_set_attachments),
            selectinload(PatientEncounters.dr_reports),
            selectinload(PatientEncounters.glaucoma_reports),
            selectinload(PatientEncounters.glaucoma_results_cleaned),
            selectinload(PatientEncounters.amd_reports),
        )
        .order_by(PatientEncounters.capture_date_dt.asc(), PatientEncounters.id.asc())
        .all()
    )


def _load_remidio_exams(db: Session, encounters: list[PatientEncounters]) -> dict[int, RemidioExam]:
    encounter_ids = [encounter.id for encounter in encounters]
    if not encounter_ids:
        return {}
    return {
        exam.patient_encounter_id: exam
        for exam in db.query(RemidioExam)
        .filter(RemidioExam.patient_encounter_id.in_(encounter_ids))
        .order_by(RemidioExam.id.asc())
        .all()
        if exam.patient_encounter_id is not None
    }


def _encounter_row(
    encounter: PatientEncounters,
    exam: RemidioExam | None,
    target_timezone: ZoneInfo,
    max_rows: dict[str, int],
    *,
    include_identifiers: bool,
) -> dict[str, Any]:
    metadata = encounter.metadata_json if isinstance(encounter.metadata_json, dict) else {}
    patient_metadata = metadata.get("patient") if isinstance(metadata.get("patient"), dict) else {}
    encounter_metadata = metadata.get("encounter") if isinstance(metadata.get("encounter"), dict) else {}
    capture_datetime = _parse_datetime(
        encounter_metadata.get("capture_datetime")
        or metadata.get("capture_datetime")
        or metadata.get("started_at")
    )
    if capture_datetime is None and exam is not None:
        capture_datetime = exam.exam_date
    localized_capture = _localize(capture_datetime, target_timezone)
    attachments = encounter.encounter_set_attachments or []
    patient_age = _first_value(patient_metadata, "patient_age_yrs", "age", "age_yrs")
    if patient_age is None:
        patient_age = _first_value(metadata, "patient_age_yrs", "age", "age_yrs")
    patient_sex = _first_value(patient_metadata, "sex", "gender")
    if patient_sex is None:
        patient_sex = _first_value(metadata, "sex", "gender")

    row: dict[str, Any] = {
        "EncounterID": encounter.id,
        "Type": "encounterSet",
        "hospital_UHID": (
            _first_value(patient_metadata, "hospital_UHID")
            or metadata.get("hospital_UHID")
            or encounter.patient_id
        ),
        "Date of capture": encounter.capture_date_dt or encounter.capture_date,
        "patient_name": _first_value(patient_metadata, "patient_name") or metadata.get("patient_name") or encounter.name,
        "patient_age_yrs": patient_age,
        "sex": patient_sex,
        "remidio_site_custom_identifier": (
            exam.site_custom_identifier
            if exam and exam.site_custom_identifier
            else _first_value(patient_metadata, "remidio_site_custom_identifier")
            or metadata.get("remidio_site_custom_identifier")
        ),
        "capture_date": localized_capture.date().isoformat() if localized_capture else encounter.capture_date_dt,
        "capture_time": localized_capture.strftime("%H:%M:%S") if localized_capture else "",
        "clinical_image_count": len(encounter.encounter_set_images or []),
        "has_DR_PDF": _has_disease_pdf(attachments, "dr"),
        "has_glaucoma_PDF": _has_disease_pdf(attachments, "glaucoma"),
        "has_AMD_PDF": _has_disease_pdf(attachments, "amd"),
    }
    for prefix, model, relationship in _OCR_MODELS:
        values = sorted(getattr(encounter, relationship) or [], key=lambda item: item.id)
        for index in range(max_rows[prefix]):
            value = values[index] if index < len(values) else None
            for column in model.__table__.columns:
                row[f"{prefix}_{index + 1}_{column.name}"] = getattr(value, column.name) if value else ""
    if not include_identifiers:
        for key in tuple(row):
            lowered = key.lower()
            if any(
                marker in lowered
                for marker in (
                    "patient_name",
                    "patient_id",
                    "uhid",
                    "custom_identifier",
                    "file_name",
                    "filename",
                    "metadata_json",
                    "remarks",
                )
            ):
                row[key] = "Anonymous" if "name" in lowered and "file" not in lowered else "masked"
    return row


def _has_disease_pdf(attachments: Iterable[EncounterSetAttachment], disease: str) -> bool:
    for attachment in attachments:
        if attachment.asset_kind != "pdf" and attachment.mime_type != "application/pdf":
            continue
        metadata = attachment.metadata_json if isinstance(attachment.metadata_json, dict) else {}
        ocr = metadata.get("ocr") if isinstance(metadata.get("ocr"), dict) else {}
        if isinstance(ocr.get(f"{disease}_report"), dict):
            return True
        report_type = str(metadata.get("remidio_report_type") or metadata.get("report_type") or "").lower()
        if disease in report_type or (disease == "glaucoma" and "gla" in report_type):
            return True
    return False


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _localize(value: datetime | None, target_timezone: ZoneInfo) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(target_timezone)


def _target_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _first_value(metadata: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return value
    return None


def _xlsx_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        value = json.dumps(value, sort_keys=True)
    if value is None:
        return ""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def _write_sheet(sheet, headers: list[str], rows: Iterable[dict[str, Any]]) -> None:
    sheet.append(headers)
    for row in rows:
        sheet.append([_xlsx_value(row.get(header)) for header in headers])
