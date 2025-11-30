"""Homepage stats and chart feed for Fundus Image Manager."""

from flask import render_template
from flask.typing import ResponseReturnValue
from sqlalchemy import select, func, or_, case, and_, text, bindparam
from db_transaction_manager import get_db_session
from models import (
    Session,
    EncounterFile,
    PatientEncounters,
    GlaucomaReport,
    GlaucomaResultsCleaned,
    DiabeticRetinopathyReport,
    DirectImageUpload,
    DirectImageVerify,
    LabUnit,
    Disease,
    Grade,
    DiseaseGrading,
    GradingTask,
)


def homepage() -> ResponseReturnValue:
    """Render the public homepage with KPI counters and chart data."""

    img_exts = [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"]

    with get_db_session() as db:
        img_filters = [func.lower(EncounterFile.filename).like(f"%{ext}") for ext in img_exts]
        images_count = db.execute(
            select(func.count(EncounterFile.id)).where(or_(*img_filters))
        ).scalar_one()
        screenings_count = db.execute(select(func.count(PatientEncounters.id))).scalar_one()

        direct_images_count = db.execute(select(func.count(DirectImageUpload.id))).scalar_one()

        verified_direct_images_count = db.execute(
            select(func.count(DirectImageVerify.id)).where(
                DirectImageVerify.verified_status == "verified"
            )
        ).scalar_one()

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

    vcdr_data_count = db.execute(
        select(func.count(GlaucomaResultsCleaned.id)).where(
            or_(
                GlaucomaResultsCleaned.vcdr_right_num.isnot(None),
                GlaucomaResultsCleaned.vcdr_left_num.isnot(None),
            )
        )
    ).scalar_one()

    disease_image_distribution = db.execute(
        text(
            """
            SELECT
                COALESCE(disease_name, 'Unknown') AS disease_name,
                COUNT(DISTINCT image_id) AS image_count
            FROM mvw_grading_data_all
            WHERE image_id IS NOT NULL
            GROUP BY COALESCE(disease_name, 'Unknown')
            ORDER BY image_count DESC
            """
        )
    ).all()

    grading_distribution = db.execute(
        text(
            """
            SELECT
                COALESCE(disease_name, 'Unknown') AS disease_name,
                COUNT(grade_id) AS grade_count
            FROM mvw_grading_data_all
            WHERE grade_id IS NOT NULL
            GROUP BY COALESCE(disease_name, 'Unknown')
            ORDER BY grade_count DESC
            """
        )
    ).all()

    vcdr_ranges = db.execute(
        select(
            func.sum(
                case((GlaucomaResultsCleaned.vcdr_right_num < 0.5, 1), else_=0)
            ).label("normal_right"),
            func.sum(
                case(
                    (
                        and_(
                            GlaucomaResultsCleaned.vcdr_right_num >= 0.5,
                            GlaucomaResultsCleaned.vcdr_right_num < 0.7,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("borderline_right"),
            func.sum(
                case(
                    (
                        and_(
                            GlaucomaResultsCleaned.vcdr_right_num >= 0.7,
                            GlaucomaResultsCleaned.vcdr_right_num < 0.8,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("abnormal_right"),
            func.sum(
                case((GlaucomaResultsCleaned.vcdr_right_num >= 0.8, 1), else_=0)
            ).label("severely_abnormal_right"),
            func.sum(
                case((GlaucomaResultsCleaned.vcdr_left_num < 0.5, 1), else_=0)
            ).label("normal_left"),
            func.sum(
                case(
                    (
                        and_(
                            GlaucomaResultsCleaned.vcdr_left_num >= 0.5,
                            GlaucomaResultsCleaned.vcdr_left_num < 0.7,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("borderline_left"),
            func.sum(
                case(
                    (
                        and_(
                            GlaucomaResultsCleaned.vcdr_left_num >= 0.7,
                            GlaucomaResultsCleaned.vcdr_left_num < 0.8,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("abnormal_left"),
            func.sum(
                case((GlaucomaResultsCleaned.vcdr_left_num >= 0.8, 1), else_=0)
            ).label("severely_abnormal_left"),
        ).where(
            or_(
                GlaucomaResultsCleaned.vcdr_right_num.isnot(None),
                GlaucomaResultsCleaned.vcdr_left_num.isnot(None),
            )
        )
    ).first()

    target_diseases = {"glaucoma", "dr"}
    total_gradable_images = db.execute(
        text(
            """
            SELECT COUNT(*) AS total_count
            FROM mvw_grading_data_all
            WHERE
                grade_id IS NOT NULL
                AND LOWER(disease_name) IN :diseases
            """
        ).bindparams(bindparam("diseases", expanding=True)),
        {"diseases": tuple(target_diseases)},
    ).scalar_one()

    ungradable_images = db.execute(
        text(
            """
            SELECT COUNT(*) AS ungradable_count
            FROM mvw_grading_data_all
            WHERE
                grade_id IS NOT NULL
                AND LOWER(disease_name) IN :diseases
                AND LOWER(COALESCE(consensus_final_grade_name, grade_name, '')) = 'not gradable'
            """
        ).bindparams(bindparam("diseases", expanding=True)),
        {"diseases": tuple(target_diseases)},
    ).scalar_one()

    gradable_images = max(total_gradable_images - ungradable_images, 0)

    dr_impression_distribution = db.execute(
        text(
            """
            SELECT
                COALESCE(consensus_final_grade_name, grade_name) AS impression,
                COUNT(*) AS grade_count
            FROM mvw_grading_data_all
            WHERE
                grade_id IS NOT NULL
                AND LOWER(disease_name) = 'dr'
            GROUP BY COALESCE(consensus_final_grade_name, grade_name)
            ORDER BY grade_count DESC
            """
        )
    ).all()

    glaucoma_impression_distribution = db.execute(
        text(
            """
            SELECT
                consensus_final_grade_name AS impression,
                COUNT(DISTINCT image_id) AS image_count
            FROM mvw_grading_data_all
            WHERE
                image_id IS NOT NULL
                AND LOWER(disease_name) = 'glaucoma'
                AND consensus_final_grade_name IS NOT NULL
            GROUP BY consensus_final_grade_name
            ORDER BY image_count DESC
            """
        )
    ).all()

    images_by_lab_unit_disease = db.execute(
        text(
            """
            SELECT
                lab_unit_name,
                disease_name,
                COUNT(DISTINCT image_id) AS image_count
            FROM mvw_grading_data_all
            WHERE lab_unit_name IS NOT NULL AND disease_name IS NOT NULL
            GROUP BY lab_unit_name, disease_name
            ORDER BY lab_unit_name, disease_name
            """
        )
    ).all()

    verified_images_by_lab_unit_disease = db.execute(
        text(
            """
            SELECT
                lab_unit_name,
                disease_name,
                COUNT(DISTINCT image_id) AS total_images,
                COUNT(DISTINCT CASE
                    WHEN LOWER(COALESCE(direct_image_verified_status, encounter_verified_status, '')) = 'verified'
                    THEN image_id
                END) AS verified_images
            FROM mvw_grading_data_all
            WHERE lab_unit_name IS NOT NULL AND disease_name IS NOT NULL
            GROUP BY lab_unit_name, disease_name
            ORDER BY lab_unit_name, disease_name
            """
        )
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
        disease_image_distribution=disease_image_distribution,
        vcdr_ranges=vcdr_ranges,
        dr_impression_distribution=dr_impression_distribution,
        glaucoma_impression_distribution=glaucoma_impression_distribution,
        gradable_images=gradable_images,
        ungradable_images=ungradable_images,
        images_by_lab_unit_disease=images_by_lab_unit_disease,
        verified_images_by_lab_unit_disease=verified_images_by_lab_unit_disease,
    )
