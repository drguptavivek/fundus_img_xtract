from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy import and_
import random

from auth.roles import roles_required
from models import Session, DirectImageUpload, ImageGrading, Disease, DirectImageVerify

# grading/direct/<uuid>", view_func=direct_image, methods=["GET"])
@roles_required("admin", "ophthalmologist", "optometrist")
def direct_image(uuid: str):
    db = Session()
    try:
        # Fetch the direct image upload by UUID
        diu = (
            db.query(DirectImageUpload)
              .filter(DirectImageUpload.uuid == uuid)
              .first()
        )
        if not diu:
            from flask import abort
            abort(404)
            
        # Check access control - consultants can only grade images from their own LabUnit
        if not current_user.has_role('admin'):
            # Get user's lab units
            user_lab_unit_ids = [lu.id for lu in current_user.lab_units]
            # Check if image belongs to user's lab unit
            if diu.lab_unit_id not in user_lab_unit_ids:
                abort(403)  # Forbidden
                
        # Fetch the current user's most recent glaucoma grading for this image (to prefill form)
        my_grading = (
            db.query(ImageGrading)
              .filter(
                  ImageGrading.direct_image_upload_id == diu.id,
                  ImageGrading.graded_for == 'glaucoma',
                  ImageGrading.grader_user_id == getattr(current_user, 'id', None),
              )
              .order_by(ImageGrading.updated_at.desc(), ImageGrading.id.desc())
              .first()
        )
        
        # Determine user's role for grading (resident or consultant)
        user_role = None
        if current_user.has_role('ophthalmologist'):
            user_role = 'consultant'
        elif current_user.has_role('optometrist'):
            user_role = 'resident'
        elif current_user.has_role('admin'):
            user_role = 'admin'
            
        # Fetch existing gradings for this image to determine grading status
        existing_gradings = (
            db.query(ImageGrading)
              .filter(ImageGrading.direct_image_upload_id == diu.id,
                      ImageGrading.graded_for == 'glaucoma')
              .all()
        )
        
        # Determine grading status
        resident_grading = any(g.grader_role == 'resident' for g in existing_gradings)
        consultant_grading = any(g.grader_role == 'consultant' for g in existing_gradings)
        
        if resident_grading and consultant_grading:
            grading_status = "Both Graded"
        elif resident_grading:
            grading_status = "Resident Only"
        elif consultant_grading:
            grading_status = "Consultant Only"
        else:
            grading_status = "Not Graded"
    finally:
        db.close()

    impressions = ["Normal", "Glaucoma Suspect", "Glaucoma", "Other Retinal", "Not gradable"]
    return render_template("grading/direct_image_glaucoma.html", image=diu, impressions=impressions, 
                          my_grading=my_grading, user_role=user_role, grading_status=grading_status)

