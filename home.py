"""Homepage stats and chart feed for Fundus Image Manager."""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

from flask import render_template
from flask.typing import ResponseReturnValue
from sqlalchemy import select, func, or_, case, and_, text, bindparam
from app_cache import cache
from db_transaction_manager import get_db_session
from models import EncounterFile, PatientEncounters, GlaucomaResultsCleaned, DirectImageUpload
from models import DirectImageVerify, Disease, Grade, DiseaseGrading
from utils.mvw_image_listing_v2 import get_mv_name_for_disease_name

_CACHE_KEY = "home:charts:v1"
_CACHE_TTL_SECONDS = 15 * 60  # 15 minutes


def _rows_to_dicts(rows: List[Any]) -> List[Dict[str, Any]]:
    """Convert SQLAlchemy row objects to plain dictionaries."""
    return [dict(row._mapping) for row in rows]


def _build_v2_union_sql(disease_rows: List[Tuple[int, str]]) -> str:
    selects = []
    for disease_id, disease_name in disease_rows:
        mv_name = get_mv_name_for_disease_name(str(disease_name), int(disease_id))
        selects.append(
            f"""
            SELECT
                image_uuid,
                disease_id,
                disease_name,
                lab_unit_name,
                task_lab_unit_id,
                task_id,
                final_grade_name,
                final_impression,
                has_resident,
                has_resident2,
                has_arbitrator,
                has_review,
                has_regrade_adj,
                direct_image_verified_status,
                encounter_verified_status
            FROM {mv_name}
            """
        )
    if not selects:
        return """
            SELECT
                NULL::text AS image_uuid,
                NULL::integer AS disease_id,
                NULL::text AS disease_name,
                NULL::text AS lab_unit_name,
                NULL::integer AS task_lab_unit_id,
                NULL::integer AS task_id,
                NULL::text AS final_grade_name,
                NULL::text AS final_impression,
                FALSE AS has_resident,
                FALSE AS has_resident2,
                FALSE AS has_arbitrator,
                FALSE AS has_review,
                FALSE AS has_regrade_adj,
                NULL::text AS direct_image_verified_status,
                NULL::text AS encounter_verified_status
            WHERE 1=0
        """
    return " UNION ALL ".join(selects)


def _get_existing_v2_mv_names(db: Any) -> Set[str]:
    """Return existing per-disease image-listing materialized view names."""
    rows = db.execute(
        text(
            """
            SELECT matviewname
            FROM pg_matviews
            WHERE schemaname = current_schema()
              AND matviewname LIKE 'mvw_image_listing\\_%\\_v2' ESCAPE '\\'
            """
        )
    ).all()
    return {str(row[0]) for row in rows}


def _filter_disease_rows_with_existing_v2_views(
    disease_rows: List[Tuple[int, str]], existing_mv_names: Set[str]
) -> List[Tuple[int, str]]:
    """Keep only diseases whose per-disease v2 view exists."""
    filtered_rows: List[Tuple[int, str]] = []
    for disease_id, disease_name in disease_rows:
        mv_name = get_mv_name_for_disease_name(str(disease_name), int(disease_id))
        if mv_name in existing_mv_names:
            filtered_rows.append((disease_id, disease_name))
    return filtered_rows


