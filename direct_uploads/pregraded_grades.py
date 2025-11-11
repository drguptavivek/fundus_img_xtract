import json
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd
from flask import current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user
from sqlalchemy import and_, select, func 
from sqlalchemy.orm import selectinload


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
    AIModel,
    utcnow,
)
from services.taskCreationServices import ensure_task
from db_transaction_manager import get_db_session
from utils.upload_eligibility import get_user_lab_unit_ids
from utils.jobUtils import get_recent_zip_uploads
from utils.dualGradingConsensusUtils import (
    create_or_update_consensus,
    update_task_state_based_on_grades,
)
import logging


processing_logger = logging.getLogger("pregraded_processing")
grades_logger = logging.getLogger("grades")


ROLE_RESIDENT = "resident"
ROLE_RESIDENT2 = "resident2"
ROLE_AI = "ai"

ROLE_DISPLAY_NAME = {
    ROLE_RESIDENT: "Resident",
    ROLE_RESIDENT2: "Resident 2",
    ROLE_AI: "AI",
}


@dataclass
class PendingImport:
    role: str
    hospital_id: int
    lab_unit_id: int
    disease_id: int
    grader_user_id: int
    rows: List[Dict[str, Optional[str]]]
    auto_mapping: Dict[str, int]
    ai_model_id: Optional[int] = None
    ai_model_name: Optional[str] = None
    ai_model_version: Optional[str] = None


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
    probability_col = f"{role}_probability" if role == ROLE_AI else None
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
        probability = None
        if probability_col:
            probability_value = row.get(probability_col, "")
            if pd.notna(probability_value):
                probability = str(probability_value).strip()
        if image_name is None:
            continue
        rows.append(
            {
                "image_name": image_name,
                "grade_text": grade_text,
                "remarks": remarks if remarks and remarks != "-" else None,
                "probability": probability,
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
        "ai_model_id": pending.ai_model_id,
        "ai_model_name": pending.ai_model_name,
        "ai_model_version": pending.ai_model_version,
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
        ai_model_id=raw.get("ai_model_id"),
        ai_model_name=raw.get("ai_model_name"),
        ai_model_version=raw.get("ai_model_version"),
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
    ai_model_id: Optional[int] = None,
    ai_model_name: Optional[str] = None,
    ai_model_version: Optional[str] = None,
) -> None:
    existing_grade = db_session.execute(
        select(Grade).where(
            Grade.task_id == task.id,
            Grade.role_slot == role,
        )
    ).scalar_one_or_none()

    grading_label = grade_options[grade_id]
    now = utcnow()

    # Log AI grade submissions to the grades log
    if role == ROLE_AI:
        from datetime import datetime, timezone
        
        # Capture previous values for logging (before updating)
        prev_grade_id = None
        prev_comment = None
        
        is_revision = existing_grade is not None
        grade_type = "revision" if is_revision else "new"
        grade_id_str = existing_grade.id if existing_grade else "N/A"
        
        if is_revision:
            prev_grade_id = existing_grade.disease_grading_id
            prev_comment = existing_grade.comment
        
        # Create log message
        # For bulk imports, we use the uploader's IP address
        ip_address = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
        
        log_message = f"Grade submission [IP: {ip_address}] [user_id: {grader_user_id}] [Task ID: {task.id}] [Slot Type: ai] [Disease ID: {task.disease_id}] [Grade: {grade_id}] [Type: {grade_type}] [Grade ID: {grade_id_str}]"
        
        # Add AI model information to the log
        if ai_model_id:
            log_message += f" [AI Model ID: {ai_model_id}]"
        if ai_model_name:
            log_message += f" [AI Model Name: {ai_model_name}]"
        if ai_model_version:
            log_message += f" [AI Model Version: {ai_model_version}]"
        
        if remarks:
            log_message += f" [Comments - {remarks}]"
            
        # If this is a revision, also log the previous grade and comment
        if is_revision and prev_grade_id is not None:
            prev_comment_display = prev_comment if prev_comment else "None"
            log_message += f" [Previous Grade: {prev_grade_id}] [Previous Comment: {prev_comment_display}]"
        
        # Log using dedicated grades logger
        grades_logger.info(log_message)

    if existing_grade:
        existing_grade.grader_user_id = grader_user_id
        existing_grade.disease_grading_id = grade_id
        existing_grade.comment = remarks
        existing_grade.disease_name = grading_label.disease.name if grading_label.disease else None
        existing_grade.grade_name = grading_label.impression
        existing_grade.grade_description = grading_label.guidelines
        existing_grade.updated_at = now
        existing_grade.ai_model_id = ai_model_id
        existing_grade.ai_model_name = ai_model_name
        existing_grade.ai_model_version = ai_model_version
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
                ai_model_id=ai_model_id,
                ai_model_name=ai_model_name,
                ai_model_version=ai_model_version,
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
        probability = row.get("probability")
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
        if pending.role == ROLE_AI:
            parts = []
            if probability:
                parts.append(f"AI probability: {probability}")
            if remarks:
                parts.append(remarks)
            final_comment = "; ".join(parts) if parts else None
        else:
            final_comment = remarks
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
                # Log the error without traceback and continue processing
                current_app.logger.warning(
                    "Failed to import grade for %s: Image '%s' not found in pre-graded uploads for the selected hospital/lab/disease.",
                    filename, filename
                )
                item_state = "error"
                detail = f"Image '{filename}' not found in pre-graded uploads for the selected hospital/lab/disease."
                failures += 1
                # Skip to job_items creation and continue with next row
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
                continue  # Skip to next row without processing grades

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

            if pending.role == ROLE_AI and pending.ai_model_id:
                ai_model = db_session.get(AIModel, pending.ai_model_id)
                ai_name = ai_model.name if ai_model else None
                ai_version = ai_model.version if ai_model else None
            else:
                ai_name = None
                ai_version = None

            _apply_grade(
                db_session,
                task=task,
                grade_id=grade_id,
                grader_user_id=pending.grader_user_id,
                role=pending.role,
                remarks=final_comment,
                grade_options=grade_options,
                ai_model_id=pending.ai_model_id if pending.role == ROLE_AI else None,
                ai_model_name=ai_name if pending.role == ROLE_AI else None,
                ai_model_version=ai_version if pending.role == ROLE_AI else None,
            )

            if pending.role in (ROLE_RESIDENT, ROLE_RESIDENT2):
                update_task_state_based_on_grades(task.id, db=db_session)
                if pending.role == ROLE_RESIDENT2:
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

    processing_logger.info(
        "job_id=%s role=%s completed success=%s failures=%s",
        job.id,
        pending.role,
        success,
        failures,
    )
    return success, failures, job_items


def _render_page(
    db_session,
    *,
    resident_graders: List[User],
    resident2_graders: List[User],
    ai_models: List[AIModel],
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
            "resident2_graders": resident2_graders,
            "ai_models": ai_models,
            "grade_options": grade_options,
        }
    )
    return render_template("direct_uploads/pregraded_grades.html", **context)


