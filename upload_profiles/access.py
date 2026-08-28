"""Authorization relationships carried by upload-profile assignments."""

from __future__ import annotations

from sqlalchemy import exists, or_, select


def uploader_qualification_clause(*, user_id: int):
    """SQL evidence that the active actor holds the uploader qualification."""
    from models import Role, User, UserRole

    return exists(
        select(UserRole.user_id)
        .join(User, User.id == UserRole.user_id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            UserRole.user_id == int(user_id),
            User.is_active.is_(True),
            Role.name == "fileUploader",
        )
    )


def is_uploader_qualified(db, *, user_id: int) -> bool:
    """Return whether the current user may combine an upload assignment."""
    return bool(db.execute(select(uploader_qualification_clause(user_id=user_id))).scalar())


def _assignment_query(*, user_id: int, project_id: int | None = None):
    from project_configuration.models import ProjectLabUnit
    from upload_profiles.models import (
        ProjectUploadProfile,
        ProjectUploadProfileAssignment,
        UploadProfile,
    )

    query = (
        select(ProjectUploadProfileAssignment.id)
        .join(
            ProjectUploadProfile,
            ProjectUploadProfile.id
            == ProjectUploadProfileAssignment.project_upload_profile_id,
        )
        .join(UploadProfile, UploadProfile.id == ProjectUploadProfile.upload_profile_id)
        .join(
            ProjectLabUnit,
            (ProjectLabUnit.project_id == ProjectUploadProfile.project_id)
            & (ProjectLabUnit.lab_unit_id == ProjectUploadProfileAssignment.lab_unit_id)
            & ProjectLabUnit.active.is_(True),
        )
        .where(
            ProjectUploadProfileAssignment.user_id == int(user_id),
            ProjectUploadProfileAssignment.active.is_(True),
            ProjectUploadProfile.active.is_(True),
            UploadProfile.active.is_(True),
            uploader_qualification_clause(user_id=user_id),
        )
    )
    if project_id is not None:
        query = query.where(ProjectUploadProfile.project_id == int(project_id))
    return query


def has_upload_assignment(
    db,
    *,
    user_id: int,
    upload_kinds=(),
    project_id: int | None = None,
    lab_unit_id: int | None = None,
) -> bool:
    """Check one active assignment, optionally narrowed by kind/project/lab."""
    from upload_profiles.models import (
        ProjectUploadProfileAssignment,
        UploadProfile,
        UploadProfileKind,
    )

    query = _assignment_query(user_id=user_id, project_id=project_id)
    kinds = frozenset(str(kind) for kind in upload_kinds if kind)
    if kinds:
        query = query.join(
            UploadProfileKind,
            UploadProfileKind.upload_profile_id == UploadProfile.id,
        ).where(UploadProfileKind.upload_kind.in_(kinds))
    if lab_unit_id is not None:
        query = query.where(
            ProjectUploadProfileAssignment.lab_unit_id == int(lab_unit_id)
        )
    return db.execute(query.limit(1)).scalar_one_or_none() is not None


def upload_assignment_lab_clause(*, user_id: int, lab_unit_column):
    """SQL clause for Lab Units reached by an exact active assignment."""
    from upload_profiles.models import ProjectUploadProfileAssignment

    return exists(
        _assignment_query(user_id=user_id).where(
            ProjectUploadProfileAssignment.lab_unit_id == lab_unit_column
        )
    )


def upload_assignment_row_clause(
    *, user_id: int, project_id_column, lab_unit_id_column
):
    """SQL clause matching a persisted project row to the same assignment."""
    from upload_profiles.models import (
        ProjectUploadProfile,
        ProjectUploadProfileAssignment,
    )

    return exists(
        _assignment_query(user_id=user_id).where(
            ProjectUploadProfile.project_id == project_id_column,
            ProjectUploadProfileAssignment.lab_unit_id == lab_unit_id_column,
        )
    )


def has_remidio_sync_assignment(
    db,
    *,
    user_id: int,
    project_id: int,
    lab_unit_id: int | None = None,
) -> bool:
    """Check assignment to an active Remidio API binding."""
    from remidio_api_integration.models import ProjectUploadProfileRemidioApiBinding
    from upload_profiles.models import (
        ProjectUploadProfile,
        ProjectUploadProfileAssignment,
    )

    binding = ProjectUploadProfileRemidioApiBinding
    query = (
        _assignment_query(user_id=user_id, project_id=project_id)
        .join(binding, binding.project_upload_profile_id == ProjectUploadProfile.id)
        .where(
            binding.active.is_(True),
            or_(
                binding.lab_unit_id.is_(None),
                binding.lab_unit_id
                == ProjectUploadProfileAssignment.lab_unit_id,
            ),
        )
    )
    if lab_unit_id is not None:
        query = query.where(
            ProjectUploadProfileAssignment.lab_unit_id == int(lab_unit_id)
        )
    return db.execute(query.limit(1)).scalar_one_or_none() is not None