@cache.cached(timeout=_CACHE_TTL_SECONDS, key_prefix=_CACHE_KEY)
def _compute_home_payload() -> Dict[str, Any]:
    """Compute home KPIs and chart data, ready for template rendering."""

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

        vcdr_ranges_row = db.execute(
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

        vcdr_ranges = (
            {key: int(value or 0) for key, value in dict(vcdr_ranges_row._mapping).items()}
            if vcdr_ranges_row
            else {
                "normal_right": 0,
                "borderline_right": 0,
                "abnormal_right": 0,
                "severely_abnormal_right": 0,
                "normal_left": 0,
                "borderline_left": 0,
                "abnormal_left": 0,
                "severely_abnormal_left": 0,
            }
        )

        disease_rows = db.execute(select(Disease.id, Disease.name).order_by(Disease.id)).all()
        existing_mv_names = _get_existing_v2_mv_names(db)
        v2_disease_rows = _filter_disease_rows_with_existing_v2_views(
            disease_rows, existing_mv_names
        )
        v2_union = _build_v2_union_sql(v2_disease_rows)
        has_grade_expr = (
            "has_resident OR has_resident2 OR has_arbitrator OR has_review OR has_regrade_adj"
        )

        target_diseases = {"glaucoma", "dr"}
        total_gradable_images = db.execute(
            text(
                f"""
                WITH v2 AS ({v2_union})
                SELECT COUNT(*) AS total_count
                FROM v2
                WHERE
                    ({has_grade_expr})
                    AND LOWER(disease_name) IN :diseases
                """
            ).bindparams(bindparam("diseases", expanding=True)),
            {"diseases": tuple(target_diseases)},
        ).scalar_one()

        ungradable_images = db.execute(
            text(
                f"""
                WITH v2 AS ({v2_union})
                SELECT COUNT(*) AS ungradable_count
                FROM v2
                WHERE
                    ({has_grade_expr})
                    AND LOWER(disease_name) IN :diseases
                    AND LOWER(COALESCE(final_grade_name, final_impression, '')) = 'not gradable'
                """
            ).bindparams(bindparam("diseases", expanding=True)),
            {"diseases": tuple(target_diseases)},
        ).scalar_one()

        gradable_images = max(total_gradable_images - ungradable_images, 0)

        disease_image_distribution = _rows_to_dicts(
            db.execute(
                text(
                    f"""
                    WITH v2 AS ({v2_union})
                    SELECT
                        COALESCE(disease_name, 'Unknown') AS disease_name,
                        COUNT(DISTINCT image_uuid) AS image_count
                    FROM v2
                    WHERE image_uuid IS NOT NULL
                    GROUP BY COALESCE(disease_name, 'Unknown')
                    ORDER BY image_count DESC
                    """
                )
            ).all()
        )

        grading_distribution = _rows_to_dicts(
            db.execute(
                text(
                    f"""
                    WITH v2 AS ({v2_union})
                    SELECT
                        COALESCE(disease_name, 'Unknown') AS disease_name,
                        COUNT(task_id) AS grade_count
                    FROM v2
                    WHERE ({has_grade_expr})
                    GROUP BY COALESCE(disease_name, 'Unknown')
                    ORDER BY grade_count DESC
                    """
                )
            ).all()
        )

        dr_impression_distribution = _rows_to_dicts(
            db.execute(
                text(
                    f"""
                    WITH v2 AS ({v2_union})
                    SELECT
                        COALESCE(final_grade_name, final_impression) AS impression,
                        COUNT(*) AS grade_count
                    FROM v2
                    WHERE
                        ({has_grade_expr})
                        AND LOWER(disease_name) = 'dr'
                        AND COALESCE(final_grade_name, final_impression) IS NOT NULL
                    GROUP BY COALESCE(final_grade_name, final_impression)
                    ORDER BY grade_count DESC
                    """
                )
            ).all()
        )

        glaucoma_impression_distribution = _rows_to_dicts(
            db.execute(
                text(
                    f"""
                    WITH v2 AS ({v2_union})
                    SELECT
                        final_grade_name AS impression,
                        COUNT(DISTINCT image_uuid) AS image_count
                    FROM v2
                    WHERE
                        image_uuid IS NOT NULL
                        AND LOWER(disease_name) = 'glaucoma'
                        AND final_grade_name IS NOT NULL
                    GROUP BY final_grade_name
                    ORDER BY image_count DESC
                    """
                )
            ).all()
        )

        images_by_lab_unit_disease = _rows_to_dicts(
            db.execute(
                text(
                    f"""
                    WITH v2 AS ({v2_union})
                    SELECT
                        lab_unit_name,
                        disease_name,
                        COUNT(DISTINCT image_uuid) AS image_count
                    FROM v2
                    WHERE lab_unit_name IS NOT NULL AND disease_name IS NOT NULL
                    GROUP BY lab_unit_name, disease_name
                    ORDER BY lab_unit_name, disease_name
                    """
                )
            ).all()
        )

        verified_images_by_lab_unit_disease = _rows_to_dicts(
            db.execute(
                text(
                    f"""
                    WITH v2 AS ({v2_union})
                    SELECT
                        lab_unit_name,
                        disease_name,
                        COUNT(DISTINCT image_uuid) AS total_images,
                        COUNT(DISTINCT CASE
                            WHEN LOWER(COALESCE(direct_image_verified_status, encounter_verified_status, '')) = 'verified'
                            THEN image_uuid
                        END) AS verified_images
                    FROM v2
                    WHERE lab_unit_name IS NOT NULL AND disease_name IS NOT NULL
                    GROUP BY lab_unit_name, disease_name
                    ORDER BY lab_unit_name, disease_name
                    """
                )
            ).all()
        )

    return {
        "images_count": images_count,
        "screenings_count": screenings_count,
        "direct_images_count": direct_images_count,
        "verified_direct_images_count": verified_direct_images_count,
        "total_gradings_count": total_gradings_count,
        "glaucoma_gradings_count": glaucoma_gradings_count,
        "dr_gradings_count": dr_gradings_count,
        "vcdr_data_count": vcdr_data_count,
        "grading_distribution": grading_distribution,
        "disease_image_distribution": disease_image_distribution,
        "vcdr_ranges": vcdr_ranges,
        "dr_impression_distribution": dr_impression_distribution,
        "glaucoma_impression_distribution": glaucoma_impression_distribution,
        "gradable_images": gradable_images,
        "ungradable_images": ungradable_images,
        "images_by_lab_unit_disease": images_by_lab_unit_disease,
        "verified_images_by_lab_unit_disease": verified_images_by_lab_unit_disease,
    }


def homepage() -> ResponseReturnValue:
    """Render the public homepage with KPI counters and chart data, cached in Redis."""
    payload = _compute_home_payload()
    return render_template("home.html", **payload)
