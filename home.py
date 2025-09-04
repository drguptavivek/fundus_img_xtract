from flask import render_template
from sqlalchemy import select, func, or_, distinct, case, and_
from models import (
    Session, EncounterFile, PatientEncounters, ImageGrading, 
    GlaucomaReport, GlaucomaResultsCleaned, DiabeticRetinopathyReport,
    DirectImageUpload, DirectImageVerify
)

def homepage():
    # Compute counts for the public home (unauthenticated visitors)
    img_exts = [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"]  # same set the app serves
    
    with Session() as db:
        # Basic counts
        img_filters = [func.lower(EncounterFile.filename).like(f"%{ext}") for ext in img_exts]
        images_count = db.execute(
            select(func.count(EncounterFile.id)).where(or_(*img_filters))
        ).scalar_one()
        screenings_count = db.execute(
            select(func.count(PatientEncounters.id))
        ).scalar_one()
        
        # Direct image counts
        direct_images_count = db.execute(
            select(func.count(DirectImageUpload.id))
        ).scalar_one()
        
        # Verification counts
        verified_direct_images_count = db.execute(
            select(func.count(DirectImageVerify.id)).where(DirectImageVerify.verified_status == "verified")
        ).scalar_one()
        
        # Grading counts
        total_gradings_count = db.execute(
            select(func.count(ImageGrading.id))
        ).scalar_one()
        
        glaucoma_gradings_count = db.execute(
            select(func.count(ImageGrading.id)).where(ImageGrading.graded_for == "glaucoma")
        ).scalar_one()
        
        dr_gradings_count = db.execute(
            select(func.count(ImageGrading.id)).where(ImageGrading.graded_for == "dr")
        ).scalar_one()
        
        # VCDR data counts
        vcdr_data_count = db.execute(
            select(func.count(GlaucomaResultsCleaned.id)).where(
                or_(
                    GlaucomaResultsCleaned.vcdr_right_num.isnot(None),
                    GlaucomaResultsCleaned.vcdr_left_num.isnot(None)
                )
            )
        ).scalar_one()
        
        # Disease distribution for chart
        # Removed as requested
        
        # Grading distribution for chart
        grading_distribution = db.execute(
            select(ImageGrading.graded_for, func.count(ImageGrading.id))
            .group_by(ImageGrading.graded_for)
        ).all()
        
        # VCDR value ranges for chart
        vcdr_ranges = db.execute(
            select(
                func.sum(case((GlaucomaResultsCleaned.vcdr_right_num < 0.5, 1), else_=0)).label('normal_right'),
                func.sum(case((and_(GlaucomaResultsCleaned.vcdr_right_num >= 0.5, GlaucomaResultsCleaned.vcdr_right_num < 0.7), 1), else_=0)).label('borderline_right'),
                func.sum(case((GlaucomaResultsCleaned.vcdr_right_num >= 0.7, 1), else_=0)).label('abnormal_right'),
                func.sum(case((GlaucomaResultsCleaned.vcdr_left_num < 0.5, 1), else_=0)).label('normal_left'),
                func.sum(case((and_(GlaucomaResultsCleaned.vcdr_left_num >= 0.5, GlaucomaResultsCleaned.vcdr_left_num < 0.7), 1), else_=0)).label('borderline_left'),
                func.sum(case((GlaucomaResultsCleaned.vcdr_left_num >= 0.7, 1), else_=0)).label('abnormal_left')
            )
            .where(
                or_(
                    GlaucomaResultsCleaned.vcdr_right_num.isnot(None),
                    GlaucomaResultsCleaned.vcdr_left_num.isnot(None)
                )
            )
        ).first()
        
        # DR grading distribution
        dr_impression_distribution = db.execute(
            select(ImageGrading.impression, func.count(ImageGrading.id))
            .where(ImageGrading.graded_for == "dr")
            .group_by(ImageGrading.impression)
            .order_by(func.count(ImageGrading.id).desc())
        ).all()
        
        # Glaucoma grading distribution
        glaucoma_impression_distribution = db.execute(
            select(ImageGrading.impression, func.count(ImageGrading.id))
            .where(ImageGrading.graded_for == "glaucoma")
            .group_by(ImageGrading.impression)
            .order_by(func.count(ImageGrading.id).desc())
        ).all()

    return render_template(
        "home.html",
        images_count=images_count,
        screenings_count=screenings_count,
        direct_images_count=direct_images_count,
        verified_direct_images_count=verified_direct_images_count,
        total_gradings_count=total_gradings_count,
        glaucoma_gradings_count=glaucoma_gradings_count,
        dr_gradings_count=dr_gradings_count,
        vcdr_data_count=vcdr_data_count,
        grading_distribution=grading_distribution,
        vcdr_ranges=vcdr_ranges,
        dr_impression_distribution=dr_impression_distribution,
        glaucoma_impression_distribution=glaucoma_impression_distribution,
    )