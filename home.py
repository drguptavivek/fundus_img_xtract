from flask import render_template
from sqlalchemy import select, func, or_, distinct, case, and_
from db_transaction_manager import get_db_session
from models import (
    Session, EncounterFile, PatientEncounters, ImageGrading,
    GlaucomaReport, GlaucomaResultsCleaned, DiabeticRetinopathyReport,
    DirectImageUpload, DirectImageVerify, LabUnit, Disease,
    Grade, DiseaseGrading
)

def homepage():
    # Compute counts for the public home (unauthenticated visitors)
    img_exts = [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"]  # same set the app serves
    
    with get_db_session() as db:
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
        disease_map = {
            (d.name or "").strip().lower(): d.id for d in db.execute(select(Disease)).scalars()
        }
        glaucoma_id = disease_map.get("glaucoma")
        dr_id = disease_map.get("dr")

        total_gradings_count = db.execute(select(func.count(Grade.id))).scalar_one()

        glaucoma_gradings_count = 0
        if glaucoma_id is not None:
            glaucoma_gradings_count = db.execute(
                select(func.count(Grade.id))
                .join(DiseaseGrading, Grade.disease_grading_id == DiseaseGrading.id)
                .where(DiseaseGrading.disease_id == glaucoma_id)
            ).scalar_one()

        dr_gradings_count = 0
        if dr_id is not None:
            dr_gradings_count = db.execute(
                select(func.count(Grade.id))
                .join(DiseaseGrading, Grade.disease_grading_id == DiseaseGrading.id)
                .where(DiseaseGrading.disease_id == dr_id)
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
        
        # VCDR value ranges for chart (adjusted cutoffs)
        vcdr_ranges = db.execute(
            select(
                func.sum(case((GlaucomaResultsCleaned.vcdr_right_num < 0.5, 1), else_=0)).label('normal_right'),
                func.sum(case((and_(GlaucomaResultsCleaned.vcdr_right_num >= 0.5, GlaucomaResultsCleaned.vcdr_right_num < 0.7), 1), else_=0)).label('borderline_right'),
                func.sum(case((and_(GlaucomaResultsCleaned.vcdr_right_num >= 0.7, GlaucomaResultsCleaned.vcdr_right_num < 0.8), 1), else_=0)).label('abnormal_right'),
                func.sum(case((GlaucomaResultsCleaned.vcdr_right_num >= 0.8, 1), else_=0)).label('severely_abnormal_right'),
                func.sum(case((GlaucomaResultsCleaned.vcdr_left_num < 0.5, 1), else_=0)).label('normal_left'),
                func.sum(case((and_(GlaucomaResultsCleaned.vcdr_left_num >= 0.5, GlaucomaResultsCleaned.vcdr_left_num < 0.7), 1), else_=0)).label('borderline_left'),
                func.sum(case((and_(GlaucomaResultsCleaned.vcdr_left_num >= 0.7, GlaucomaResultsCleaned.vcdr_left_num < 0.8), 1), else_=0)).label('abnormal_left'),
                func.sum(case((GlaucomaResultsCleaned.vcdr_left_num >= 0.8, 1), else_=0)).label('severely_abnormal_left')
            )
            .where(
                or_(
                    GlaucomaResultsCleaned.vcdr_right_num.isnot(None),
                    GlaucomaResultsCleaned.vcdr_left_num.isnot(None)
                )
            )
        ).first()
        
        # Calculate ungradable images
        total_gradable_images = db.execute(
            select(func.count(ImageGrading.id))
            .where(ImageGrading.graded_for.in_(["glaucoma", "dr"]))
        ).scalar_one()
        
        ungradable_images = db.execute(
            select(func.count(ImageGrading.id))
            .where(and_(
                ImageGrading.graded_for.in_(["glaucoma", "dr"]),
                ImageGrading.impression == "Not gradable"
            ))
        ).scalar_one()
        
        gradable_images = total_gradable_images - ungradable_images
        
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
        
        # Images by lab unit and disease (stacked bar chart)
        images_by_lab_unit_disease = db.execute(
            select(
                LabUnit.name.label('lab_unit_name'),
                Disease.name.label('disease_name'),
                func.count(DirectImageUpload.id).label('image_count')
            )
            .join(DirectImageUpload.lab_unit)
            .join(DirectImageUpload.disease)
            .group_by(LabUnit.name, Disease.name)
            .order_by(LabUnit.name, Disease.name)
        ).all()
        
        # Verified images by lab unit and disease (percentage chart)
        verified_images_by_lab_unit_disease = db.execute(
            select(
                LabUnit.name.label('lab_unit_name'),
                Disease.name.label('disease_name'),
                func.count(DirectImageUpload.id).label('total_images'),
                func.sum(case((DirectImageVerify.verified_status == "verified", 1), else_=0)).label('verified_images')
            )
            .join(DirectImageUpload.lab_unit)
            .join(DirectImageUpload.disease)
            .outerjoin(DirectImageVerify, DirectImageUpload.id == DirectImageVerify.image_upload_id)
            .group_by(LabUnit.name, Disease.name)
            .order_by(LabUnit.name, Disease.name)
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
        gradable_images=gradable_images,
        ungradable_images=ungradable_images,
        images_by_lab_unit_disease=images_by_lab_unit_disease,
        verified_images_by_lab_unit_disease=verified_images_by_lab_unit_disease
    )
