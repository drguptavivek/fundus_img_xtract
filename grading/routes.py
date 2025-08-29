from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import and_, distinct, func
import random

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
        total_glaucoma = db.query(ImageGrading).filter(ImageGrading.graded_for == 'glaucoma').count()
        total_dr = db.query(ImageGrading).filter(ImageGrading.graded_for == 'dr').count()
        total_unique_images = db.query(distinct(ImageGrading.encounter_file_id)).count()
        overall_total = db.query(ImageGrading).count()
        # Counts by impression (overall)
        type_rows = (
            db.query(ImageGrading.impression, func.count(ImageGrading.id))
              .group_by(ImageGrading.impression)
              .all()
        )
        type_counts = {k or 'Unknown': int(v) for k, v in type_rows}

        # Build candidate list: 50 most recent images not yet graded by this user for glaucoma
        grader_id = getattr(current_user, 'id', None)
        # Outer join to filter where no record exists for this user & 'glaucoma'
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
        start_url = url_for('grading.glaucoma_image', uuid=choice.uuid) if choice and choice.uuid else None

        # My gradings (paginated)
        page = request.args.get('p', default=1, type=int) or 1
        page = max(1, page)
        per_page = 20
        # Filter my gradings by impression type if provided
        gimp = (request.args.get('gimp') or 'all').strip()
        my_q = (
            db.query(ImageGrading)
              .options(joinedload(ImageGrading.image))
              .filter(ImageGrading.grader_user_id == getattr(current_user, 'id', None))
              .order_by(ImageGrading.updated_at.desc())
        )
        if gimp and gimp.lower() != 'all':
            my_q = my_q.filter(ImageGrading.impression == gimp)
        total_mine = my_q.count()
        items_mine = (
            my_q
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        total_pages_mine = max(1, (total_mine + per_page - 1) // per_page) if total_mine else 1
        mine_prev_url = url_for('grading.index', p=page-1, gimp=gimp) if page > 1 else None
        mine_next_url = url_for('grading.index', p=page+1, gimp=gimp) if page < total_pages_mine else None
    finally:
        db.close()

    return render_template(
        "grading/index.html",
        total_glaucoma=total_glaucoma,
        total_dr=total_dr,
        total_unique_images=total_unique_images,
        overall_total=overall_total,
        type_counts=type_counts,
        start_url=start_url,
        my_items=items_mine,
        my_total=total_mine,
        my_page=page,
        my_total_pages=total_pages_mine,
        my_prev_url=mine_prev_url,
        my_next_url=mine_next_url,
        gimp=gimp,
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

        # If user clicked Save & Next, pick a next image using the same logic
        # as the Start Glaucoma Grading button: random among 50 most recent
        # images not graded by this user for glaucoma.
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
        # Default: Redirect back to this image glaucoma grading page
        return redirect(url_for('grading.glaucoma_image', uuid=ef.uuid))
    finally:
        db.close()
