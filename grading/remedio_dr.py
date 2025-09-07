from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.orm import selectinload
from sqlalchemy import and_
import random

from auth.roles import roles_required
from models import Session, PatientEncounters, EncounterFile, ImageGrading


@roles_required("admin", "resident", "ophthalmologist")
def remedio_dr_image(uuid: str):
    db = Session()
    try:
        ef = (
            db.query(EncounterFile)
              .options(selectinload(EncounterFile.gradings))
              .filter(EncounterFile.uuid == uuid)
              .first()
        )
        if not ef:
            from flask import abort
            abort(404)
        enc = db.query(PatientEncounters).filter(PatientEncounters.id == ef.patient_encounter_id).first()
        my_grading = (
            db.query(ImageGrading)
              .filter(
                  ImageGrading.encounter_file_id == ef.id,
                  ImageGrading.graded_for == 'dr',
                  ImageGrading.grader_user_id == getattr(current_user, 'id', None),
              )
              .order_by(ImageGrading.updated_at.desc(), ImageGrading.id.desc())
              .first()
        )
    finally:
        db.close()

    # Basic DR impressions; adjust as needed
    dr_impressions = [
        "No DR",
        "Mild NPDR",
        "Moderate NPDR",
        "Severe NPDR",
        "PDR",
        "Not gradable",
    ]
    return render_template("grading/remedio_dr_image.html", image=ef, encounter=enc, impressions=dr_impressions, my_grading=my_grading)


@roles_required("admin", "resident", "ophthalmologist")
def remedio_dr_grade():
    ef_id = request.form.get("ef_id")
    ef_uuid = (request.form.get("ef_uuid") or request.form.get("uuid") or "").strip()
    impression = (request.form.get("impression") or "").strip()
    remarks = (request.form.get("remarks") or "").strip() or None
    ef = None
    db = Session()
    try:
        if ef_uuid:
            ef = db.query(EncounterFile).filter(EncounterFile.uuid == ef_uuid).first()
        else:
            try:
                ef_id_int = int(ef_id)
                ef = db.query(EncounterFile).filter(EncounterFile.id == ef_id_int).first()
            except Exception:
                ef = None
        if not ef:
            flash("Invalid image.", "danger")
            return redirect(request.referrer or url_for("grading.index"))
        
        # Check if image is locked
        if ef.is_locked:
            flash("This image has been locked for editing after matching. No further changes allowed.", "danger")
            return redirect(request.referrer or url_for("grading.index"))
    finally:
        db.close()

    role = None
    try:
        if current_user.has_role('ophthalmologist'):
            role = 'consultant'
        elif current_user.has_role('resident'):
            role = 'resident'
        elif current_user.has_role('admin'):
            role = 'admin'
    except Exception:
        role = 'unknown'

    # Accept anything for DR impressions (free-form), but ensure non-empty
    if not impression:
        flash("Please select a DR impression.", "warning")
        return redirect(request.referrer or url_for("grading.index"))

    db = Session()
    try:
        user_id = getattr(current_user, 'id', None)
        username = getattr(current_user, 'username', None)
        existing = (
            db.query(ImageGrading)
              .filter(ImageGrading.encounter_file_id == ef.id,
                      ImageGrading.grader_user_id == user_id,
                      ImageGrading.grader_role == role,
                      ImageGrading.graded_for == 'dr')
              .first()
        )
        
        # Check if existing grading is locked
        if existing and ef.is_locked:
            flash("This image has been locked for editing after matching. No further changes allowed.", "danger")
            return redirect(url_for('grading.remedio_dr_image', uuid=ef.uuid))
        
        if existing:
            existing.impression = impression
            existing.remarks = remarks
            db.add(existing)
        else:
            db.add(ImageGrading(
                encounter_file_id=ef.id,
                grader_user_id=user_id,
                grader_username=username,
                grader_role=role,
                graded_for='dr',
                impression=impression,
                remarks=remarks,
            ))
        db.commit()
        flash("DR grading saved.", "success")

        action = (request.form.get('action') or '').strip().lower()
        if action == 'save_next':
            grader_id = getattr(current_user, 'id', None)
            cand_q = (
                db.query(EncounterFile)
                  .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
                  .outerjoin(
                      ImageGrading,
                      and_(
                          ImageGrading.encounter_file_id == EncounterFile.id,
                          ImageGrading.graded_for == 'dr',
                          ImageGrading.grader_user_id == grader_id,
                      ),
                  )
                  .filter(PatientEncounters.capture_date_dt.isnot(None))
                  .filter(EncounterFile.file_type == 'image')
                  .filter(ImageGrading.id.is_(None))
                  .filter(EncounterFile.is_locked == False)  # Only unlocked images
                  .order_by(PatientEncounters.capture_date_dt.desc(), EncounterFile.id.desc())
                  .limit(50)
            )
            candidates = cand_q.all()
            choice = random.choice(candidates) if candidates else None
            if choice and choice.uuid:
                return redirect(url_for('grading.remedio_dr_image', uuid=choice.uuid))
            else:
                flash("No further ungraded DR images found.", "info")
        elif action == 'save_close':
            return redirect(url_for('grading.index'))
        return redirect(url_for('grading.remedio_dr_image', uuid=ef.uuid))
    finally:
        db.close()


@roles_required("admin", "resident", "ophthalmologist")
def remedio_dr_remove():
    ef_uuid = (request.form.get("ef_uuid") or request.form.get("uuid") or "").strip()
    grading_id_raw = request.form.get("grading_id")
    if not ef_uuid or not grading_id_raw:
        flash("Invalid request.", "danger")
        return redirect(request.referrer or url_for("grading.index"))
    try:
        grading_id = int(grading_id_raw)
    except Exception:
        flash("Invalid grading id.", "danger")
        return redirect(request.referrer or url_for("grading.index"))

    db = Session()
    try:
        ef = db.query(EncounterFile).filter(EncounterFile.uuid == ef_uuid).first()
        if not ef:
            flash("Image not found.", "danger")
            return redirect(url_for('grading.index'))
        
        # Check if image is locked
        if ef.is_locked:
            flash("This image has been locked for editing after matching. No further changes allowed.", "danger")
            return redirect(url_for('grading.remedio_dr_image', uuid=ef.uuid))

        user_id = getattr(current_user, 'id', None)
        gr = (
            db.query(ImageGrading)
              .filter(ImageGrading.id == grading_id,
                      ImageGrading.encounter_file_id == ef.id,
                      ImageGrading.grader_user_id == user_id,
                      ImageGrading.graded_for == 'dr')
              .first()
        )
        if not gr:
            flash("No matching DR grading found to remove.", "info")
            return redirect(url_for('grading.remedio_dr_image', uuid=ef.uuid))
        db.delete(gr)
        db.commit()
        flash("Removed this DR grading instance.", "success")
        return redirect(url_for('grading.remedio_dr_image', uuid=ef.uuid))
    finally:
        db.close()