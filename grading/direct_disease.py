from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy import and_
import random

from auth.roles import roles_required
from models import Session, DirectImageUpload, ImageGrading, Disease, DiseaseGrading, DirectImageVerify


@roles_required("admin", "ophthalmologist", "resident")
def direct_disease_image(uuid: str, disease_id: int):
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
                
        # Fetch the disease
        disease = db.query(Disease).filter(Disease.id == disease_id).first()
        if not disease:
            abort(404)
                
        # Fetch the current user's most recent grading for this image and disease
        my_grading = (
            db.query(ImageGrading)
              .filter(
                  ImageGrading.direct_image_upload_id == diu.id,
                  ImageGrading.graded_for == disease.name.lower(),
                  ImageGrading.grader_user_id == getattr(current_user, 'id', None),
              )
              .order_by(ImageGrading.updated_at.desc(), ImageGrading.id.desc())
              .first()
        )
        
        # Fetch disease gradings for this disease
        disease_gradings = (
            db.query(DiseaseGrading)
              .filter(DiseaseGrading.disease_id == disease_id, DiseaseGrading.is_active == True)
              .order_by(DiseaseGrading.display_order)
              .all()
        )
    finally:
        db.close()

    return render_template(
        "grading/direct_image_disease.html", 
        image=diu, 
        disease=disease,
        disease_gradings=disease_gradings, 
        my_grading=my_grading
    )


@roles_required("admin", "ophthalmologist", "resident")
def direct_disease_grade():
    uuid = (request.form.get("uuid") or "").strip()
    disease_id_raw = request.form.get("disease_id")
    grading_id_raw = request.form.get("grading_id")
    impression = (request.form.get("impression") or "").strip()
    remarks = (request.form.get("remarks") or "").strip() or None
    
    diu = None
    disease = None
    db = Session()
    try:
        # Fetch the direct image upload by UUID
        diu = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid).first()
        if not diu:
            flash("Invalid image.", "danger")
            return redirect(request.referrer or url_for("grading.index"))
            
        # Fetch the disease
        try:
            disease_id = int(disease_id_raw)
            disease = db.query(Disease).filter(Disease.id == disease_id).first()
        except Exception:
            disease = None
            
        if not disease:
            flash("Invalid disease.", "danger")
            return redirect(request.referrer or url_for("grading.index"))
            
        # Check access control - consultants can only grade images from their own LabUnit
        if not current_user.has_role('admin'):
            # Get user's lab units
            user_lab_unit_ids = [lu.id for lu in current_user.lab_units]
            # Check if image belongs to user's lab unit
            if diu.lab_unit_id not in user_lab_unit_ids:
                flash("Access denied.", "danger")
                return redirect(request.referrer or url_for("grading.index"))
        
        # Check if image is locked
        if diu.is_locked:
            flash("This image has been locked for editing after matching. No further changes allowed.", "danger")
            return redirect(request.referrer or url_for("grading.index"))
    finally:
        db.close()

    role = None
    try:
        if current_user.has_role('ophthalmologist'):
            role = 'ophthalmologist'
        elif current_user.has_role('resident'):
            role = 'resident'
        elif current_user.has_role('admin'):
            # If admin also has ophthalmologist role, record as ophthalmologist
            if current_user.has_role('ophthalmologist'):
                role = 'ophthalmologist'
            else:
                role = 'admin'
    except Exception:
        role = 'unknown'

    # Validate impression is one of the valid disease gradings
    db = Session()
    try:
        valid_impression = db.query(DiseaseGrading).filter(
            DiseaseGrading.disease_id == disease_id,
            DiseaseGrading.impression == impression,
            DiseaseGrading.is_active == True
        ).first()
        
        if not valid_impression:
            flash("Please select a valid impression.", "warning")
            return redirect(request.referrer or url_for("grading.index"))
    finally:
        db.close()

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
                      ImageGrading.graded_for == disease.name.lower())
              .first()
        )
        
        # Check if existing grading is locked
        if existing and diu.is_locked:
            flash("This image has been locked for editing after matching. No further changes allowed.", "danger")
            return redirect(url_for('grading.direct_disease_image', uuid=uuid, disease_id=disease_id))
        
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
                graded_for=disease.name.lower(),
                impression=impression,
                remarks=remarks,
            ))
        db.commit()
        flash(f"{disease.name} grading saved.", "success")
        
        # Save & Next flow
        action = (request.form.get('action') or '').strip().lower()
        if action == 'save_next':
            # Build candidate list for direct image uploads not yet graded by this user for this disease
            grader_id = getattr(current_user, 'id', None)
            # Outer join to filter where no record exists for this user & disease
            cand_direct_q = (
                db.query(DirectImageUpload)
                .join(DirectImageVerify, DirectImageUpload.id == DirectImageVerify.image_upload_id)
                .outerjoin(
                    ImageGrading,
                    and_(
                        ImageGrading.direct_image_upload_id == DirectImageUpload.id,
                        ImageGrading.graded_for == disease.name.lower(),
                        ImageGrading.grader_user_id == grader_id,
                    ),
                )
                .filter(DirectImageUpload.disease_id == disease_id)
                .filter(DirectImageVerify.verified_status == 'verified')
                .filter(ImageGrading.id.is_(None))
                .filter(DirectImageUpload.is_locked == False)  # Only unlocked images
                .order_by(DirectImageUpload.created_at.desc())
                .limit(50)
            )
            candidates_direct = cand_direct_q.all()
            choice_direct = random.choice(candidates_direct) if candidates_direct else None
            if choice_direct and choice_direct.uuid:
                return redirect(url_for('grading.direct_disease_image', uuid=choice_direct.uuid, disease_id=disease_id))
            else:
                flash(f"No further ungraded direct images found for {disease.name}.", "info")
        elif action == 'save_close':
            return redirect(url_for('grading.index'))
        # Default
        return redirect(url_for('grading.direct_disease_image', uuid=uuid, disease_id=disease_id))
    finally:
        db.close()


