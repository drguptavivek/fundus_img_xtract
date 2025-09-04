from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, distinct, func
import random

from auth.roles import roles_required
from models import Session, PatientEncounters, EncounterFile, ImageGrading, DirectImageUpload, Disease, DirectImageVerify


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
                # First check if it's an EncounterFile UUID
                ef = db.query(EncounterFile).filter(EncounterFile.uuid == img_uuid).first()
                diu = None
                if not ef:
                    # If not found, check if it's a DirectImageUpload UUID
                    diu = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == img_uuid).first()
                
                if not ef and not diu:
                    flash("No image found for that UUID.", "danger")
                    return redirect(url_for('grading.index'))
                
                # Basic image check by type or extension for EncounterFile
                if ef:
                    ext = ef.filename.rsplit('.', 1)[-1].lower() if ef.filename and '.' in ef.filename else ''
                    if not ((ef.file_type or '').lower().startswith('image') or ext in {"png","jpg","jpeg","gif","bmp","webp"}):
                        flash("That UUID does not reference an image.", "danger")
                        return redirect(url_for('grading.index'))
                
                # For DirectImageUpload, we assume it's always an image
                
                # Message depending on whether the current user already graded it for the selected type
                my_id = getattr(current_user, 'id', None)
                has_my = False
                if ef:
                    has_my = (
                        db.query(ImageGrading)
                          .filter(ImageGrading.encounter_file_id == ef.id,
                                  ImageGrading.graded_for == code_for,
                                  ImageGrading.grader_user_id == my_id)
                          .count()
                    )
                elif diu:
                    has_my = (
                        db.query(ImageGrading)
                          .filter(ImageGrading.direct_image_upload_id == diu.id,
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

            # Redirect to appropriate endpoint based on image type
            if ef:
                if code_for == 'glaucoma':
                    return redirect(url_for('grading.remedio_glaucoma_image', uuid=img_uuid))
                elif code_for == 'dr':
                    return redirect(url_for('grading.remedio_dr_image', uuid=img_uuid))
            elif diu:
                # For direct images, we only support glaucoma grading
                if code_for in ['glaucoma', 'dr']:
                    return redirect(url_for('grading.direct_image', uuid=img_uuid))
                else:
                    flash("AMD grading is not available for direct images.", "warning")
                    return redirect(url_for('grading.index'))
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
        start_url = url_for('grading.remedio_glaucoma_image', uuid=choice.uuid) if choice and choice.uuid else None

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
        start_dr_url = url_for('grading.remedio_dr_image', uuid=choice_dr.uuid) if choice_dr and choice_dr.uuid else None

        # Build candidate list for direct image uploads not yet graded by this user for glaucoma
        # Get the Glaucoma disease ID
        glaucoma_disease = db.query(Disease).filter(Disease.name == 'Glaucoma').first()
        start_direct_url = None
        if glaucoma_disease:
            # Outer join to filter where no record exists for this user & 'glaucoma'
            cand_direct_q = (
                db.query(DirectImageUpload)
                .join(DirectImageVerify, DirectImageUpload.id == DirectImageVerify.image_upload_id)
                .outerjoin(
                    ImageGrading,
                    and_(
                        ImageGrading.direct_image_upload_id == DirectImageUpload.id,
                        ImageGrading.graded_for == 'glaucoma',
                        ImageGrading.grader_user_id == grader_id,
                    ),
                )
                .filter(DirectImageUpload.disease_id == glaucoma_disease.id)
                .filter(DirectImageVerify.verified_status == 'verified')
                .filter(ImageGrading.id.is_(None))
                .order_by(DirectImageUpload.created_at.desc())
                .limit(50)
            )
            candidates_direct = cand_direct_q.all()
            choice_direct = random.choice(candidates_direct) if candidates_direct else None
            start_direct_url = url_for('grading.direct_image', uuid=choice_direct.uuid) if choice_direct and choice_direct.uuid else None
        page = request.args.get('p', default=1, type=int) or 1
        page = max(1, page)
        per_page = 20
        # Filter my gradings by impression type and grading type if provided
        gimp = (request.args.get('gimp') or 'all').strip()
        gfor = (request.args.get('gfor') or 'all').strip().lower()
        my_q = (
            db.query(ImageGrading)
              .options(
                  joinedload(ImageGrading.image),
                  joinedload(ImageGrading.direct_image)
              )
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
        start_direct_url=start_direct_url,
        my_items=items_mine,
        my_total=total_mine,
        my_page=page,
        my_total_pages=total_pages_mine,
        my_prev_url=mine_prev_url,
        my_next_url=mine_next_url,
        gimp=gimp,
        gfor=gfor,
    )