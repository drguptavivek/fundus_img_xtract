from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, distinct, func, or_, desc, case
from sqlalchemy.sql import text

from auth.roles import roles_required
from models import Session, PatientEncounters, EncounterFile, ImageGrading, DirectImageUpload, Disease, DiseaseGrading


@roles_required("admin", "ophthalmologist")
def arbitration_dashboard():
    """Display the arbitration dashboard with images that have discrepancies."""
    db = Session()
    try:
        # Get encounter files with discrepancies (both resident and consultant graded but with different impressions)
        encounter_discrepancies = (
            db.query(EncounterFile)
            .join(ImageGrading, EncounterFile.id == ImageGrading.encounter_file_id)
            .filter(EncounterFile.is_locked == True, EncounterFile.is_arbitration == False)
            .group_by(EncounterFile.id)
            .having(
                and_(
                    # Has both resident and consultant gradings
                    func.count(case((ImageGrading.grader_role == 'resident', 1))) > 0,
                    func.count(case((ImageGrading.grader_role == 'consultant', 1))) > 0,
                    # But the impressions are different
                    func.count(distinct(ImageGrading.impression)) > 1
                )
            )
            .all()
        )
        
        # Get direct uploads with discrepancies
        direct_discrepancies = (
            db.query(DirectImageUpload)
            .join(ImageGrading, DirectImageUpload.id == ImageGrading.direct_image_upload_id)
            .filter(DirectImageUpload.is_locked == True, DirectImageUpload.is_arbitration == False)
            .group_by(DirectImageUpload.id)
            .having(
                and_(
                    # Has both resident and consultant gradings
                    func.count(case((ImageGrading.grader_role == 'resident', 1))) > 0,
                    func.count(case((ImageGrading.grader_role == 'consultant', 1))) > 0,
                    # But the impressions are different
                    func.count(distinct(ImageGrading.impression)) > 1
                )
            )
            .all()
        )
        
        # Combine and limit to 50 for display
        all_discrepancies = list(encounter_discrepancies) + list(direct_discrepancies)
        
    finally:
        db.close()
    
    return render_template(
        "grading/arbitration_dashboard.html", 
        discrepancies=all_discrepancies
    )


@roles_required("admin", "ophthalmologist")
def arbitration_image(uuid: str):
    """Display an image for arbitration."""
    db = Session()
    try:
        # Try to find as encounter file first
        ef = db.query(EncounterFile).filter(EncounterFile.uuid == uuid).first()
        if ef:
            # Check if it's locked and not yet arbitrated
            if not ef.is_locked or ef.is_arbitration:
                flash("This image is not available for arbitration.", "danger")
                return redirect(url_for('grading.index'))
            
            # Get existing gradings
            existing_gradings = (
                db.query(ImageGrading)
                .filter(ImageGrading.encounter_file_id == ef.id)
                .all()
            )
            
            # Separate resident and consultant gradings
            resident_grading = None
            consultant_grading = None
            for grading in existing_gradings:
                if grading.grader_role == 'resident':
                    resident_grading = grading
                elif grading.grader_role == 'consultant':
                    consultant_grading = grading
            
            # Get arbitration grading if exists
            arbitration_grading = None
            for grading in existing_gradings:
                if grading.is_arbitration:
                    arbitration_grading = grading
                    break
            
            # Get disease for display
            disease = "glaucoma"  # Default for remed.io images
            
            return render_template(
                "grading/arbitration_image.html",
                image=ef,
                image_type="encounter",
                resident_grading=resident_grading,
                consultant_grading=consultant_grading,
                arbitration_grading=arbitration_grading,
                disease=disease
            )
        
        # If not found as encounter file, try direct upload
        diu = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid).first()
        if diu:
            # Check if it's locked and not yet arbitrated
            if not diu.is_locked or diu.is_arbitration:
                flash("This image is not available for arbitration.", "danger")
                return redirect(url_for('grading.index'))
            
            # Get existing gradings
            existing_gradings = (
                db.query(ImageGrading)
                .filter(ImageGrading.direct_image_upload_id == diu.id)
                .all()
            )
            
            # Separate resident and consultant gradings
            resident_grading = None
            consultant_grading = None
            for grading in existing_gradings:
                if grading.grader_role == 'resident':
                    resident_grading = grading
                elif grading.grader_role == 'consultant':
                    consultant_grading = grading
            
            # Get arbitration grading if exists
            arbitration_grading = None
            for grading in existing_gradings:
                if grading.is_arbitration:
                    arbitration_grading = grading
                    break
            
            # Get disease
            disease = db.query(Disease).filter(Disease.id == diu.disease_id).first()
            
            return render_template(
                "grading/arbitration_image.html",
                image=diu,
                image_type="direct",
                resident_grading=resident_grading,
                consultant_grading=consultant_grading,
                arbitration_grading=arbitration_grading,
                disease=disease
            )
        
        # If neither found
        flash("Image not found.", "danger")
        return redirect(url_for('grading.index'))
    finally:
        db.close()