@roles_required("admin", "ophthalmologist", "resident")
def direct_disease_remove():
    uuid = (request.form.get("uuid") or "").strip()
    disease_id_raw = request.form.get("disease_id")
    grading_id_raw = request.form.get("grading_id")
    if not uuid or not disease_id_raw or not grading_id_raw:
        flash("Invalid request.", "danger")
        return redirect(request.referrer or url_for("grading.index"))
    try:
        disease_id = int(disease_id_raw)
        grading_id = int(grading_id_raw)
    except Exception:
        flash("Invalid disease id or grading id.", "danger")
        return redirect(request.referrer or url_for("grading.index"))

    db = Session()
    try:
        diu = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid).first()
        if not diu:
            flash("Image not found.", "danger")
            return redirect(url_for('grading.index'))

        # Fetch the disease
        disease = db.query(Disease).filter(Disease.id == disease_id).first()
        if not disease:
            flash("Disease not found.", "danger")
            return redirect(url_for('grading.index'))

        # Check access control - consultants can only grade images from their own LabUnit
        if not current_user.has_role('admin'):
            # Get user's lab units
            user_lab_unit_ids = [lu.id for lu in current_user.lab_units]
            # Check if image belongs to user's lab unit
            if diu.lab_unit_id not in user_lab_unit_ids:
                flash("Access denied.", "danger")
                return redirect(request.referrer or url_for("grading.index"))
        
        # Check if image is locked
        if diu.is_locked:
            flash("This image has been locked for editing after matching. No further changes allowed.", "danger")
            return redirect(url_for('grading.direct_disease_image', uuid=uuid, disease_id=disease_id))

        user_id = getattr(current_user, 'id', None)
        gr = (
            db.query(ImageGrading)
              .filter(ImageGrading.id == grading_id,
                      ImageGrading.direct_image_upload_id == diu.id,
                      ImageGrading.grader_user_id == user_id,
                      ImageGrading.graded_for == disease.name.lower())
              .first()
        )
        if not gr:
            flash("No matching grading found to remove.", "info")
            return redirect(url_for('grading.direct_disease_image', uuid=uuid, disease_id=disease_id))
        db.delete(gr)
        db.commit()
        flash(f"Removed this {disease.name} grading instance.", "success")
        return redirect(url_for('grading.direct_disease_image', uuid=uuid, disease_id=disease_id))
    finally:
        db.close()