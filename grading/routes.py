from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.orm import joinedload, selectinload

from auth.roles import roles_required
from . import bp
from models import Session, PatientEncounters, EncounterFile, ImageGrading, utcnow


@bp.route("/", methods=["GET", "POST"])
@roles_required("admin", "optometrist", "ophthalmologist")
def index():
    if request.method == "POST":
        img_uuid = (request.form.get("image_uuid") or "").strip()
        if img_uuid:
            return redirect(url_for('grading.glaucoma_image', uuid=img_uuid))
        flash("Please enter a valid Image UUID", "warning")

    # Stats + most recent encounter with an ungraded glaucoma image
    db = Session()
    try:
        from sqlalchemy import distinct
        total_glaucoma = db.query(ImageGrading).filter(ImageGrading.graded_for == 'glaucoma').count()
        total_dr = db.query(ImageGrading).filter(ImageGrading.graded_for == 'dr').count()
        total_unique_images = db.query(distinct(ImageGrading.encounter_file_id)).count()

        # Find the most recent image (by encounter date desc, then ef.id desc) that has
        # no glaucoma grading by anyone yet.
        graded_gl_ef_ids = (
            db.query(ImageGrading.encounter_file_id)
              .filter(ImageGrading.graded_for == 'glaucoma')
              .subquery()
        )
        recent_img = (
            db.query(EncounterFile)
              .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
              .filter(PatientEncounters.capture_date_dt.isnot(None))
              .filter(EncounterFile.file_type == 'image')
              .filter(~EncounterFile.id.in_(graded_gl_ef_ids))
              .order_by(PatientEncounters.capture_date_dt.desc(), EncounterFile.id.desc())
              .first()
        )
        start_url = url_for('grading.glaucoma_image', uuid=recent_img.uuid) if recent_img and recent_img.uuid else None
    finally:
        db.close()

    return render_template(
        "grading/index.html",
        total_glaucoma=total_glaucoma,
        total_dr=total_dr,
        total_unique_images=total_unique_images,
        start_url=start_url,
    )

 


@bp.route("/glaucoma/image/<uuid>", methods=["GET"])
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
    finally:
        db.close()

    impressions = ["Normal", "Glaucoma Suspect", "Glaucoma", "Other Retinal", "Not gradable"]
    return render_template("grading/image_glaucoma.html", image=ef, encounter=enc, impressions=impressions)


@bp.route("/glaucoma/grade", methods=["POST"])
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
        # ef already loaded
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
        # Redirect back to image glaucoma grading page
        return redirect(url_for('grading.glaucoma_image', uuid=ef.uuid))
    finally:
        db.close()
