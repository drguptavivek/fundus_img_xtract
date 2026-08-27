"""SQLAlchemy repository for the unified authorization grant table."""

from __future__ import annotations

from sqlalchemy import false, or_, select

from authz_v2.core.principals import PrincipalDTO
from authz_v2.core.resources import ScopeDTO
from authz_v2.core.roles import Role, ScopeType, may_delegate
from authz_v2.domain.exceptions import AuthorizationDataError
from authz_v2.domain.grants import GrantViewDTO
from authz_v2.domain.models import AuthorizationGrant
from authz_v2.repositories.contracts import GrantRecord
from authz_v2.resources.references import is_positive_int
from models import Hospital, LabUnit, Project, User
from models import Role as RoleModel
from project_configuration.models import ProjectLabUnit


class GrantRepository:
    def __init__(self, db) -> None:
        self.db = db

    def principal(self, user_id: int) -> PrincipalDTO | None:
        user = self.db.get(User, user_id)
        if user is None:
            return None
        return PrincipalDTO(user.id, active=bool(user.is_active), authenticated=True)

    def grants_for(self, user_id: int) -> tuple[GrantRecord, ...]:
        rows = self.db.execute(
            select(AuthorizationGrant, RoleModel.name)
            .join(RoleModel, RoleModel.id == AuthorizationGrant.role_id)
            .where(
                AuthorizationGrant.user_id == user_id,
                AuthorizationGrant.active.is_(True),
            )
        ).all()
        result: list[GrantRecord] = []
        for grant, role_name in rows:
            try:
                role = Role(role_name)
            except ValueError as exc:
                raise AuthorizationDataError(
                    f"unknown stored authorization role id={grant.role_id}"
                ) from exc
            scope = self._scope_for(grant)
            if scope is None:
                raise AuthorizationDataError(
                    f"unresolved stored authorization scope grant_id={grant.id}"
                )
            result.append(
                GrantRecord(grant.id, grant.user_id, role, scope, grant.active)
            )
        return tuple(result)

    def list_manageable(self, actor_id: int) -> tuple[GrantViewDTO, ...]:
        """Load only grants the actor can delegate at a containing scope."""
        actor_grants = self.grants_for(actor_id)
        role_ids = dict(
            self.db.execute(
                select(RoleModel.name, RoleModel.id).where(
                    RoleModel.name.in_([role.value for role in Role])
                )
            ).all()
        )
        conditions = []
        for actor_grant in actor_grants:
            delegated_role_ids = [
                role_ids[role.value]
                for role in Role
                if role.value in role_ids and may_delegate(actor_grant.role, role)
            ]
            if not delegated_role_ids:
                continue
            scope = actor_grant.scope
            scope_condition = false()
            if scope.scope_type is ScopeType.SYSTEM:
                scope_condition = AuthorizationGrant.id.is_not(None)
            elif scope.scope_type is ScopeType.HOSPITAL:
                scope_condition = or_(
                    AuthorizationGrant.hospital_id == scope.scope_id,
                    AuthorizationGrant.lab_unit_id.in_(
                        select(LabUnit.id).where(LabUnit.hospital_id == scope.scope_id)
                    ),
                )
            elif scope.scope_type is ScopeType.LAB_UNIT:
                scope_condition = AuthorizationGrant.lab_unit_id == scope.scope_id
            elif scope.scope_type is ScopeType.PROJECT:
                scope_condition = or_(
                    AuthorizationGrant.project_id == scope.scope_id,
                    AuthorizationGrant.project_lab_unit_id.in_(
                        select(ProjectLabUnit.id).where(
                            ProjectLabUnit.project_id == scope.scope_id
                        )
                    ),
                )
            elif scope.scope_type is ScopeType.PROJECT_LAB_UNIT:
                scope_condition = (
                    AuthorizationGrant.project_lab_unit_id == scope.scope_id
                )
            conditions.append(
                (AuthorizationGrant.role_id.in_(delegated_role_ids)) & scope_condition
            )

        rows = self.db.execute(
            select(AuthorizationGrant, RoleModel.name)
            .join(RoleModel, RoleModel.id == AuthorizationGrant.role_id)
            .where(
                AuthorizationGrant.user_id != actor_id,
                or_(*conditions) if conditions else false(),
            )
            .order_by(AuthorizationGrant.id)
        ).all()
        result: list[GrantViewDTO] = []
        for grant, role_name in rows:
            try:
                role = Role(role_name)
            except ValueError as exc:
                raise AuthorizationDataError(
                    f"unknown stored authorization role id={grant.role_id}"
                ) from exc
            scope = self._scope_for(grant)
            if scope is None:
                raise AuthorizationDataError(
                    f"unresolved stored authorization scope grant_id={grant.id}"
                )
            result.append(self.as_view(grant, role=role, scope=scope))
        return tuple(result)

    def as_view(
        self,
        grant: AuthorizationGrant,
        *,
        role: Role | None = None,
        scope: ScopeDTO | None = None,
    ) -> GrantViewDTO:
        """Detach one grant from ORM state for authorized serialization."""
        role = role or self.role_for(grant.role_id)
        scope = scope or self._scope_for(grant)
        if role is None or scope is None:
            raise AuthorizationDataError(
                f"unresolved stored authorization grant id={grant.id}"
            )
        return GrantViewDTO(
            id=grant.id,
            user_id=grant.user_id,
            role=role,
            scope=scope,
            description=grant.description,
            active=grant.active,
            created_by_user_id=grant.created_by_user_id,
            updated_by_user_id=grant.updated_by_user_id,
            deactivated_by_user_id=grant.deactivated_by_user_id,
            created_at=grant.created_at,
            updated_at=grant.updated_at,
            deactivated_at=grant.deactivated_at,
        )

    def get_for_update(self, grant_id: int) -> AuthorizationGrant | None:
        return self.db.scalar(
            select(AuthorizationGrant)
            .where(AuthorizationGrant.id == grant_id)
            .with_for_update()
        )

    def role_id(self, role: Role) -> int | None:
        return self.db.scalar(select(RoleModel.id).where(RoleModel.name == role.value))

    def role_for(self, role_id: int) -> Role | None:
        name = self.db.scalar(select(RoleModel.name).where(RoleModel.id == role_id))
        try:
            return Role(name) if name is not None else None
        except ValueError:
            return None

    def find_historical(
        self,
        *,
        user_id: int,
        role_id: int,
        scope: ScopeDTO,
    ) -> AuthorizationGrant | None:
        statement = select(AuthorizationGrant).where(
            AuthorizationGrant.user_id == user_id,
            AuthorizationGrant.role_id == role_id,
            AuthorizationGrant.scope_type == scope.scope_type.value,
        )
        if scope.scope_type is ScopeType.SYSTEM:
            statement = statement.where(
                AuthorizationGrant.hospital_id.is_(None),
                AuthorizationGrant.lab_unit_id.is_(None),
                AuthorizationGrant.project_id.is_(None),
                AuthorizationGrant.project_lab_unit_id.is_(None),
            )
        else:
            target_column, target_id = self._target(scope)
            statement = statement.where(target_column == target_id)
        statement = statement.with_for_update()
        return self.db.scalar(statement)

    def add(self, grant: AuthorizationGrant) -> AuthorizationGrant:
        self.db.add(grant)
        self.db.flush()
        return grant

    def scope_for(self, grant: AuthorizationGrant) -> ScopeDTO | None:
        return self._scope_for(grant)

    def resolve_scope(self, scope: ScopeDTO) -> ScopeDTO | None:
        """Reload a requested grant target and derive its lineage from storage."""
        if scope.scope_type is ScopeType.SYSTEM:
            return ScopeDTO(ScopeType.SYSTEM) if scope.scope_id is None else None
        if not is_positive_int(scope.scope_id):
            return None
        if scope.scope_type is ScopeType.HOSPITAL:
            hospital = self.db.get(Hospital, scope.scope_id)
            if hospital is None:
                return None
            return ScopeDTO(ScopeType.HOSPITAL, hospital.id, hospital_id=hospital.id)
        if scope.scope_type is ScopeType.LAB_UNIT:
            lab = self.db.get(LabUnit, scope.scope_id)
            if lab is None:
                return None
            return ScopeDTO(
                ScopeType.LAB_UNIT,
                lab.id,
                hospital_id=lab.hospital_id,
                lab_unit_id=lab.id,
            )
        if scope.scope_type is ScopeType.PROJECT:
            project = self.db.get(Project, scope.scope_id)
            if project is None:
                return None
            return ScopeDTO(ScopeType.PROJECT, project.id, project_id=project.id)
        project_lab = self.db.get(ProjectLabUnit, scope.scope_id)
        if project_lab is None:
            return None
        lab = self.db.get(LabUnit, project_lab.lab_unit_id)
        if lab is None:
            return None
        return ScopeDTO(
            ScopeType.PROJECT_LAB_UNIT,
            project_lab.id,
            hospital_id=lab.hospital_id,
            lab_unit_id=lab.id,
            project_id=project_lab.project_id,
            project_lab_unit_id=project_lab.id,
        )

    @staticmethod
    def _target(scope: ScopeDTO):
        return {
            ScopeType.SYSTEM: (AuthorizationGrant.id, None),
            ScopeType.HOSPITAL: (AuthorizationGrant.hospital_id, scope.scope_id),
            ScopeType.LAB_UNIT: (AuthorizationGrant.lab_unit_id, scope.scope_id),
            ScopeType.PROJECT: (AuthorizationGrant.project_id, scope.scope_id),
            ScopeType.PROJECT_LAB_UNIT: (
                AuthorizationGrant.project_lab_unit_id,
                scope.scope_id,
            ),
        }[scope.scope_type]

    def _scope_for(self, grant: AuthorizationGrant) -> ScopeDTO | None:
        scope_type = ScopeType(grant.scope_type)
        if scope_type is ScopeType.SYSTEM:
            return ScopeDTO(scope_type)
        if scope_type is ScopeType.HOSPITAL:
            return ScopeDTO(
                scope_type, grant.hospital_id, hospital_id=grant.hospital_id
            )
        if scope_type is ScopeType.LAB_UNIT:
            lab = self.db.get(LabUnit, grant.lab_unit_id)
            if lab is None:
                return None
            return ScopeDTO(
                scope_type, lab.id, hospital_id=lab.hospital_id, lab_unit_id=lab.id
            )
        if scope_type is ScopeType.PROJECT:
            return ScopeDTO(scope_type, grant.project_id, project_id=grant.project_id)
        project_lab = self.db.get(ProjectLabUnit, grant.project_lab_unit_id)
        if project_lab is None:
            return None
        lab = self.db.get(LabUnit, project_lab.lab_unit_id)
        return ScopeDTO(
            scope_type,
            project_lab.id,
            hospital_id=lab.hospital_id if lab else None,
            lab_unit_id=project_lab.lab_unit_id,
            project_id=project_lab.project_id,
            project_lab_unit_id=project_lab.id,
        )
