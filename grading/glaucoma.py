from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.orm import selectinload
from sqlalchemy import and_
import random

from auth.roles import roles_required
from models import Session, PatientEncounters, EncounterFile, ImageGrading


@roles_required("admin", "optometrist", "ophthalmologist")
def glaucoma_image(uuid: str):
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
        # Fetch the current user's most recent glaucoma grading for this image (to prefill form)
        my_grading = (
            db.query(ImageGrading)
              .filter(
                  ImageGrading.encounter_file_id == ef.id,
                  ImageGrading.graded_for == 'glaucoma',
                  ImageGrading.grader_user_id == getattr(current_user, 'id', None),
              )
              .order_by(ImageGrading.updated_at.desc(), ImageGrading.id.desc())
              .first()
        )
    finally:
        db.close()

    impressions = ["Normal", "Glaucoma Suspect", "Glaucoma", "Other Retinal", "Not gradable"]
    return render_template("grading/image_glaucoma.html", image=ef, encounter=enc, impressions=impressions, my_grading=my_grading)


@roles_required("admin", "optometrist", "ophthalmologist")
def glaucoma_grade():
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
    finally:
        db.close()

    role = None
    try:
        if current_user.has_role('ophthalmologist'):
            role = 'ophthalmologist'
        elif current_user.has_role('optometrist'):
            role = 'optometrist'
        elif current_user.has_role('admin'):
            role = 'admin'
    except Exception:
        role = 'unknown'

    if impression not in {"Normal", "Glaucoma Suspect", "Glaucoma", "Other Retinal", "Not gradable"}:
        flash("Please select a valid impression.", "warning")
        return redirect(request.referrer or url_for("screenings.list_screenings"))

    db = Session()
    try:
        # Upsert by image + user + role
        user_id = getattr(current_user, 'id', None)
        username = getattr(current_user, 'username', None)
        existing = (
            db.query(ImageGrading)
              .filter(ImageGrading.encounter_file_id == ef.id,
                      ImageGrading.grader_user_id == user_id,
                      ImageGrading.grader_role == role,
                      ImageGrading.graded_for == 'glaucoma')
              .first()
        )
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
                graded_for='glaucoma',
                impression=impression,
                remarks=remarks,
            ))
        db.commit()
        flash("Grading saved.", "success")

        # Save & Next flow
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
                          ImageGrading.graded_for == 'glaucoma',
                          ImageGrading.grader_user_id == grader_id,
                      ),
                  )
                  .filter(PatientEncounters.capture_date_dt.isnot(None))
                  .filter(EncounterFile.file_type == 'image')
                  .filter(ImageGrading.id.is_(None))
                  .order_by(PatientEncounters.capture_date_dt.desc(), EncounterFile.id.desc())
                  .limit(50)
            )
            candidates = cand_q.all()
            choice = random.choice(candidates) if candidates else None
            if choice and choice.uuid:
                return redirect(url_for('grading.glaucoma_image', uuid=choice.uuid))
            else:
                flash("No further ungraded glaucoma images found.", "info")
        elif action == 'save_close':
            return redirect(url_for('grading.index'))
        # Default
        return redirect(url_for('grading.glaucoma_image', uuid=ef.uuid))
    finally:
        db.close()


@roles_required("admin", "optometrist", "ophthalmologist")
def glaucoma_remove():
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

        user_id = getattr(current_user, 'id', None)
        gr = (
            db.query(ImageGrading)
              .filter(ImageGrading.id == grading_id,
                      ImageGrading.encounter_file_id == ef.id,
                      ImageGrading.grader_user_id == user_id,
                      ImageGrading.graded_for == 'glaucoma')
              .first()
        )
        if not gr:
            flash("No matching grading found to remove.", "info")
            return redirect(url_for('grading.glaucoma_image', uuid=ef.uuid))
        db.delete(gr)
        db.commit()
        flash("Removed this grading instance.", "success")
        return redirect(url_for('grading.glaucoma_image', uuid=ef.uuid))
    finally:
        db.close()