@bp.route("/direct/pregraded/grades", methods=["GET", "POST"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin")
def pregraded_grades():
    with get_db_session() as db_session:
        resident_graders = _eligible_graders(db_session, ["resident", "ophthalmologist"])
        resident2_graders = _eligible_graders(db_session, ["ophthalmologist"])
        ai_models = (
            db_session.execute(
                select(AIModel).order_by(AIModel.name, AIModel.version)
            )
            .scalars()
            .all()
        )

        if request.method == "GET":
            # Check if there's stored form data from a previous submission
            stored_form_data = session.get("pregraded_form_submission")
            context = {}
            
            if stored_form_data:
                # Pass the stored form data to the template
                context.update({
                    "selected_hospital": stored_form_data.get("hospital_id"),
                    "selected_lab_unit": stored_form_data.get("lab_unit_id"),
                    "selected_disease": stored_form_data.get("disease_id"),
                    "selected_area": stored_form_data.get("area_id"),
                    "selected_grader": stored_form_data.get("grader_user_id"),
                    "selected_ai_model_id": stored_form_data.get("ai_model_id"),
                })
                # Clear the stored data after retrieving it
                del session["pregraded_form_submission"]
            
            # Get recent pregraded grade uploads for display
            recent_uploads = get_recent_zip_uploads(limit=5, job_type="resident excel")
            # Also get resident2 and AI excel uploads
            recent_uploads.extend(get_recent_zip_uploads(limit=5, job_type="resident2 excel"))
            recent_uploads.extend(get_recent_zip_uploads(limit=5, job_type="ai excel"))
            # Sort by created_at date and take the top 5
            recent_uploads.sort(key=lambda x: x['job']['created_at'], reverse=True)
            recent_uploads = recent_uploads[:5]
                
            context["recent_uploads"] = recent_uploads
                
            return _render_page(
                db_session,
                resident_graders=resident_graders,
                resident2_graders=resident2_graders,
                ai_models=ai_models,
                context=context,
            )

        form_role = request.form.get("form_role")
        if form_role not in {ROLE_RESIDENT, ROLE_RESIDENT2, ROLE_AI}:
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

            # Get the original filename from the session (stored during form processing)
            excel_filename = session.get("pregraded_excel_filename", "Unknown Excel File")
            
            display_role = ROLE_DISPLAY_NAME.get(pending.role, pending.role.title())
            summary = f"{display_role} grade import"
            if pending.role == ROLE_AI and pending.ai_model_id:
                summary = f"AI grade import (model {pending.ai_model_id})"
            
            # Determine upload type based on role
            upload_type = f"{pending.role} excel"
            
            job = Job(
                token=str(uuid.uuid4()),
                status="processing",
                uploader_user_id=current_user.id,
                uploader_username=current_user.username,
                uploader_ip=request.remote_addr,
                lab_unit_id=pending.lab_unit_id,
                rejected_summary=summary,
                excel_filename=excel_filename,
                upload_type=upload_type,
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
            
            # Clear the Excel filename from session
            if "pregraded_excel_filename" in session:
                del session["pregraded_excel_filename"]

            flash(
                f"Imported {success} grade(s); {failures} error(s). Review job details for specifics.",
                "success" if failures == 0 else "warning",
            )
            return redirect(url_for("jobs.upload_processing", job_id=job.token))

        hospital_id = request.form.get("hospital_id", type=int)
        lab_unit_id = request.form.get("lab_unit_id", type=int)
        disease_id = request.form.get("disease_id", type=int)
        area_id = request.form.get("area_id", type=int)
        grader_user_id = request.form.get("grader_user_id", type=int)
        ai_model_id = request.form.get("ai_model_id", type=int) if form_role == ROLE_AI else None

        field_checks = [
            ("Hospital", hospital_id),
            ("Lab Unit", lab_unit_id),
            ("Disease", disease_id),
        ]
        if form_role != ROLE_AI:
            field_checks.append(("Grader", grader_user_id))
            
        # Store form data in session for potential validation failure
        form_data = {
            "form_role": form_role,
            "hospital_id": hospital_id,
            "lab_unit_id": lab_unit_id,
            "disease_id": disease_id,
            "area_id": area_id,
        }
        if form_role != ROLE_AI:
            form_data["grader_user_id"] = grader_user_id
        else:
            form_data["ai_model_id"] = ai_model_id
            
        session["pregraded_form_submission"] = form_data
        
        for field_name, value in field_checks:
            if value is None:
                processing_logger.warning("Missing field %s for role %s", field_name, form_role)
                flash(f"{field_name} must be selected.", "danger")
                return redirect(url_for("direct_uploads.pregraded_grades"))

        grades_file = request.files.get("grades_file")
        if not grades_file or not grades_file.filename:
            processing_logger.warning("No file uploaded for role %s", form_role)
            flash("Please select an Excel file to upload.", "danger")
            return redirect(url_for("direct_uploads.pregraded_grades"))
            
        # Store the Excel filename in session for later use
        session["pregraded_excel_filename"] = grades_file.filename
            
        # Clear form data from session after successful validation
        if "pregraded_form_submission" in session:
            del session["pregraded_form_submission"]

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

        if form_role == ROLE_AI:
            effective_grader_id = current_user.id
            ai_model_id = request.form.get("ai_model_id", type=int)
            ai_model_name = (request.form.get("ai_model_name") or "").strip()
            ai_model_version = (request.form.get("ai_model_version") or "").strip()
            ai_model_description = (request.form.get("ai_model_description") or "").strip()

            if ai_model_id:
                model = db_session.get(AIModel, ai_model_id)
                if not model:
                    processing_logger.warning("Selected AI model id %s not found", ai_model_id)
                    flash("Selected AI model not found.", "danger")
                    return redirect(url_for("direct_uploads.pregraded_grades"))
                ai_model_name_value = model.name
                ai_model_version_value = model.version
            else:
                if not ai_model_name or not ai_model_version:
                    processing_logger.warning("AI model creation missing name/version")
                    flash("Provide AI model name and version or select an existing model.", "danger")
                    return redirect(url_for("direct_uploads.pregraded_grades"))
                existing_model = db_session.execute(
                    select(AIModel).where(
                        func.lower(AIModel.name) == ai_model_name.lower(),
                        func.lower(AIModel.version) == ai_model_version.lower(),
                    )
                ).scalar_one_or_none()
                if existing_model:
                    model = existing_model
                    ai_model_id = model.id
                    ai_model_name_value = model.name
                    ai_model_version_value = model.version
                else:
                    model = AIModel(
                        name=ai_model_name,
                        version=ai_model_version,
                        description=ai_model_description or None,
                    )
                    db_session.add(model)
                    db_session.commit()
                    processing_logger.info(
                        "Created AI model id=%s name=%s version=%s",
                        model.id,
                        model.name,
                        model.version,
                    )
                    ai_model_id = model.id
                    ai_model_name_value = model.name
                    ai_model_version_value = model.version
        else:
            ai_model_id = None
            ai_model_name_value = None
            ai_model_version_value = None
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
            if form_role == ROLE_RESIDENT2 and "ophthalmologist" not in role_names:
                processing_logger.warning("Grader %s lacks resident2 eligibility", grader_user_id)
                flash("Selected user is not eligible for resident2 grading.", "danger")
                return redirect(url_for("direct_uploads.pregraded_grades"))
            effective_grader_id = grader_user_id

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
            grader_user_id=effective_grader_id,
            rows=rows,
            auto_mapping=auto_mapping,
            ai_model_id=ai_model_id,
            ai_model_name=ai_model_name_value,
            ai_model_version=ai_model_version_value,
        )

        if not unmapped_values:
            # Get the original filename from the uploaded file
            excel_filename = grades_file.filename if grades_file else "Unknown Excel File"
            
            display_role = ROLE_DISPLAY_NAME.get(form_role, form_role.title())
            summary = f"{display_role} grade import"
            if form_role == ROLE_AI and ai_model_id:
                summary = f"AI grade import (model {ai_model_id})"
            
            # Determine upload type based on role
            upload_type = f"{form_role} excel"
            
            job = Job(
                token=str(uuid.uuid4()),
                status="processing",
                uploader_user_id=current_user.id,
                uploader_username=current_user.username,
                uploader_ip=request.remote_addr,
                lab_unit_id=lab_unit_id,
                rejected_summary=summary,
                excel_filename=excel_filename,
                upload_type=upload_type,
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
            
            # Clear the Excel filename from session
            if "pregraded_excel_filename" in session:
                del session["pregraded_excel_filename"]

            flash(
                f"Imported {success} grade(s); {failures} error(s). Review job details for specifics.",
                "success" if failures == 0 else "warning",
            )
            return redirect(url_for("jobs.upload_processing", job_id=job.token))

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
            "selected_grader": effective_grader_id,
            "selected_ai_model_id": ai_model_id,
            "available_mapping": auto_mapping,
            "modal_grade_options": list(disease_grade_options.values()),
        }
        return _render_page(
            db_session,
            resident_graders=resident_graders,
            resident2_graders=resident2_graders,
            ai_models=ai_models,
            context=context,
        )


@bp.route("/direct/pregraded/grades/recent", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin")
def recent_pregraded_grades():
    """Display a list of recent Excel grading files that were uploaded."""
    with get_db_session() as db_session:
        # Query recent jobs that are pre-graded grade imports
        # Filter by upload_type ending with "excel"
        recent_jobs = (
            db_session.query(Job)
            .filter(
                Job.upload_type.like("%excel"),
                Job.uploader_user_id == current_user.id if not current_user.has_role("admin", "data_manager") else True
            )
            .options(selectinload(Job.lab_unit).selectinload(LabUnit.hospital))
            .order_by(Job.created_at.desc())
            .limit(10)
            .all()
        )
        
        # Prepare data for template
        grade_imports = []
        for job in recent_jobs:
            # Determine the type from the upload_type
            import_type = "Unknown"
            if job.upload_type:
                if job.upload_type == "resident excel":
                    import_type = "Resident"
                elif job.upload_type == "resident2 excel":
                    import_type = "Resident 2"
                elif job.upload_type == "ai excel":
                    import_type = "AI"
            
            # Count successful and failed items
            success_count = len([item for item in job.items if item.state == "completed"])
            error_count = len([item for item in job.items if item.state == "error"])
            
            grade_imports.append({
                "id": job.id,
                "token": job.token,
                "filename": job.excel_filename or "Unknown Excel File",
                "type": import_type,
                "upload_type": job.upload_type,
                "created_at": job.created_at,
                "success_count": success_count,
                "error_count": error_count,
                "total_count": success_count + error_count,
                "status": job.status,
                "lab_unit": job.lab_unit.name if job.lab_unit else None,
                "hospital": job.lab_unit.hospital.name if job.lab_unit and job.lab_unit.hospital else None,
            })
        
        return render_template("direct_uploads/recent_grades.html", grade_imports=grade_imports)
