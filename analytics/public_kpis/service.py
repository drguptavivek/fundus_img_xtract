"""Cached query service for privacy-safe public KPI aggregates."""

from __future__ import annotations

from sqlalchemy import func, or_, select

from app_cache import cache
from auth.utils import utcnow
from db_transaction_manager import get_db_session
from models import (
    DirectImageUpload,
    Disease,
    EncounterFile,
    EncounterSetGradingScope,
    EncounterSetImage,
    Grade,
    GradingTask,
    PatientEncounters,
    Project,
)

from .dto import PublicKpisDTO

PUBLIC_KPI_CACHE_SECONDS = 5 * 60
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")


def _disease_task_counts_query():
    """Build disease counts for image targets, excluding unified scopes."""

    return (
        select(Disease.name, func.count(GradingTask.id).label("task_count"))
        .join(GradingTask, GradingTask.disease_id == Disease.id)
        .outerjoin(
            EncounterSetGradingScope,
            EncounterSetGradingScope.id == GradingTask.encounter_set_scope_id,
        )
        .where(
            or_(
                GradingTask.encounter_file_id.is_not(None),
                GradingTask.direct_image_upload_id.is_not(None),
                GradingTask.encounter_set_image_id.is_not(None),
            ),
            or_(
                EncounterSetGradingScope.id.is_(None),
                EncounterSetGradingScope.link_role != "unified",
            ),
        )
        .group_by(Disease.id, Disease.name)
        .order_by(Disease.name)
    )


@cache.memoize(timeout=PUBLIC_KPI_CACHE_SECONDS)
def get_public_kpis() -> PublicKpisDTO:
    """Return cached system-wide aggregates without scoped or patient data."""

    image_predicate = or_(
        *(func.lower(EncounterFile.filename).like(f"%{extension}") for extension in _IMAGE_EXTENSIONS)
    )
    zip_encounter_predicate = (
        PatientEncounters.zip_file_id.is_not(None)
        & PatientEncounters.is_set_based.is_(False)
    )
    encounter_set_predicate = PatientEncounters.is_set_based.is_(True)

    query = select(
        select(func.count(EncounterFile.id)).where(image_predicate).scalar_subquery().label("zip_images"),
        select(func.count(DirectImageUpload.id)).scalar_subquery().label("direct_images"),
        select(func.count(EncounterSetImage.id)).scalar_subquery().label("encounter_set_images"),
        select(func.count(PatientEncounters.id)).where(zip_encounter_predicate).scalar_subquery().label("zip_encounters"),
        select(func.count(PatientEncounters.id)).where(encounter_set_predicate).scalar_subquery().label("encounter_set_encounters"),
        select(func.count(Grade.id)).where(Grade.role_slot == "ai").scalar_subquery().label("total_ai_gradings"),
        select(func.count(Grade.id)).scalar_subquery().label("total_gradings"),
        select(func.count(Project.id)).where(Project.active.is_(True)).scalar_subquery().label("active_projects"),
        select(func.count(GradingTask.id)).scalar_subquery().label("total_tasks"),
    )

    with get_db_session() as db:
        row = db.execute(query).one()
        disease_rows = db.execute(_disease_task_counts_query()).all()

    zip_images = int(row.zip_images or 0)
    direct_images = int(row.direct_images or 0)
    encounter_set_images = int(row.encounter_set_images or 0)
    zip_encounters = int(row.zip_encounters or 0)
    encounter_set_encounters = int(row.encounter_set_encounters or 0)

    return PublicKpisDTO(
        total_images=zip_images + direct_images + encounter_set_images,
        zip_images=zip_images,
        direct_images=direct_images,
        encounter_set_images=encounter_set_images,
        total_encounters=zip_encounters + encounter_set_encounters,
        zip_encounters=zip_encounters,
        encounter_set_encounters=encounter_set_encounters,
        total_ai_gradings=int(row.total_ai_gradings or 0),
        total_gradings=int(row.total_gradings or 0),
        active_projects=int(row.active_projects or 0),
        total_tasks=int(row.total_tasks or 0),
        disease_task_counts={str(item.name): int(item.task_count) for item in disease_rows},
        generated_at=utcnow(),
    )