# bp.add_url_rule("/direct/glaucoma/grade", view_func=direct_glaucoma_grade, methods=["POST"])
@roles_required("admin", "ophthalmologist", "optometrist")
def direct_glaucoma_grade():
    uuid = (request.form.get("uuid") or "").strip()
    impression = (request.form.get("impression") or "").strip()
    remarks = (request.form.get("remarks") or "").strip() or None
    
    diu = None
    db = Session()
    try:
        # Fetch the direct image upload by UUID
        diu = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid).first()
        if not diu:
            flash("Invalid image.", "danger")
            return redirect(request.referrer or url_for("grading.index"))
            
        # Check access control - consultants can only grade images from their own LabUnit
        if not current_user.has_role('admin'):
            # Get user's lab units
            user_lab_unit_ids = [lu.id for lu in current_user.lab_units]
            # Check if image belongs to user's lab unit
            if diu.lab_unit_id not in user_lab_unit_ids:
                flash("Access denied.", "danger")
                return redirect(request.referrer or url_for("grading.index"))
    finally:
        db.close()

    # Determine user's role for grading (resident or consultant)
    role = None
    try:
        if current_user.has_role('ophthalmologist'):
            role = 'consultant'
        elif current_user.has_role('optometrist'):
            role = 'resident'
        elif current_user.has_role('admin'):
            role = 'admin'
    except Exception:
        role = 'unknown'

    if impression not in {"Normal", "Glaucoma Suspect", "Glaucoma", "Other Retinal", "Not gradable"}:
        flash("Please select a valid impression.", "warning")
        return redirect(request.referrer or url_for("grading.index"))

    db = Session()
    try:
        # Upsert by image + user + role
        user_id = getattr(current_user, 'id', None)
        username = getattr(current_user, 'username', None)
        existing = (
            db.query(ImageGrading)
              .filter(ImageGrading.direct_image_upload_id == diu.id,
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
                direct_image_upload_id=diu.id,
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
            # Build candidate list for direct image uploads not yet graded by this user for glaucoma
            grader_id = getattr(current_user, 'id', None)
            glaucoma_disease = db.query(Disease).filter(Disease.name == 'Glaucoma').first()
            if glaucoma_disease:
                # First, try to find images that haven't been graded by the current user's role
                if role in ['resident', 'consultant']:
                    # Get images that have been graded by the other role but not by the current user's role
                    other_role = 'consultant' if role == 'resident' else 'resident'
                    
                    # Subquery to find images graded by the other role
                    other_role_graded = (
                        db.query(ImageGrading.direct_image_upload_id)
                        .filter(ImageGrading.graded_for == 'glaucoma',
                                ImageGrading.grader_role == other_role)
                        .subquery()
                    )
                    
                    # Query to find images that have been graded by the other role but not by the current user's role
                    cand_direct_q = (
                        db.query(DirectImageUpload)
                        .join(DirectImageVerify, DirectImageUpload.id == DirectImageVerify.image_upload_id)
                        .join(other_role_graded, DirectImageUpload.id == other_role_graded.c.direct_image_upload_id)
                        .outerjoin(
                            ImageGrading,
                            and_(
                                ImageGrading.direct_image_upload_id == DirectImageUpload.id,
                                ImageGrading.graded_for == 'glaucoma',
                                ImageGrading.grader_user_id == grader_id,
                                ImageGrading.grader_role == role,
                            ),
                        )
                        .filter(DirectImageUpload.disease_id == glaucoma_disease.id)
                        .filter(DirectImageVerify.verified_status == 'verified')
                        .filter(ImageGrading.id.is_(None))
                        .order_by(DirectImageUpload.created_at.desc())
                        .limit(50)
                    )
                    candidates_direct = cand_direct_q.all()
                    
                    # If no candidates found, look for any ungraded images
                    if not candidates_direct:
                        cand_direct_q = (
                            db.query(DirectImageUpload)
                            .join(DirectImageVerify, DirectImageUpload.id == DirectImageVerify.image_upload_id)
                            .outerjoin(
                                ImageGrading,
                                and_(
                                    ImageGrading.direct_image_upload_id == DirectImageUpload.id,
                                    ImageGrading.graded_for == 'glaucoma',
                                ),
                            )
                            .filter(DirectImageUpload.disease_id == glaucoma_disease.id)
                            .filter(DirectImageVerify.verified_status == 'verified')
                            .filter(ImageGrading.id.is_(None))
                            .order_by(DirectImageUpload.created_at.desc())
                            .limit(50)
                        )
                        candidates_direct = cand_direct_q.all()
                else:
                    # For admin users, use the existing logic
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
                if choice_direct and choice_direct.uuid:
                    return redirect(url_for('grading.direct_image', uuid=choice_direct.uuid))
                else:
                    flash("No further ungraded direct images found.", "info")
            else:
                flash("No further ungraded direct images found.", "info")
        elif action == 'save_close':
            return redirect(url_for('grading.index'))
        # Default
        return redirect(url_for('grading.direct_image', uuid=uuid))
    finally:
        db.close()

# bp.add_url_rule("/direct/glaucoma/remove", view_func=direct_glaucoma_remove, methods=["POST"])
@roles_required("admin", "ophthalmologist")
def direct_glaucoma_remove():
    uuid = (request.form.get("uuid") or "").strip()
    grading_id_raw = request.form.get("grading_id")
    if not uuid or not grading_id_raw:
        flash("Invalid request.", "danger")
        return redirect(request.referrer or url_for("grading.index"))
    try:
        grading_id = int(grading_id_raw)
    except Exception:
        flash("Invalid grading id.", "danger")
        return redirect(request.referrer or url_for("grading.index"))

    db = Session()
    try:
        diu = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid).first()
        if not diu:
            flash("Image not found.", "danger")
            return redirect(url_for('grading.index'))

        # Check access control - consultants can only grade images from their own LabUnit
        if not current_user.has_role('admin'):
            # Get user's lab units
            user_lab_unit_ids = [lu.id for lu in current_user.lab_units]
            # Check if image belongs to user's lab unit
            if diu.lab_unit_id not in user_lab_unit_ids:
                flash("Access denied.", "danger")
                return redirect(request.referrer or url_for("grading.index"))

        user_id = getattr(current_user, 'id', None)
        gr = (
            db.query(ImageGrading)
              .filter(ImageGrading.id == grading_id,
                      ImageGrading.direct_image_upload_id == diu.id,
                      ImageGrading.grader_user_id == user_id,
                      ImageGrading.graded_for == 'glaucoma')
              .first()
        )
        if not gr:
            flash("No matching grading found to remove.", "info")
            return redirect(url_for('grading.direct_image', uuid=uuid))
        db.delete(gr)
        db.commit()
        flash("Removed this grading instance.", "success")
        return redirect(url_for('grading.direct_image', uuid=uuid))
    finally:
        db.close()