@roles_required("admin", "ophthalmologist")
def arbitration_grade():
    """Save an arbitration grading."""
    uuid = (request.form.get("uuid") or "").strip()
    image_type = (request.form.get("image_type") or "").strip()
    disease_id_raw = request.form.get("disease_id")
    impression = (request.form.get("impression") or "").strip()
    remarks = (request.form.get("remarks") or "").strip() or None
    
    db = Session()
    try:
        # Validate inputs
        if not uuid or not image_type:
            flash("Invalid request.", "danger")
            return redirect(url_for('grading.index'))
        
        if image_type == "encounter":
            # Get encounter file
            ef = db.query(EncounterFile).filter(EncounterFile.uuid == uuid).first()
            if not ef:
                flash("Image not found.", "danger")
                return redirect(url_for('grading.index'))
            
            # Check if it's locked and not yet arbitrated
            if not ef.is_locked or ef.is_arbitration:
                flash("This image is not available for arbitration.", "danger")
                return redirect(url_for('grading.index'))
            
            # For remed.io images, disease is glaucoma
            disease_name = "glaucoma"
            
            # Validate impression
            if impression not in {"Normal", "Glaucoma Suspect", "Glaucoma", "Other Retinal", "Not gradable"}:
                flash("Please select a valid impression.", "warning")
                return redirect(url_for('grading.arbitration_image', uuid=uuid))
                
        elif image_type == "direct":
            # Get direct image upload
            diu = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid).first()
            if not diu:
                flash("Image not found.", "danger")
                return redirect(url_for('grading.index'))
            
            # Check if it's locked and not yet arbitrated
            if not diu.is_locked or diu.is_arbitration:
                flash("This image is not available for arbitration.", "danger")
                return redirect(url_for('grading.index'))
            
            # Get disease
            try:
                disease_id = int(disease_id_raw)
                disease = db.query(Disease).filter(Disease.id == disease_id).first()
                if not disease:
                    flash("Invalid disease.", "danger")
                    return redirect(url_for('grading.index'))
                disease_name = disease.name.lower()
            except Exception:
                flash("Invalid disease.", "danger")
                return redirect(url_for('grading.index'))
            
            # Validate impression for direct images
            # For direct images, we need to validate against disease gradings
            valid_impression = db.query(DiseaseGrading).filter(
                DiseaseGrading.disease_id == disease_id,
                DiseaseGrading.impression == impression,
                DiseaseGrading.is_active == True
            ).first()
            
            if not valid_impression:
                flash("Please select a valid impression.", "warning")
                return redirect(url_for('grading.arbitration_image', uuid=uuid))
        else:
            flash("Invalid image type.", "danger")
            return redirect(url_for('grading.index'))
        
        # Save arbitration grading
        user_id = getattr(current_user, 'id', None)
        username = getattr(current_user, 'username', None)
        
        if image_type == "encounter":
            db.add(ImageGrading(
                encounter_file_id=ef.id,
                grader_user_id=user_id,
                grader_username=username,
                grader_role='consultant',  # Arbitration is done by consultant
                graded_for=disease_name,
                impression=impression,
                remarks=remarks,
                is_arbitration=True  # Mark as arbitration grading
            ))
            
            # Mark the encounter file as arbitrated
            ef.is_arbitration = True
            ef.arbitrated_by = user_id
            db.add(ef)
        else:  # direct
            db.add(ImageGrading(
                direct_image_upload_id=diu.id,
                grader_user_id=user_id,
                grader_username=username,
                grader_role='consultant',  # Arbitration is done by consultant
                graded_for=disease_name,
                impression=impression,
                remarks=remarks,
                is_arbitration=True  # Mark as arbitration grading
            ))
            
            # Mark the direct image upload as arbitrated
            diu.is_arbitration = True
            diu.arbitrated_by = user_id
            db.add(diu)
        
        db.commit()
        flash("Arbitration grading saved.", "success")
        
        # Redirect based on action
        action = (request.form.get('action') or '').strip().lower()
        if action == 'save_next':
            # Try to find another image for arbitration
            next_image = _get_next_arbitration_image(db, user_id)
            if next_image:
                if hasattr(next_image, 'encounter_file_id'):  # It's an EncounterFile
                    return redirect(url_for('grading.arbitration_image', uuid=next_image.uuid))
                else:  # It's a DirectImageUpload
                    return redirect(url_for('grading.arbitration_image', uuid=next_image.uuid))
            else:
                flash("No further images requiring arbitration found.", "info")
                return redirect(url_for('grading.index'))
        elif action == 'save_close':
            return redirect(url_for('grading.index'))
        
        # Default redirect
        return redirect(url_for('grading.arbitration_image', uuid=uuid))
    finally:
        db.close()


def _get_next_arbitration_image(db, user_id):
    """Get the next image that needs arbitration."""
    # Try encounter files first
    ef = (
        db.query(EncounterFile)
        .filter(EncounterFile.is_locked == True, EncounterFile.is_arbitration == False)
        .order_by(EncounterFile.id.desc())
        .first()
    )
    
    if ef:
        return ef
    
    # If no encounter files, try direct uploads
    diu = (
        db.query(DirectImageUpload)
        .filter(DirectImageUpload.is_locked == True, DirectImageUpload.is_arbitration == False)
        .order_by(DirectImageUpload.id.desc())
        .first()
    )
    
    return diu