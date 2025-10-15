import json
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd
from flask import current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user
from sqlalchemy import and_, select, func

from . import bp
from auth.roles import roles_required
from models import (
    Area,
    DirectImageUpload,
    Disease,
    DiseaseGrading,
    GradingTask,
    Hospital,
    Job,
    JobItem,
    LabUnit,
    Role,
    Session as DBSession,
    User,
    Grade,
    utcnow,
)
from services.taskCreationServices import ensure_task
from utils.utils import with_session
from utils.upload_eligibility import get_user_lab_unit_ids
from utils.dualGradingConsensusUtils import (
    create_or_update_consensus,
    update_task_state_based_on_grades,
)
import logging


processing_logger = logging.getLogger("pregraded_processing")


ROLE_RESIDENT = "resident"
ROLE_FACULTY = "faculty"


@dataclass
class PendingImport:
    role: str
    hospital_id: int
    lab_unit_id: int
    disease_id: int
    grader_user_id: int
    rows: List[Dict[str, Optional[str]]]
    auto_mapping: Dict[str, int]


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(col).strip().lower().replace(" ", "_") for col in df.columns]
    return df


def _load_workbook(file_storage) -> pd.DataFrame:
    try:
        df = pd.read_excel(file_storage, engine="openpyxl")
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Unable to read Excel file: {exc}") from exc
    return _normalize_columns(df)


def _extract_rows(df: pd.DataFrame, role: str) -> List[Dict[str, Optional[str]]]:
    required = {"image_name"}
    grade_col = f"{role}_grade"
    remark_col = f"{role}_remarks"
    required.add(grade_col)
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(sorted(missing))}")

    rows: List[Dict[str, Optional[str]]] = []
    for _, row in df.iterrows():
        image_name = (str(row.get("image_name", "")).strip() or None)
        grade_value = row.get(grade_col)
        grade_text = str(grade_value).strip() if pd.notna(grade_value) else ""
        remarks_value = row.get(remark_col, "")
        remarks = str(remarks_value).strip() if pd.notna(remarks_value) else ""
        if image_name is None:
            continue
        rows.append(
            {
                "image_name": image_name,
                "grade_text": grade_text,
                "remarks": remarks if remarks and remarks != "-" else None,
            }
        )
    if not rows:
        raise ValueError("Workbook does not contain any rows with image_name.")
    return rows


def _grade_lookup(db_session, disease_id: int) -> Dict[int, DiseaseGrading]:
    gradings = db_session.execute(
        select(DiseaseGrading).where(
            and_(
                DiseaseGrading.disease_id == disease_id,
                DiseaseGrading.is_active.is_(True),
            )
        )
    ).scalars().all()
    return {grading.id: grading for grading in gradings}


