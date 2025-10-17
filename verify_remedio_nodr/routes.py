from __future__ import annotations

from datetime import datetime, date as _date
from typing import Any

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload, selectinload

from auth.roles import roles_required
from models import (
    Disease,
    DiabeticRetinopathyReport,
    EncounterFile,
    LabUnit,
    PatientEncounters,
    Session,
    utcnow,
)
from services.taskCreationServices import can_unverify_image, ensure_task, remove_pending_tasks
from utils.upload_eligibility import get_user_lab_unit_ids

from . import bp


DR_NAME_CANDIDATES = ("diabetic retinopathy", "dr")


def _get_dr_disease(db: Session) -> Disease | None:
    lowered = [name.lower() for name in DR_NAME_CANDIDATES]
    return (
        db.query(Disease)
        .filter(func.lower(Disease.name).in_(lowered))
        .first()
    )


def _base_encounter_query(db: Session, restricted_lab_units: set[int] | None):
    query = (
        db.query(PatientEncounters)
        .outerjoin(DiabeticRetinopathyReport, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
        .filter(DiabeticRetinopathyReport.id.is_(None))
        .filter(PatientEncounters.zip_file_id.isnot(None))
    )
    if restricted_lab_units is not None:
        query = query.filter(PatientEncounters.lab_unit_id.in_(restricted_lab_units))
    return query


@bp.route("/list", methods=["GET"])
@roles_required("admin", "optometrist", "data_manager")
def nodr_list():
    page = request.args.get("page", default=1, type=int) or 1
    selected_date = (request.args.get("date") or "").strip() or None
    ver = (request.args.get("ver") or "all").strip().lower()
    if ver not in {"all", "yes", "no"}:
        ver = "all"
    page = max(1, page)

    db = Session()
    try:
        restricted_lab_units: set[int] | None = None
        if not (current_user.has_role("admin") or current_user.has_role("data_manager")):
            allowed = get_user_lab_unit_ids(current_user.id)
            restricted_lab_units = set(allowed) if allowed else {-1}

        base_query = _base_encounter_query(db, restricted_lab_units)

        date_rows = (
            base_query.filter(PatientEncounters.capture_date_dt.isnot(None))
            .with_entities(PatientEncounters.capture_date_dt)
            .distinct()
            .order_by(PatientEncounters.capture_date_dt.desc())
            .all()
        )
        dates: list[_date] = [row[0] for row in date_rows]

        unv_rows = (
            base_query.filter(PatientEncounters.capture_date_dt.isnot(None))
            .filter(
                (PatientEncounters.encounter_verified_status.is_(None))
                | (PatientEncounters.encounter_verified_status != "verified")
            )
            .with_entities(PatientEncounters.capture_date_dt)
            .distinct()
            .order_by(PatientEncounters.capture_date_dt.desc())
            .all()
        )
        most_recent_unverified = unv_rows[0][0] if unv_rows else None

        ver_rows = (
            base_query.filter(PatientEncounters.capture_date_dt.isnot(None))
            .filter(PatientEncounters.encounter_verified_status == "verified")
            .with_entities(PatientEncounters.capture_date_dt)
            .distinct()
            .order_by(PatientEncounters.capture_date_dt.desc())
            .all()
        )
        most_recent_verified = ver_rows[0][0] if ver_rows else None

        total_pages = max(1, len(dates))
        focus_idx = 0
        sel_dt: _date | None = None
        if selected_date:
            try:
                sel_dt = datetime.strptime(selected_date, "%Y-%m-%d").date()
            except Exception:
                sel_dt = None
        if sel_dt and sel_dt in dates:
            focus_idx = dates.index(sel_dt)
        else:
            focus_idx = min(max(1, page), total_pages) - 1

        focus_date = dates[focus_idx] if dates else None
        page = focus_idx + 1 if total_pages else 1
        selected_date = focus_date.isoformat() if focus_date else None

        recent_unverified_url = None
        if most_recent_unverified and most_recent_unverified in dates:
            ru_idx = dates.index(most_recent_unverified) + 1
            recent_unverified_url = url_for("verify_remedio_nodr.nodr_list", page=ru_idx, ver="no")

        recent_verified_url = None
        if most_recent_verified and most_recent_verified in dates:
            rv_idx = dates.index(most_recent_verified) + 1
            recent_verified_url = url_for("verify_remedio_nodr.nodr_list", page=rv_idx, ver="yes")

        items: list[PatientEncounters] = []
        if focus_date is not None:
            items_query = (
                base_query
                .filter(PatientEncounters.capture_date_dt == focus_date)
                .order_by(PatientEncounters.id.desc())
                .options(
                    selectinload(PatientEncounters.lab_unit).selectinload(LabUnit.hospital),
                    selectinload(PatientEncounters.encounter_files),
                )
            )
            rows = items_query.all()
            if ver == "yes":
                items = [enc for enc in rows if enc.encounter_verified_status == "verified"]
            elif ver == "no":
                items = [enc for enc in rows if enc.encounter_verified_status != "verified"]
            else:
                items = rows
            
            # Check if each verified encounter can be unverified
            items_with_unverify_status = []
            for enc in items:
                can_unverify = True
                if enc.encounter_verified_status == "verified":
                    # Check if all images have only pending tasks
                    for ef in enc.encounter_files or []:
                        if ef.file_type == 'image' and not can_unverify_image(db, kind="encounter", image_id=ef.id):
                            can_unverify = False
                            break
                items_with_unverify_status.append({
                    'encounter': enc,
                    'can_unverify': can_unverify
                })

        my_recent_verified: list[PatientEncounters] = []
        try:
            uname = getattr(current_user, "username", None)
            if uname:
                recent_query = (
                    base_query
                    .filter(PatientEncounters.encounter_verified_status == "verified")
                    .filter(PatientEncounters.encounter_verified_by == uname)
                    .order_by(PatientEncounters.encounter_verified_at.desc(), PatientEncounters.id.desc())
                    .options(
                        selectinload(PatientEncounters.lab_unit).selectinload(LabUnit.hospital),
                        selectinload(PatientEncounters.encounter_files),
                    )
                    .limit(20)
                )
                my_recent_verified = recent_query.all()
        except Exception:
            my_recent_verified = []
    finally:
        db.close()

    has_prev = page > 1
    has_next = page < total_pages

    return render_template(
        "verify_remedio_nodr/list.html",
        items=items_with_unverify_status,
        page=page,
        total=len(items),
        total_pages=total_pages,
        has_prev=has_prev,
        has_next=has_next,
        prev_url=url_for("verify_remedio_nodr.nodr_list", page=page-1, ver=ver) if has_prev else None,
        next_url=url_for("verify_remedio_nodr.nodr_list", page=page+1, ver=ver) if has_next else None,
        selected_date=selected_date,
        ver=ver,
        recent_unverified_url=recent_unverified_url,
        recent_verified_url=recent_verified_url,
        my_recent_verified=my_recent_verified,
    )


def _load_encounter(db: Session, encounter_id: int) -> PatientEncounters | None:
    return (
        db.query(PatientEncounters)
        .options(
            joinedload(PatientEncounters.lab_unit).joinedload(LabUnit.hospital),
            selectinload(PatientEncounters.encounter_files),
            selectinload(PatientEncounters.encounter_files).joinedload(EncounterFile.patient_encounter),
        )
        .filter(PatientEncounters.id == encounter_id)
        .first()
    )


@bp.route("/edit/<int:encounter_id>", methods=["GET", "POST"])
@roles_required("admin", "optometrist", "data_manager")
def nodr_edit(encounter_id: int):
    page_hint = request.args.get("page", type=int)

    db = Session()
    try:
        encounter = _load_encounter(db, encounter_id)
        if not encounter:
            from flask import abort
            abort(404)

        lab_unit_id = getattr(encounter, "lab_unit_id", None)
        if lab_unit_id is not None and not (current_user.has_role('admin') or current_user.has_role('data_manager')):
            allowed_lab_units = get_user_lab_unit_ids(current_user.id)
            if lab_unit_id not in allowed_lab_units:
                flash("You don't have permission to access this encounter.", "danger")
                return redirect(url_for("verify_remedio_nodr.nodr_list"))

        if request.method == "POST":
            new_pid = (request.form.get("patient_id") or "").strip()
            if new_pid:
                encounter.patient_id = new_pid
            date_str = (request.form.get("capture_date_dt") or "").strip()
            if date_str:
                try:
                    d = datetime.strptime(date_str, "%Y-%m-%d").date()
                    encounter.capture_date_dt = d
                    encounter.capture_date = d.isoformat()
                except Exception:
                    pass
            db.add(encounter)
            db.commit()
            flash("Encounter details saved.", "success")
            return redirect(url_for("verify_remedio_nodr.nodr_edit", encounter_id=encounter_id, page=page_hint))

        # Determine prev/next encounters for navigation based on capture date/id
        focus_date = encounter.capture_date_dt
        prev_encounter = (
            _base_encounter_query(db, None)
            .filter(
                (PatientEncounters.capture_date_dt > focus_date)
                | (
                    (PatientEncounters.capture_date_dt == focus_date)
                    & (PatientEncounters.id > encounter.id)
                )
            )
            .order_by(PatientEncounters.capture_date_dt.asc().nullslast(), PatientEncounters.id.asc())
            .first()
        )
        next_encounter = (
            _base_encounter_query(db, None)
            .filter(
                (PatientEncounters.capture_date_dt < focus_date)
                | (
                    (PatientEncounters.capture_date_dt == focus_date)
                    & (PatientEncounters.id < encounter.id)
                )
            )
            .order_by(PatientEncounters.capture_date_dt.desc().nullslast(), PatientEncounters.id.desc())
            .first()
        )
    finally:
        db.close()

    return render_template(
        "verify_remedio_nodr/edit.html",
        encounter=encounter,
        prev_url=url_for("verify_remedio_nodr.nodr_edit", encounter_id=prev_encounter.id) if prev_encounter else None,
        next_url=url_for("verify_remedio_nodr.nodr_edit", encounter_id=next_encounter.id) if next_encounter else None,
        back_url=url_for("verify_remedio_nodr.nodr_list", page=page_hint) if page_hint else url_for("verify_remedio_nodr.nodr_list"),
    )


@bp.route("/edit/<int:encounter_id>/mark_eye", methods=["POST"])
@roles_required("admin", "optometrist", "data_manager")
def nodr_mark_eye(encounter_id: int):
    side = (request.form.get("side") or "").strip().lower()
    ef_id = request.form.get("ef_id")
    if side not in {"right", "left", "cannot_tell"}:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": False, "error": "invalid_side"}, 400
        flash("Invalid selection.", "danger")
        return redirect(url_for("verify_remedio_nodr.nodr_edit", encounter_id=encounter_id))
    try:
        ef_id_int = int(ef_id)
    except Exception:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": False, "error": "invalid_image"}, 400
        flash("Invalid image id.", "danger")
        return redirect(url_for("verify_remedio_nodr.nodr_edit", encounter_id=encounter_id))

    db = Session()
    try:
        encounter = db.query(PatientEncounters).filter(PatientEncounters.id == encounter_id).first()
        if not encounter:
            from flask import abort
            abort(404)
        ef = db.query(EncounterFile).filter(EncounterFile.id == ef_id_int).first()
        if not ef or ef.patient_encounter_id != encounter.id:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
                return {"ok": False, "error": "not_found"}, 404
            flash("Image not found for this encounter.", "danger")
            return redirect(url_for("verify_remedio_nodr.nodr_edit", encounter_id=encounter_id))
        ef.eye_side = side
        db.add(ef)
        db.commit()
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": True, "ef_id": ef.id, "side": ef.eye_side}
        flash("Image laterality updated.", "success")
    finally:
        db.close()
    return redirect(url_for("verify_remedio_nodr.nodr_edit", encounter_id=encounter_id))


@bp.route("/edit/<int:encounter_id>/verify", methods=["POST"])
@roles_required("admin", "optometrist", "data_manager")
def nodr_verify(encounter_id: int):
    db = Session()
    try:
        encounter = _load_encounter(db, encounter_id)
        if not encounter:
            from flask import abort
            abort(404)

        missing = [ef for ef in encounter.encounter_files if ef.file_type == 'image' and (ef.eye_side not in {'right', 'left', 'cannot_tell'})]
        if missing:
            msg = f"{len(missing)} image(s) still untagged; cannot verify."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
                return {"ok": False, "error": "incomplete", "message": msg}, 400
            flash(msg, "danger")
            return redirect(url_for("verify_remedio_nodr.nodr_edit", encounter_id=encounter_id))

        encounter.encounter_verified_status = 'verified'
        encounter.encounter_verified_by = getattr(current_user, 'username', 'unknown')
        encounter.encounter_verified_at = utcnow()
        db.add(encounter)
        db.commit()

        try:
            dr_disease = _get_dr_disease(db)
            if dr_disease:
                images = db.query(EncounterFile).filter(EncounterFile.patient_encounter_id == encounter.id).all()
                for image in images:
                    try:
                        ensure_task(image.uuid, dr_disease.id)
                        current_app.logger.info("Created DR grading task for image UUID %s via No-DR verification", image.uuid)
                    except Exception as task_error:
                        current_app.logger.exception("Failed to create DR grading task for image UUID %s: %s", image.uuid, task_error)
            else:
                current_app.logger.warning("DR disease not found when verifying encounter %s", encounter.id)
        except Exception as e:
            current_app.logger.exception("Failed to create grading tasks for no-DR encounter %s: %s", encounter.id, e)

        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": True, "status": encounter.encounter_verified_status, "by": encounter.encounter_verified_by}
        flash("Encounter verified.", "success")
        return redirect(url_for("verify_remedio_nodr.nodr_edit", encounter_id=encounter_id))
    finally:
        db.close()


@bp.route("/edit/<int:encounter_id>/unverify", methods=["POST"])
@roles_required("admin", "optometrist", "data_manager")
def nodr_unverify(encounter_id: int):
    db = Session()
    try:
        encounter = _load_encounter(db, encounter_id)
        if not encounter:
            from flask import abort
            abort(404)

        # Check if we can unverify the encounter (all tasks must be pending)
        images = [ef for ef in encounter.encounter_files if ef.file_type == 'image']
        can_unverify = True
        for image in images:
            if not can_unverify_image(db, kind="encounter", image_id=image.id):
                can_unverify = False
                break
        
        if not can_unverify:
            msg = "Cannot unverify encounter - some images have non-pending tasks."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
                return {"ok": False, "error": "tasks_in_progress", "message": msg}, 400
            else:
                flash(msg, "danger")
                return redirect(url_for("verify_remedio_nodr.nodr_edit", encounter_id=encounter_id))

        # Proceed with unverification
        encounter.encounter_verified_status = None
        encounter.encounter_verified_by = None
        encounter.encounter_verified_at = None
        db.add(encounter)
        db.commit()

        try:
            dr_disease = _get_dr_disease(db)
            if dr_disease:
                for image in images:
                    try:
                        removed_count = remove_pending_tasks(db, kind="encounter", image_id=image.id)
                        if removed_count > 0:
                            current_app.logger.info("Removed %d pending DR tasks for no-DR encounter image %s", removed_count, image.uuid)
                    except Exception as task_error:
                        current_app.logger.exception("Failed to remove DR tasks for no-DR encounter image %s: %s", image.uuid, task_error)
            else:
                current_app.logger.warning("DR disease not found when attempting to unverify encounter %s", encounter.id)
        except Exception as e:
            current_app.logger.exception("Failed to remove tasks during no-DR encounter unverification %s: %s", encounter.id, e)

        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": True, "status": encounter.encounter_verified_status}
        flash("Encounter unverified.", "warning")
        return redirect(url_for("verify_remedio_nodr.nodr_edit", encounter_id=encounter_id))
    finally:
        db.close()
