"""Persistence models for grants, authorization audit, and project-site policy."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from auth.utils import utcnow
from db_base import Base


class AuthorizationGrant(Base):
    """One durable role relation at exactly one supported scope."""

    __tablename__ = "authorization_grants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    hospital_id: Mapped[int | None] = mapped_column(
        ForeignKey("hospitals.id", ondelete="RESTRICT")
    )
    lab_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("lab_units.id", ondelete="RESTRICT")
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT")
    )
    project_lab_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_lab_units.id", ondelete="RESTRICT")
    )
    description: Mapped[str | None] = mapped_column(String(500))
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", index=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    deactivated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('system','hospital','lab_unit','project','project_lab_unit')",
            name="ck_authorization_grants_scope_type",
        ),
        CheckConstraint(
            "(scope_type = 'system' AND hospital_id IS NULL AND lab_unit_id IS NULL AND project_id IS NULL AND project_lab_unit_id IS NULL) OR "
            "(scope_type = 'hospital' AND hospital_id IS NOT NULL AND lab_unit_id IS NULL AND project_id IS NULL AND project_lab_unit_id IS NULL) OR "
            "(scope_type = 'lab_unit' AND hospital_id IS NULL AND lab_unit_id IS NOT NULL AND project_id IS NULL AND project_lab_unit_id IS NULL) OR "
            "(scope_type = 'project' AND hospital_id IS NULL AND lab_unit_id IS NULL AND project_id IS NOT NULL AND project_lab_unit_id IS NULL) OR "
            "(scope_type = 'project_lab_unit' AND hospital_id IS NULL AND lab_unit_id IS NULL AND project_id IS NULL AND project_lab_unit_id IS NOT NULL)",
            name="ck_authorization_grants_scope_target",
        ),
        CheckConstraint(
            "description IS NULL OR length(btrim(description)) BETWEEN 1 AND 500",
            name="ck_authorization_grants_description",
        ),
        Index(
            "uq_authorization_grants_system",
            "user_id",
            "role_id",
            unique=True,
            postgresql_where=text("scope_type = 'system'"),
        ),
        Index(
            "uq_authorization_grants_hospital",
            "user_id",
            "role_id",
            "hospital_id",
            unique=True,
            postgresql_where=text("scope_type = 'hospital'"),
        ),
        Index(
            "uq_authorization_grants_lab",
            "user_id",
            "role_id",
            "lab_unit_id",
            unique=True,
            postgresql_where=text("scope_type = 'lab_unit'"),
        ),
        Index(
            "uq_authorization_grants_project",
            "user_id",
            "role_id",
            "project_id",
            unique=True,
            postgresql_where=text("scope_type = 'project'"),
        ),
        Index(
            "uq_authorization_grants_project_lab",
            "user_id",
            "role_id",
            "project_lab_unit_id",
            unique=True,
            postgresql_where=text("scope_type = 'project_lab_unit'"),
        ),
        Index(
            "ix_authorization_grants_resolve",
            "user_id",
            "active",
            "role_id",
            "scope_type",
        ),
    )


class AuthorizationAuditEvent(Base):
    """Append-only durable record for consequential authorization events."""

    __tablename__ = "authorization_audit_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    session_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    policy_path: Mapped[str | None] = mapped_column(String(120))
    break_glass: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    request_id: Mapped[str | None] = mapped_column(String(128), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(128))
    scope_type: Mapped[str | None] = mapped_column(String(32))
    scope_id: Mapped[str | None] = mapped_column(String(128))
    detail_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )

    __table_args__ = (
        CheckConstraint(
            "outcome IN ('allow','deny','error')", name="ck_authorization_audit_outcome"
        ),
        Index("ix_authorization_audit_action_created", "action", "created_at"),
    )


class ProjectLabUnitAuthorizationPolicy(Base):
    """Per-project-site release controls, defaulting closed."""

    __tablename__ = "project_lab_unit_authorization_policies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_lab_unit_id: Mapped[int] = mapped_column(
        ForeignKey("project_lab_units.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    grade_export_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    dataset_creation_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    dataset_sharing_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class AuthorizationResourceScope(Base):
    """Authoritative lineage for resources without durable scope columns.

    The row is deliberately keyed by an explicit resource type and opaque stable
    identifier.  Callers never supply scope facts to a decision; adapters reload
    this row and reject missing, inactive, or structurally invalid bindings.
    """

    __tablename__ = "authorization_resource_scopes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    hospital_id: Mapped[int | None] = mapped_column(
        ForeignKey("hospitals.id", ondelete="RESTRICT")
    )
    lab_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("lab_units.id", ondelete="RESTRICT")
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT")
    )
    project_lab_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_lab_units.id", ondelete="RESTRICT")
    )
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    requester_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    automation_rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_automated_remote_inference_rules.id", ondelete="SET NULL")
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    domain_valid: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "resource_type", "resource_id", name="uq_authorization_resource_scope"
        ),
        CheckConstraint(
            "scope_type IN ('system','hospital','lab_unit','project','project_lab_unit')",
            name="ck_authorization_resource_scopes_scope_type",
        ),
        CheckConstraint(
            "(scope_type = 'system' AND hospital_id IS NULL AND lab_unit_id IS NULL AND project_id IS NULL AND project_lab_unit_id IS NULL) OR "
            "(scope_type = 'hospital' AND hospital_id IS NOT NULL AND lab_unit_id IS NULL AND project_id IS NULL AND project_lab_unit_id IS NULL) OR "
            "(scope_type = 'lab_unit' AND hospital_id IS NULL AND lab_unit_id IS NOT NULL AND project_id IS NULL AND project_lab_unit_id IS NULL) OR "
            "(scope_type = 'project' AND hospital_id IS NULL AND lab_unit_id IS NULL AND project_id IS NOT NULL AND project_lab_unit_id IS NULL) OR "
            "(scope_type = 'project_lab_unit' AND hospital_id IS NULL AND lab_unit_id IS NULL AND project_id IS NULL AND project_lab_unit_id IS NOT NULL)",
            name="ck_authorization_resource_scopes_scope_target",
        ),
        Index(
            "ix_authorization_resource_scopes_lookup",
            "resource_type",
            "resource_id",
            "active",
        ),
    )


class PasswordResetCredential(Base):
    """Hashed, expiring, one-use password reset credential."""

    __tablename__ = "password_reset_credentials"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "length(btrim(token_hash)) >= 32",
            name="ck_password_reset_credentials_hash",
        ),
        Index(
            "ix_password_reset_credentials_active",
            "user_id",
            "expires_at",
            postgresql_where=text("consumed_at IS NULL"),
        ),
    )


class AuthorizationUploadProfileAssignment(Base):
    """Exact classical lab/profile assignment for one uploader."""

    __tablename__ = "authorization_upload_profile_assignments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    lab_unit_id: Mapped[int] = mapped_column(
        ForeignKey("lab_units.id", ondelete="CASCADE"), nullable=False
    )
    upload_profile_id: Mapped[int] = mapped_column(
        ForeignKey("upload_profiles.id", ondelete="CASCADE"), nullable=False
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "lab_unit_id",
            "upload_profile_id",
            name="uq_authorization_upload_profile_assignment",
        ),
        Index(
            "ix_authorization_upload_profile_assignment_lookup",
            "user_id",
            "lab_unit_id",
            "active",
        ),
    )