def _normalize_text(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _auto_map_grade_values(
    grade_options: Dict[int, DiseaseGrading], grade_texts: List[str]
) -> Tuple[Dict[str, int], List[str]]:
    by_impression = {
        _normalize_text(option.impression): option.id for option in grade_options.values()
    }
    auto_mapping: Dict[str, int] = {}
    unmapped: List[str] = []
    for text in grade_texts:
        if not text:
            continue  # empty grades handled downstream as errors
        key = _normalize_text(text)
        grade_id = by_impression.get(key)
        if grade_id is not None:
            auto_mapping[text] = grade_id
        else:
            unmapped.append(text)
    return auto_mapping, unmapped


def _store_pending_import(token: str, pending: PendingImport) -> None:
    store = session.setdefault("pregraded_grade_imports", {})
    store[token] = {
        "role": pending.role,
        "hospital_id": pending.hospital_id,
        "lab_unit_id": pending.lab_unit_id,
        "disease_id": pending.disease_id,
        "grader_user_id": pending.grader_user_id,
        "rows": pending.rows,
        "auto_mapping": pending.auto_mapping,
    }
    session.modified = True
    processing_logger.debug(
        "Pending import stored token=%s role=%s rows=%s",
        token,
        pending.role,
        len(pending.rows),
    )


def _pop_pending_import(token: str) -> Optional[PendingImport]:
    store = session.get("pregraded_grade_imports") or {}
    raw = store.pop(token, None)
    session["pregraded_grade_imports"] = store
    session.modified = True
    if not raw:
        processing_logger.debug("Pending import token %s not found", token)
        return None
    processing_logger.debug("Pending import token %s restored", token)
    return PendingImport(
        role=raw["role"],
        hospital_id=raw["hospital_id"],
        lab_unit_id=raw["lab_unit_id"],
        disease_id=raw["disease_id"],
        grader_user_id=raw["grader_user_id"],
        rows=raw["rows"],
        auto_mapping=raw["auto_mapping"],
    )


def _resolve_grade_mapping(
    pending: PendingImport, mapping: Dict[str, int], grade_options: Dict[int, DiseaseGrading]
) -> Dict[str, int]:
    final_mapping = dict(pending.auto_mapping)
    final_mapping.update(mapping)

    for row in pending.rows:
        grade_text = row["grade_text"]
        if not grade_text:
            continue
        if grade_text not in final_mapping:
            raise ValueError(f"No mapping provided for grade value '{grade_text}'.")
        grade_id = final_mapping[grade_text]
        if grade_id not in grade_options:
            raise ValueError(f"Invalid grade ID {grade_id} supplied for '{grade_text}'.")
    return final_mapping


def _eligible_graders(db_session, roles: List[str]) -> List[User]:
    stmt = (
        select(User)
        .join(User.roles)
        .where(Role.name.in_(roles))
        .distinct()
        .order_by(User.username)
    )
    return db_session.execute(stmt).scalars().all()


def _find_upload(
    db_session,
    *,
    image_name: str,
    hospital_id: int,
    lab_unit_id: int,
    disease_id: int,
) -> Optional[DirectImageUpload]:
    normalized_name = image_name.strip().lower()
    stmt = (
        select(DirectImageUpload)
        .where(
            func.lower(DirectImageUpload.original_filename) == normalized_name,
            DirectImageUpload.hospital_id == hospital_id,
            DirectImageUpload.lab_unit_id == lab_unit_id,
            DirectImageUpload.disease_id == disease_id,
            DirectImageUpload.is_pregraded.is_(True),
        )
        .order_by(DirectImageUpload.created_at.desc())
    )
    uploads = db_session.execute(stmt).scalars().all()
    if not uploads:
        processing_logger.debug(
            "No upload match for filename=%s hospital=%s lab=%s disease=%s",
            image_name,
            hospital_id,
            lab_unit_id,
            disease_id,
        )
        return None
    if len(uploads) > 1:
        current_app.logger.warning(
            "Multiple pre-graded uploads matched image_name=%s (hospital=%s lab=%s disease=%s); using most recent.",
            image_name,
            hospital_id,
            lab_unit_id,
            disease_id,
        )
    return uploads[0]


def _apply_grade(
    db_session,
    *,
    task: GradingTask,
    grade_id: int,
    grader_user_id: int,
    role: str,
    remarks: Optional[str],
    grade_options: Dict[int, DiseaseGrading],
) -> None:
    existing_grade = db_session.execute(
        select(Grade).where(
            Grade.task_id == task.id,
            Grade.role_slot == role,
        )
    ).scalar_one_or_none()

    grading_label = grade_options[grade_id]
    now = utcnow()

    if existing_grade:
        existing_grade.grader_user_id = grader_user_id
        existing_grade.disease_grading_id = grade_id
        existing_grade.comment = remarks
        existing_grade.disease_name = grading_label.disease.name if grading_label.disease else None
        existing_grade.grade_name = grading_label.impression
        existing_grade.grade_description = grading_label.guidelines
        existing_grade.updated_at = now
    else:
        db_session.add(
            Grade(
                task_id=task.id,
                grader_user_id=grader_user_id,
                role_slot=role,
                disease_grading_id=grade_id,
                comment=remarks,
                disease_name=grading_label.disease.name if grading_label.disease else None,
                grade_name=grading_label.impression,
                grade_description=grading_label.guidelines,
            )
        )


def _process_rows(
    db_session,
    *,
    pending: PendingImport,
    mapping: Dict[str, int],
    job: Job,
    grade_options: Dict[int, DiseaseGrading],
) -> Tuple[int, int, List[JobItem]]:
    success = 0
    failures = 0
    job_items: List[JobItem] = []

    processing_logger.info(
        "job_id=%s role=%s start rows=%s hospital=%s lab=%s disease=%s",
        job.id,
        pending.role,
        len(pending.rows),
        pending.hospital_id,
        pending.lab_unit_id,
        pending.disease_id,
    )

    for row in pending.rows:
        filename = row["image_name"]
        grade_text = row["grade_text"]
        if not grade_text:
            item_state = "error"
            detail = "Missing grade value"
            processing_logger.warning(
                "job_id=%s role=%s filename=%s result=%s detail=%s",
                job.id,
                pending.role,
                filename,
                item_state,
                detail,
            )
            job_items.append(
                JobItem(
                    job_id=job.id,
                    filename=filename,
                    state=item_state,
                    detail=detail,
                    uploader_user_id=current_user.id,
                    uploader_username=current_user.username,
                    uploader_ip=request.remote_addr,
                )
            )
            failures += 1
            continue

        grade_id = mapping.get(grade_text)
        if grade_id is None:
            item_state = "error"
            detail = f"No grade mapping for '{grade_text}'"
            processing_logger.warning(
                "job_id=%s role=%s filename=%s result=%s detail=%s",
                job.id,
                pending.role,
                filename,
                item_state,
                detail,
            )
            job_items.append(
                JobItem(
                    job_id=job.id,
                    filename=filename,
                    state=item_state,
                    detail=detail,
                    uploader_user_id=current_user.id,
                    uploader_username=current_user.username,
                    uploader_ip=request.remote_addr,
                )
            )
            failures += 1
            continue

        remarks = row["remarks"]
        item_state = "completed"
        detail = "Grade imported successfully"

        try:
            processing_logger.info(
                "job_id=%s role=%s filename=%s mapping_grade=%s",
                job.id,
                pending.role,
                filename,
                grade_id,
            )
            upload = _find_upload(
                db_session,
                image_name=filename,
                hospital_id=pending.hospital_id,
                lab_unit_id=pending.lab_unit_id,
                disease_id=pending.disease_id,
            )
            if not upload:
                raise ValueError(
                    f"Image '{filename}' not found in pre-graded uploads for the selected hospital/lab/disease."
                )

            try:
                ensure_task(upload.uuid, pending.disease_id)
            except Exception as exc:  # noqa: BLE001
                current_app.logger.warning(
                    "ensure_task failed for pre-graded import (uuid=%s): %s",
                    upload.uuid,
                    exc,
                )
                processing_logger.warning(
                    "job_id=%s role=%s filename=%s ensure_task_failed=%s",
                    job.id,
                    pending.role,
                    filename,
                    exc,
                )
            else:
                processing_logger.info(
                    "job_id=%s role=%s filename=%s ensured_task_uuid=%s",
                    job.id,
                    pending.role,
                    filename,
                    upload.uuid,
                )

            task = db_session.execute(
                select(GradingTask).where(
                    GradingTask.direct_image_upload_id == upload.id,
                    GradingTask.disease_id == pending.disease_id,
                )
            ).scalar_one_or_none()

            if not task:
                raise ValueError("Associated grading task not found.")

            _apply_grade(
                db_session,
                task=task,
                grade_id=grade_id,
                grader_user_id=pending.grader_user_id,
                role=pending.role,
                remarks=remarks,
                grade_options=grade_options,
            )

            update_task_state_based_on_grades(task.id, db=db_session)
            if pending.role == ROLE_FACULTY:
                create_or_update_consensus(task.id, db=db_session)

            success += 1
        except Exception as exc:  # noqa: BLE001
            current_app.logger.exception("Failed to import grade for %s: %s", filename, exc)
            item_state = "error"
            detail = str(exc)
            failures += 1

        job_items.append(
            JobItem(
                job_id=job.id,
                filename=filename,
                state=item_state,
                detail=detail,
                uploader_user_id=current_user.id,
                uploader_username=current_user.username,
                uploader_ip=request.remote_addr,
            )
        )

        processing_logger.info(
            "job_id=%s role=%s filename=%s result=%s detail=%s",
            job.id,
            pending.role,
            filename,
            item_state,
            detail,
        )

    return success, failures, job_items


def _render_page(
    db_session,
    *,
    resident_graders: List[User],
    faculty_graders: List[User],
    context: Optional[dict] = None,
):
    context = context or {}
    allowed_lab_units = get_user_lab_unit_ids(current_user.id)
    is_admin_like = current_user.has_role("admin", "data_manager")

    if allowed_lab_units or is_admin_like:
        lab_units = (
            db_session.execute(
                select(LabUnit).order_by(LabUnit.name)
            ).scalars().all()
            if is_admin_like
            else db_session.execute(
                select(LabUnit)
                .where(LabUnit.id.in_(allowed_lab_units))
                .order_by(LabUnit.name)
            ).scalars().all()
        )
    else:
        lab_units = []

    hospital_ids = {lu.hospital_id for lu in lab_units}
    hospitals = (
        db_session.execute(
            select(Hospital).where(Hospital.id.in_(hospital_ids)).order_by(Hospital.name)
        ).scalars().all()
        if hospital_ids
        else []
    )

    diseases = db_session.execute(select(Disease).order_by(Disease.name)).scalars().all()
    areas = db_session.execute(select(Area).order_by(Area.name)).scalars().all()

    grade_options: Dict[int, List[DiseaseGrading]] = {}
    for disease in diseases:
        gradings = (
            db_session.execute(
                select(DiseaseGrading)
                .where(
                    and_(
                        DiseaseGrading.disease_id == disease.id,
                        DiseaseGrading.is_active.is_(True),
                    )
                )
                .order_by(DiseaseGrading.display_order)
            )
            .scalars()
            .all()
        )
        grade_options[disease.id] = gradings

    context.update(
        {
            "hospitals": hospitals,
            "lab_units": lab_units,
            "diseases": diseases,
            "areas": areas,
            "resident_graders": resident_graders,
            "faculty_graders": faculty_graders,
            "grade_options": grade_options,
        }
    )
    return render_template("direct_uploads/pregraded_grades.html", **context)


@bp.route("/direct/pregraded/grades", methods=["GET", "POST"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin")
def pregraded_grades():
    with with_session() as db_session:
        resident_graders = _eligible_graders(db_session, ["resident", "ophthalmologist"])
        faculty_graders = _eligible_graders(db_session, ["ophthalmologist"])

        if request.method == "GET":
            return _render_page(
                db_session,
                resident_graders=resident_graders,
                faculty_graders=faculty_graders,
            )

        form_role = request.form.get("form_role")
        if form_role not in {ROLE_RESIDENT, ROLE_FACULTY}:
            flash("Invalid form submission.", "danger")
            return redirect(url_for("direct_uploads.pregraded_grades"))

        mapping_token = request.form.get("mapping_token")
        mapping_json = request.form.get("mapping_json")
        processing_logger.info(
            "POST /direct/pregraded/grades role=%s mapping_token=%s mapping_json_len=%s",
            form_role,
            mapping_token or "",
            len(mapping_json or ""),
        )
        if mapping_token:
            pending = _pop_pending_import(mapping_token)
            if not pending:
                processing_logger.warning("Mapping token %s missing/expired", mapping_token)
                flash("Mapping session expired. Please upload the file again.", "warning")
                return redirect(url_for("direct_uploads.pregraded_grades"))

            try:
                mapping_payload = json.loads(mapping_json or "{}")
            except json.JSONDecodeError:
                processing_logger.error("Invalid mapping JSON for token %s", mapping_token)
                flash("Invalid mapping payload.", "danger")
                return redirect(url_for("direct_uploads.pregraded_grades"))

            grade_options = _grade_lookup(db_session, pending.disease_id)
            try:
                final_mapping = _resolve_grade_mapping(pending, mapping_payload, grade_options)
            except ValueError as exc:
                processing_logger.warning("Mapping validation failed: %s", exc)
                flash(str(exc), "danger")
                return redirect(url_for("direct_uploads.pregraded_grades"))

            job = Job(
                token=str(uuid.uuid4()),
                status="processing",
                uploader_user_id=current_user.id,
                uploader_username=current_user.username,
                uploader_ip=request.remote_addr,
                lab_unit_id=pending.lab_unit_id,
                rejected_summary=f"{pending.role.title()} grade import",
            )
            db_session.add(job)
            db_session.flush()

            success, failures, job_items = _process_rows(
                db_session,
                pending=pending,
                mapping=final_mapping,
                job=job,
                grade_options=grade_options,
            )
            db_session.add_all(job_items)
            job.status = "completed" if failures == 0 else "error"
            if failures:
                job.error = f"{failures} of {len(pending.rows)} rows failed."
            db_session.commit()

            flash(
                f"Imported {success} grade(s); {failures} error(s). Review job details for specifics.",
                "success" if failures == 0 else "warning",
            )
            return redirect(url_for("direct_uploads.upload_processing", job_id=job.id))

        hospital_id = request.form.get("hospital_id", type=int)
        lab_unit_id = request.form.get("lab_unit_id", type=int)
        disease_id = request.form.get("disease_id", type=int)
        grader_user_id = request.form.get("grader_user_id", type=int)

        for field_name, value in [
            ("Hospital", hospital_id),
            ("Lab Unit", lab_unit_id),
            ("Disease", disease_id),
            ("Grader", grader_user_id),
        ]:
            if value is None:
                processing_logger.warning("Missing field %s for role %s", field_name, form_role)
                flash(f"{field_name} must be selected.", "danger")
                return redirect(url_for("direct_uploads.pregraded_grades"))

        grades_file = request.files.get("grades_file")
        if not grades_file or not grades_file.filename:
            processing_logger.warning("No file uploaded for role %s", form_role)
            flash("Please select an Excel file to upload.", "danger")
            return redirect(url_for("direct_uploads.pregraded_grades"))

        allowed_lab_units = get_user_lab_unit_ids(current_user.id)
        is_admin_like = current_user.has_role("admin", "data_manager")
        if not is_admin_like and lab_unit_id not in allowed_lab_units:
            processing_logger.warning(
                "User %s attempted grade import to unauthorized lab %s",
                current_user.id,
                lab_unit_id,
            )
            flash("You do not have access to the selected lab unit.", "danger")
            return redirect(url_for("direct_uploads.pregraded_grades"))

        grader = db_session.get(User, grader_user_id)
        if not grader:
            processing_logger.warning("Grader user_id=%s not found", grader_user_id)
            flash("Selected grader not found.", "danger")
            return redirect(url_for("direct_uploads.pregraded_grades"))

        role_names = {role.name.lower() for role in grader.roles}
        if form_role == ROLE_RESIDENT and not ({"resident", "ophthalmologist"} & role_names):
            processing_logger.warning("Grader %s lacks resident role", grader_user_id)
            flash("Selected user is not eligible for resident grading.", "danger")
            return redirect(url_for("direct_uploads.pregraded_grades"))
        if form_role == ROLE_FACULTY and "ophthalmologist" not in role_names:
            processing_logger.warning("Grader %s lacks faculty eligibility", grader_user_id)
            flash("Selected user is not eligible for faculty grading.", "danger")
            return redirect(url_for("direct_uploads.pregraded_grades"))

        try:
            df = _load_workbook(grades_file)
            rows = _extract_rows(df, form_role)
            processing_logger.info(
                "Workbook parsed for role=%s rows=%s (mapping_token=%s)",
                form_role,
                len(rows),
                mapping_token or "",
            )
        except ValueError as exc:
            processing_logger.warning("Workbook validation failed: %s", exc)
            flash(str(exc), "danger")
            return redirect(url_for("direct_uploads.pregraded_grades"))

        grade_options = _grade_lookup(db_session, disease_id)
        if not grade_options:
            flash("No grading options defined for the selected disease.", "danger")
            return redirect(url_for("direct_uploads.pregraded_grades"))

        unique_values = sorted({row["grade_text"] for row in rows if row["grade_text"]})
        auto_mapping, unmapped_values = _auto_map_grade_values(grade_options, unique_values)
        processing_logger.info(
            "Auto mapping generated for role=%s mapped=%s unmapped=%s",
            form_role,
            list(auto_mapping.keys()),
            unmapped_values,
        )

        pending = PendingImport(
            role=form_role,
            hospital_id=hospital_id,
            lab_unit_id=lab_unit_id,
            disease_id=disease_id,
            grader_user_id=grader_user_id,
            rows=rows,
            auto_mapping=auto_mapping,
        )

        if not unmapped_values:
            job = Job(
                token=str(uuid.uuid4()),
                status="processing",
                uploader_user_id=current_user.id,
                uploader_username=current_user.username,
                uploader_ip=request.remote_addr,
                lab_unit_id=lab_unit_id,
                rejected_summary=f"{form_role.title()} grade import",
            )
            db_session.add(job)
            db_session.flush()

            grade_options = _grade_lookup(db_session, disease_id)
            success, failures, job_items = _process_rows(
                db_session,
                pending=pending,
                mapping=auto_mapping,
                job=job,
                grade_options=grade_options,
            )
            db_session.add_all(job_items)
            job.status = "completed" if failures == 0 else "error"
            if failures:
                job.error = f"{failures} of {len(rows)} rows failed."
            db_session.commit()

            flash(
                f"Imported {success} grade(s); {failures} error(s). Review job details for specifics.",
                "success" if failures == 0 else "warning",
            )
            return redirect(url_for("direct_uploads.upload_processing", job_id=job.id))

        token = str(uuid.uuid4())
        _store_pending_import(token, pending)
        processing_logger.info(
            "Stored pending import token=%s role=%s unmapped_count=%s",
            token,
            form_role,
            len(unmapped_values),
        )

        flash(
            "Some grade values could not be automatically matched. Please map them to known gradings.",
            "warning",
        )
        disease_grade_options = _grade_lookup(db_session, disease_id)
        context = {
            "modal_values": unmapped_values,
            "modal_token": token,
            "modal_role": form_role,
            "selected_hospital": hospital_id,
            "selected_lab_unit": lab_unit_id,
            "selected_disease": disease_id,
            "selected_grader": grader_user_id,
            "available_mapping": auto_mapping,
            "modal_grade_options": list(disease_grade_options.values()),
        }
        return _render_page(
            db_session,
            resident_graders=resident_graders,
            faculty_graders=faculty_graders,
            context=context,
        )
