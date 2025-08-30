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
        code_for = (request.form.get("code_for") or request.form.get("gfor") or "glaucoma").strip().lower()
        if code_for not in {"glaucoma","dr","amd"}:
            code_for = "glaucoma"
        if img_uuid:
            # Validate UUID points to an image we can grade; add clear messaging for scenarios
            db = Session()
            try:
                ef = db.query(EncounterFile).filter(EncounterFile.uuid == img_uuid).first()
                if not ef:
                    flash("No image found for that UUID.", "danger")
                    return redirect(url_for('grading.index'))
                # Basic image check by type or extension
                ext = ef.filename.rsplit('.', 1)[-1].lower() if ef.filename and '.' in ef.filename else ''
                if not ((ef.file_type or '').lower().startswith('image') or ext in {"png","jpg","jpeg","gif","bmp","webp"}):
                    flash("That UUID does not reference an image.", "danger")
                    return redirect(url_for('grading.index'))

                # Message depending on whether the current user already graded it for the selected type
                my_id = getattr(current_user, 'id', None)
                has_my = (
                    db.query(ImageGrading)
                      .filter(ImageGrading.encounter_file_id == ef.id,
                              ImageGrading.graded_for == code_for,
                              ImageGrading.grader_user_id == my_id)
                      .count()
                )
                if code_for == 'amd':
                    flash("AMD grading is not available yet.", "warning")
                    return redirect(url_for('grading.index'))
                if has_my:
                    flash(f"Opening your previous {code_for.upper()} grading to revise.", "info")
                else:
                    flash(f"Opening image — no {code_for.upper()} grading by you yet.", "success")
            finally:
                db.close()

            if code_for == 'glaucoma':
                return redirect(url_for('grading.glaucoma_image', uuid=img_uuid))
            elif code_for == 'dr':
                return redirect(url_for('grading.dr_image', uuid=img_uuid))
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

        # Build candidate list for DR ungraded by this user (50 recent)
        cand_dr_q = (
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
              .order_by(PatientEncounters.capture_date_dt.desc(), EncounterFile.id.desc())
              .limit(50)
        )
        candidates_dr = cand_dr_q.all()
        choice_dr = random.choice(candidates_dr) if candidates_dr else None
        start_dr_url = url_for('grading.dr_image', uuid=choice_dr.uuid) if choice_dr and choice_dr.uuid else None

        # My gradings (paginated)
        page = request.args.get('p', default=1, type=int) or 1
        page = max(1, page)
        per_page = 20
        # Filter my gradings by impression type and grading type if provided
        gimp = (request.args.get('gimp') or 'all').strip()
        gfor = (request.args.get('gfor') or 'all').strip().lower()
        my_q = (
            db.query(ImageGrading)
              .options(joinedload(ImageGrading.image))
              .filter(ImageGrading.grader_user_id == getattr(current_user, 'id', None))
              .order_by(ImageGrading.updated_at.desc())
        )
        if gimp and gimp.lower() != 'all':
            my_q = my_q.filter(ImageGrading.impression == gimp)
        if gfor and gfor != 'all':
            my_q = my_q.filter(ImageGrading.graded_for == gfor)
        total_mine = my_q.count()
        items_mine = (
            my_q
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        total_pages_mine = max(1, (total_mine + per_page - 1) // per_page) if total_mine else 1
        mine_prev_url = url_for('grading.index', p=page-1, gimp=gimp, gfor=gfor) if page > 1 else None
        mine_next_url = url_for('grading.index', p=page+1, gimp=gimp, gfor=gfor) if page < total_pages_mine else None
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
        start_dr_url=start_dr_url,
        my_items=items_mine,
        my_total=total_mine,
        my_page=page,
        my_total_pages=total_pages_mine,
        my_prev_url=mine_prev_url,
        my_next_url=mine_next_url,
        gimp=gimp,
        gfor=gfor,
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


# ---- DR grading routes (similar to glaucoma) ----

@bp.route("/dr/image/<uuid>", methods=["GET"])
@roles_required("admin", "optometrist", "ophthalmologist")
def dr_image(uuid: str):
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
    return render_template("grading/image_dr.html", image=ef, encounter=enc, impressions=dr_impressions, my_grading=my_grading)


@bp.route("/dr/grade", methods=["POST"])
@roles_required("admin", "optometrist", "ophthalmologist")
def dr_grade():
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
                  .order_by(PatientEncounters.capture_date_dt.desc(), EncounterFile.id.desc())
                  .limit(50)
            )
            candidates = cand_q.all()
            choice = random.choice(candidates) if candidates else None
            if choice and choice.uuid:
                return redirect(url_for('grading.dr_image', uuid=choice.uuid))
            else:
                flash("No further ungraded DR images found.", "info")
        elif action == 'save_close':
            return redirect(url_for('grading.index'))
        return redirect(url_for('grading.dr_image', uuid=ef.uuid))
    finally:
        db.close()


@bp.route("/dr/remove", methods=["POST"])
@roles_required("admin", "optometrist", "ophthalmologist")
def dr_remove():
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
                      ImageGrading.graded_for == 'dr')
              .first()
        )
        if not gr:
            flash("No matching DR grading found to remove.", "info")
            return redirect(url_for('grading.dr_image', uuid=ef.uuid))
        db.delete(gr)
        db.commit()
        flash("Removed this DR grading instance.", "success")
        return redirect(url_for('grading.dr_image', uuid=ef.uuid))
    finally:
        db.close()



@bp.route("/glaucoma/remove", methods=["POST"])
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
