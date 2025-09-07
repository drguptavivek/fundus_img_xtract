"""
Matching service for dual grading system.
This service runs periodically to match resident and consultant gradings for the same images.
"""

from datetime import datetime, timedelta
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session as DBSession

from models import Session, EncounterFile, DirectImageUpload, ImageGrading, DiseaseGrading


def run_matching():
    """
    Run the matching process to identify pairs of resident/consultant gradings.
    This function should be called periodically (e.g., every 2 hours).
    """
    db = Session()
    try:
        # Match encounter files (Remedio ZIP images)
        _match_encounter_files(db)
        
        # Match direct image uploads
        _match_direct_uploads(db)
        
        db.commit()
        print("Matching process completed successfully.")
    except Exception as e:
        db.rollback()
        print(f"Error during matching process: {e}")
        raise
    finally:
        db.close()


def _match_encounter_files(db):
    """
    Match resident and consultant gradings for encounter files.
    """
    # Get encounter files that have both resident and consultant gradings but haven't been matched yet
    unmatched_encounters = (
        db.query(EncounterFile)
        .filter(EncounterFile.is_locked == False)  # Only process unlocked files
        .filter(
            and_(
                # Has resident grading
                db.query(ImageGrading.id).filter(
                    ImageGrading.encounter_file_id == EncounterFile.id,
                    ImageGrading.grader_role == 'resident'
                ).exists(),
                # Has consultant grading
                db.query(ImageGrading.id).filter(
                    ImageGrading.encounter_file_id == EncounterFile.id,
                    ImageGrading.grader_role == 'consultant'
                ).exists()
            )
        )
        .all()
    )
    
    for encounter in unmatched_encounters:
        # Lock the encounter file
        encounter.is_locked = True
        encounter.matched_at = datetime.utcnow()
        db.add(encounter)
        
        print(f"Matched and locked encounter file {encounter.uuid}")


def _match_direct_uploads(db):
    """
    Match resident and consultant gradings for direct image uploads.
    """
    # Get direct uploads that have both resident and consultant gradings but haven't been matched yet
    unmatched_directs = (
        db.query(DirectImageUpload)
        .filter(DirectImageUpload.is_locked == False)  # Only process unlocked files
        .filter(
            and_(
                # Has resident grading
                db.query(ImageGrading.id).filter(
                    ImageGrading.direct_image_upload_id == DirectImageUpload.id,
                    ImageGrading.grader_role == 'resident'
                ).exists(),
                # Has consultant grading
                db.query(ImageGrading.id).filter(
                    ImageGrading.direct_image_upload_id == DirectImageUpload.id,
                    ImageGrading.grader_role == 'consultant'
                ).exists()
            )
        )
        .all()
    )
    
    for direct_upload in unmatched_directs:
        # Lock the direct upload
        direct_upload.is_locked = True
        direct_upload.matched_at = datetime.utcnow()
        db.add(direct_upload)
        
        print(f"Matched and locked direct upload {direct_upload.uuid}")


def get_matching_stats(db=None):
    """
    Get statistics about the matching process.
    """
    close_db = False
    if db is None:
        db = Session()
        close_db = True
        
    try:
        # Total images
        total_encounters = db.query(EncounterFile).count()
        total_directs = db.query(DirectImageUpload).count()
        
        # Locked images (matched)
        locked_encounters = db.query(EncounterFile).filter(EncounterFile.is_locked == True).count()
        locked_directs = db.query(DirectImageUpload).filter(DirectImageUpload.is_locked == True).count()
        
        # Arbitrated images
        arbitrated_encounters = db.query(EncounterFile).filter(EncounterFile.is_arbitration == True).count()
        arbitrated_directs = db.query(DirectImageUpload).filter(DirectImageUpload.is_arbitration == True).count()
        
        # Images with both gradings
        encounters_with_both = (
            db.query(EncounterFile)
            .filter(
                and_(
                    db.query(ImageGrading.id).filter(
                        ImageGrading.encounter_file_id == EncounterFile.id,
                        ImageGrading.grader_role == 'resident'
                    ).exists(),
                    db.query(ImageGrading.id).filter(
                        ImageGrading.encounter_file_id == EncounterFile.id,
                        ImageGrading.grader_role == 'consultant'
                    ).exists()
                )
            )
            .count()
        )
        
        direct_with_both = (
            db.query(DirectImageUpload)
            .filter(
                and_(
                    db.query(ImageGrading.id).filter(
                        ImageGrading.direct_image_upload_id == DirectImageUpload.id,
                        ImageGrading.grader_role == 'resident'
                    ).exists(),
                    db.query(ImageGrading.id).filter(
                        ImageGrading.direct_image_upload_id == DirectImageUpload.id,
                        ImageGrading.grader_role == 'consultant'
                    ).exists()
                )
            )
            .count()
        )
        
        return {
            'total_encounters': total_encounters,
            'total_directs': total_directs,
            'locked_encounters': locked_encounters,
            'locked_directs': locked_directs,
            'arbitrated_encounters': arbitrated_encounters,
            'arbitrated_directs': arbitrated_directs,
            'encounters_with_both': encounters_with_both,
            'direct_with_both': direct_with_both
        }
    finally:
        if close_db:
            db.close()


# Flask-specific functions
try:
    from flask import render_template, request, redirect, url_for, flash
    from flask_login import current_user
    from auth.roles import roles_required
    
    @roles_required("admin", "ophthalmologist", "data_manager")
    def matching_dashboard():
        """Display the matching dashboard with statistics and manual trigger."""
        # Get current matching statistics
        stats = get_matching_stats()
        
        return render_template(
            "dual_grading/matching.html",
            stats=stats
        )

    @roles_required("admin", "ophthalmologist", "data_manager")
    def run_matching_process():
        """Manually trigger the matching process."""
        try:
            run_matching()
            flash("Matching process completed successfully.", "success")
        except Exception as e:
            flash(f"Error running matching process: {e}", "danger")
        
        return redirect(url_for('dual_grading.matching_dashboard'))
        
except ImportError:
    # If Flask is not available, don't define the Flask-specific functions
    pass


if __name__ == "__main__":
    # Run matching process when script is executed directly
    run_matching()