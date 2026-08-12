"""add project role scope grants

Revision ID: 7cb461952afe
Revises: e3f4a5b6c7d8
Create Date: 2026-08-12 06:10:39.256891
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7cb461952afe"
down_revision: Union[str, Sequence[str], None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ROLE_NAMES = (
    "project_pi",
    "site_pi",
    "principal_investigator",
    "co_investigator",
    "coordinator",
    "collaborator",
)


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _index_names(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
        if index.get("name")
    }


def _create_index_if_missing(
    name: str,
    columns: list[str],
    *,
    unique: bool = False,
    where: str | None = None,
) -> None:
    if name in _index_names("project_role_grants"):
        return
    kwargs = {"postgresql_where": sa.text(where)} if where else {}
    op.create_index(name, "project_role_grants", columns, unique=unique, **kwargs)


def _seed_roles(conn) -> None:
    if not _table_exists("roles"):
        return
    for role_name in ROLE_NAMES:
        conn.execute(
            sa.text(
                "INSERT INTO roles (name) SELECT :role_name "
                "WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = :role_name)"
            ),
            {"role_name": role_name},
        )


def _backfill_investigator_roles(conn) -> None:
    if not _table_exists("project_investigators"):
        return
    conn.execute(sa.text("""
        INSERT INTO project_role_grants (
            project_id, user_id, role_id, scope_type,
            hospital_id, lab_unit_id, active, created_at, updated_at
        )
        SELECT investigator.project_id, investigator.user_id, role.id, 'project',
               CAST(NULL AS INTEGER), CAST(NULL AS INTEGER),
               investigator.active, investigator.created_at, investigator.updated_at
        FROM project_investigators investigator
        JOIN roles role ON role.name = investigator.role
        WHERE NOT EXISTS (
            SELECT 1 FROM project_role_grants grant_row
            WHERE grant_row.project_id = investigator.project_id
              AND grant_row.user_id = investigator.user_id
              AND grant_row.role_id = role.id
              AND grant_row.scope_type = 'project'
        )
    """))


def _backfill_uploaders(conn) -> None:
    if not _table_exists("project_upload_profile_assignments") or not _table_exists("project_upload_profiles"):
        return
    conn.execute(sa.text("""
        INSERT INTO project_role_grants (
            project_id, user_id, role_id, scope_type,
            hospital_id, lab_unit_id, active, created_at, updated_at
        )
        SELECT project_profile.project_id, assignment.user_id, role.id, 'lab_unit',
               CAST(NULL AS INTEGER), assignment.lab_unit_id,
               BOOL_OR(assignment.active AND project_profile.active), now(), now()
        FROM project_upload_profile_assignments assignment
        JOIN project_upload_profiles project_profile
          ON project_profile.id = assignment.project_upload_profile_id
        JOIN roles role ON role.name = 'fileUploader'
        WHERE NOT EXISTS (
            SELECT 1 FROM project_role_grants grant_row
            WHERE grant_row.project_id = project_profile.project_id
              AND grant_row.user_id = assignment.user_id
              AND grant_row.role_id = role.id
              AND grant_row.scope_type = 'lab_unit'
              AND grant_row.lab_unit_id = assignment.lab_unit_id
        )
        GROUP BY project_profile.project_id, assignment.user_id, role.id, assignment.lab_unit_id
    """))


def _backfill_unambiguous_permissions(conn) -> None:
    if not _table_exists("project_encounter_set_permissions"):
        return
    conn.execute(sa.text("""
        WITH mapped AS (
            SELECT permission.project_id, permission.user_id, permission.lab_unit_id,
                   mapping.role_name, permission.active
            FROM project_encounter_set_permissions permission
            CROSS JOIN LATERAL (
                VALUES
                    ('fileUploader', permission.can_upload),
                    ('discrepancy_reviewer', permission.can_review_discrepancies),
                    ('data_exporter', permission.can_export_data),
                    ('analytics_viewer', permission.can_view_analytics),
                    ('dataset_creator', permission.can_create_datasets),
                    ('regrade_adjudicator', permission.can_adjudicate_regrades)
            ) AS mapping(role_name, enabled)
            WHERE mapping.enabled = TRUE
        )
        INSERT INTO project_role_grants (
            project_id, user_id, role_id, scope_type,
            hospital_id, lab_unit_id, active, created_at, updated_at
        )
        SELECT mapped.project_id, mapped.user_id, role.id, 'lab_unit',
               CAST(NULL AS INTEGER), mapped.lab_unit_id, mapped.active, now(), now()
        FROM mapped
        JOIN roles role ON role.name = mapped.role_name
        WHERE NOT EXISTS (
            SELECT 1 FROM project_role_grants grant_row
            WHERE grant_row.project_id = mapped.project_id
              AND grant_row.user_id = mapped.user_id
              AND grant_row.role_id = role.id
              AND grant_row.scope_type = 'lab_unit'
              AND grant_row.lab_unit_id = mapped.lab_unit_id
        )
    """))


def upgrade() -> None:
    conn = op.get_bind()
    _seed_roles(conn)
    if not _table_exists("project_role_grants"):
        op.create_table(
            "project_role_grants",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("role_id", sa.Integer(), nullable=False),
            sa.Column("scope_type", sa.String(length=16), nullable=False),
            sa.Column("hospital_id", sa.Integer(), nullable=True),
            sa.Column("lab_unit_id", sa.Integer(), nullable=True),
            sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "scope_type IN ('project','hospital','lab_unit')",
                name="ck_project_role_grants_scope_type",
            ),
            sa.CheckConstraint(
                "(scope_type = 'project' AND hospital_id IS NULL AND lab_unit_id IS NULL) OR "
                "(scope_type = 'hospital' AND hospital_id IS NOT NULL AND lab_unit_id IS NULL) OR "
                "(scope_type = 'lab_unit' AND hospital_id IS NULL AND lab_unit_id IS NOT NULL)",
                name="ck_project_role_grants_scope_target",
            ),
            sa.ForeignKeyConstraint(
                ["project_id"], ["projects.id"],
                name="fk_project_role_grants_project_id_projects", ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["user_id"], ["users.id"],
                name="fk_project_role_grants_user_id_users", ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["role_id"], ["roles.id"],
                name="fk_project_role_grants_role_id_roles", ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["hospital_id"], ["hospitals.id"],
                name="fk_project_role_grants_hospital_id_hospitals", ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["lab_unit_id"], ["lab_units.id"],
                name="fk_project_role_grants_lab_unit_id_lab_units", ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name="pk_project_role_grants"),
        )

    for name, columns in (
        ("ix_project_role_grants_active", ["active"]),
        ("ix_project_role_grants_hospital_id", ["hospital_id"]),
        ("ix_project_role_grants_lab_unit_id", ["lab_unit_id"]),
        ("ix_project_role_grants_project_id", ["project_id"]),
        ("ix_project_role_grants_role_id", ["role_id"]),
        ("ix_project_role_grants_user_id", ["user_id"]),
        ("ix_project_role_grants_lookup", ["user_id", "project_id", "role_id", "active"]),
    ):
        _create_index_if_missing(name, columns)
    _create_index_if_missing(
        "uq_project_role_grants_project_scope",
        ["project_id", "user_id", "role_id"],
        unique=True,
        where="scope_type = 'project'",
    )
    _create_index_if_missing(
        "uq_project_role_grants_hospital_scope",
        ["project_id", "user_id", "role_id", "hospital_id"],
        unique=True,
        where="scope_type = 'hospital'",
    )
    _create_index_if_missing(
        "uq_project_role_grants_lab_scope",
        ["project_id", "user_id", "role_id", "lab_unit_id"],
        unique=True,
        where="scope_type = 'lab_unit'",
    )
    _backfill_investigator_roles(conn)
    _backfill_uploaders(conn)
    _backfill_unambiguous_permissions(conn)


def downgrade() -> None:
    conn = op.get_bind()
    if _table_exists("project_role_grants"):
        op.drop_table("project_role_grants")
    if _table_exists("roles") and _table_exists("user_roles"):
        for role_name in ("project_pi", "site_pi"):
            conn.execute(
                sa.text(
                    "DELETE FROM roles WHERE name = :role_name AND NOT EXISTS ("
                    "SELECT 1 FROM user_roles WHERE role_id = roles.id)"
                ),
                {"role_name": role_name},
            )
