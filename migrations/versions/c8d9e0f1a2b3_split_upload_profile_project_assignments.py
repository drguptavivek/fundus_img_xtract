"""split upload profile project and lab assignments

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-05-23 07:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


# revision identifiers, used by Alembic.
revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, Sequence[str], None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _column_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    return {column["name"] for column in inspect(conn).get_columns(table_name)}


def _index_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    return {index["name"] for index in inspect(conn).get_indexes(table_name)}


def _fk_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    return {fk["name"] for fk in inspect(conn).get_foreign_keys(table_name) if fk.get("name")}


def _unique_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    return {constraint["name"] for constraint in inspect(conn).get_unique_constraints(table_name) if constraint.get("name")}


def _check_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    return {constraint["name"] for constraint in inspect(conn).get_check_constraints(table_name) if constraint.get("name")}


def _create_index_if_missing(conn, index_name: str, table_name: str, columns: list[str]) -> None:
    if index_name not in _index_names(conn, table_name):
        op.create_index(index_name, table_name, columns)


def _drop_index_if_exists(conn, index_name: str, table_name: str) -> None:
    if index_name in _index_names(conn, table_name):
        op.drop_index(index_name, table_name=table_name)


def _drop_constraint_if_exists(conn, table_name: str, constraint_name: str, constraint_type: str) -> None:
    known: set[str]
    if constraint_type == "foreignkey":
        known = _fk_names(conn, table_name)
    elif constraint_type == "unique":
        known = _unique_names(conn, table_name)
    elif constraint_type == "check":
        known = _check_names(conn, table_name)
    else:
        known = set()
    if constraint_name in known:
        op.drop_constraint(constraint_name, table_name, type_=constraint_type)


def _create_project_profile_tables(conn) -> None:
    if "project_upload_profiles" not in _table_names(conn):
        op.create_table(
            "project_upload_profiles",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("upload_profile_id", sa.Integer(), nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_project_upload_profiles_project", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["upload_profile_id"], ["upload_profiles.id"], name="fk_project_upload_profiles_profile", ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("project_id", "upload_profile_id", name="uq_project_upload_profile"),
        )
    _create_index_if_missing(conn, "ix_project_upload_profiles_project_id", "project_upload_profiles", ["project_id"])
    _create_index_if_missing(conn, "ix_project_upload_profiles_upload_profile_id", "project_upload_profiles", ["upload_profile_id"])
    _create_index_if_missing(conn, "ix_project_upload_profiles_active", "project_upload_profiles", ["active"])
    _create_index_if_missing(conn, "ix_project_upload_profiles_project_active", "project_upload_profiles", ["project_id", "active"])
    _create_index_if_missing(conn, "ix_project_upload_profiles_profile_active", "project_upload_profiles", ["upload_profile_id", "active"])

    if "project_upload_profile_assignments" not in _table_names(conn):
        op.create_table(
            "project_upload_profile_assignments",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_upload_profile_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("lab_unit_id", sa.Integer(), nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(
                ["project_upload_profile_id"],
                ["project_upload_profiles.id"],
                name="fk_project_upload_profile_assignments_mapping",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_project_upload_profile_assignments_user", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["lab_unit_id"], ["lab_units.id"], name="fk_project_upload_profile_assignments_lab", ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("project_upload_profile_id", "user_id", "lab_unit_id", name="uq_project_upload_profile_assignment"),
        )
    _create_index_if_missing(conn, "ix_project_upload_profile_assignments_project_upload_profile_id", "project_upload_profile_assignments", ["project_upload_profile_id"])
    _create_index_if_missing(conn, "ix_project_upload_profile_assignments_user_id", "project_upload_profile_assignments", ["user_id"])
    _create_index_if_missing(conn, "ix_project_upload_profile_assignments_lab_unit_id", "project_upload_profile_assignments", ["lab_unit_id"])
    _create_index_if_missing(conn, "ix_project_upload_profile_assignments_active", "project_upload_profile_assignments", ["active"])
    _create_index_if_missing(conn, "ix_project_upload_profile_assignments_user_active", "project_upload_profile_assignments", ["user_id", "active"])
    _create_index_if_missing(conn, "ix_project_upload_profile_assignments_lab_active", "project_upload_profile_assignments", ["lab_unit_id", "active"])


def _backfill_project_profile_tables(conn) -> None:
    tables = _table_names(conn)
    columns = _column_names(conn, "upload_profiles")
    if "upload_profiles" not in tables or "project_id" not in columns:
        return
    conn.execute(
        text(
            """
            INSERT INTO project_upload_profiles (project_id, upload_profile_id, active, created_at, updated_at)
            SELECT up.project_id, up.id, up.active, now(), now()
            FROM upload_profiles up
            JOIN projects p ON p.id = up.project_id
            WHERE up.project_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM project_upload_profiles pup
                  WHERE pup.project_id = up.project_id
                    AND pup.upload_profile_id = up.id
              )
            """
        )
    )

    if "upload_profile_assignments" not in tables or "lab_unit_id" not in columns:
        return
    conn.execute(
        text(
            """
            INSERT INTO project_upload_profile_assignments
                (project_upload_profile_id, user_id, lab_unit_id, active, created_at, updated_at)
            SELECT
                pup.id,
                upa.user_id,
                up.lab_unit_id,
                (
                    upa.active IS TRUE
                    AND up.active IS TRUE
                    AND users.is_active IS TRUE
                    AND ulu.user_id IS NOT NULL
                    AND users.hospital_id = lab_units.hospital_id
                ) AS active,
                now(),
                now()
            FROM upload_profile_assignments upa
            JOIN upload_profiles up ON up.id = upa.upload_profile_id
            JOIN project_upload_profiles pup
              ON pup.project_id = up.project_id
             AND pup.upload_profile_id = up.id
            JOIN users ON users.id = upa.user_id
            JOIN lab_units ON lab_units.id = up.lab_unit_id
            LEFT JOIN user_lab_units ulu
              ON ulu.user_id = upa.user_id
             AND ulu.lab_unit_id = up.lab_unit_id
            WHERE up.lab_unit_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM project_upload_profile_assignments existing
                  WHERE existing.project_upload_profile_id = pup.id
                    AND existing.user_id = upa.user_id
                    AND existing.lab_unit_id = up.lab_unit_id
              )
            """
        )
    )


def upgrade() -> None:
    conn = op.get_bind()
    if "upload_profiles" not in _table_names(conn):
        return

    _create_project_profile_tables(conn)
    _backfill_project_profile_tables(conn)

    if "upload_profile_assignments" in _table_names(conn):
        op.drop_table("upload_profile_assignments")

    _drop_constraint_if_exists(conn, "upload_profiles", "uq_upload_profile_lab_project_name", "unique")
    _drop_constraint_if_exists(conn, "upload_profiles", "fk_upload_profiles_lab_unit_id_lab_units", "foreignkey")
    _drop_constraint_if_exists(conn, "upload_profiles", "fk_upload_profiles_project_id_projects", "foreignkey")
    _drop_index_if_exists(conn, "ix_upload_profiles_lab_project_active", "upload_profiles")
    _drop_index_if_exists(conn, "ix_upload_profiles_lab_unit_id", "upload_profiles")
    _drop_index_if_exists(conn, "ix_upload_profiles_project_id", "upload_profiles")

    columns = _column_names(conn, "upload_profiles")
    if "lab_unit_id" in columns:
        op.drop_column("upload_profiles", "lab_unit_id")
    columns = _column_names(conn, "upload_profiles")
    if "project_id" in columns:
        op.drop_column("upload_profiles", "project_id")

    _create_index_if_missing(conn, "ix_upload_profiles_active_name", "upload_profiles", ["active", "name"])


def downgrade() -> None:
    conn = op.get_bind()
    if "upload_profiles" not in _table_names(conn):
        return

    columns = _column_names(conn, "upload_profiles")
    if "project_id" not in columns:
        op.add_column("upload_profiles", sa.Column("project_id", sa.Integer(), nullable=True))
    columns = _column_names(conn, "upload_profiles")
    if "lab_unit_id" not in columns:
        op.add_column("upload_profiles", sa.Column("lab_unit_id", sa.Integer(), nullable=True))

    if "project_upload_profiles" in _table_names(conn):
        conn.execute(
            text(
                """
                UPDATE upload_profiles up
                SET project_id = selected.project_id
                FROM (
                    SELECT DISTINCT ON (upload_profile_id)
                        upload_profile_id,
                        project_id
                    FROM project_upload_profiles
                    ORDER BY upload_profile_id, active DESC, id ASC
                ) selected
                WHERE selected.upload_profile_id = up.id
                  AND up.project_id IS NULL
                """
            )
        )

    if "project_upload_profile_assignments" in _table_names(conn):
        conn.execute(
            text(
                """
                UPDATE upload_profiles up
                SET lab_unit_id = selected.lab_unit_id
                FROM (
                    SELECT DISTINCT ON (pup.upload_profile_id)
                        pup.upload_profile_id,
                        pupa.lab_unit_id
                    FROM project_upload_profile_assignments pupa
                    JOIN project_upload_profiles pup ON pup.id = pupa.project_upload_profile_id
                    ORDER BY pup.upload_profile_id, pupa.active DESC, pupa.id ASC
                ) selected
                WHERE selected.upload_profile_id = up.id
                  AND up.lab_unit_id IS NULL
                """
            )
        )

    _create_index_if_missing(conn, "ix_upload_profiles_project_id", "upload_profiles", ["project_id"])
    _create_index_if_missing(conn, "ix_upload_profiles_lab_unit_id", "upload_profiles", ["lab_unit_id"])
    _create_index_if_missing(conn, "ix_upload_profiles_lab_project_active", "upload_profiles", ["lab_unit_id", "project_id", "active"])
    if "fk_upload_profiles_project_id_projects" not in _fk_names(conn, "upload_profiles"):
        op.create_foreign_key(
            "fk_upload_profiles_project_id_projects",
            "upload_profiles",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="CASCADE",
        )
    if "fk_upload_profiles_lab_unit_id_lab_units" not in _fk_names(conn, "upload_profiles"):
        op.create_foreign_key(
            "fk_upload_profiles_lab_unit_id_lab_units",
            "upload_profiles",
            "lab_units",
            ["lab_unit_id"],
            ["id"],
            ondelete="CASCADE",
        )
    if "uq_upload_profile_lab_project_name" not in _unique_names(conn, "upload_profiles"):
        op.create_unique_constraint("uq_upload_profile_lab_project_name", "upload_profiles", ["lab_unit_id", "project_id", "name"])

    if "upload_profile_assignments" not in _table_names(conn):
        op.create_table(
            "upload_profile_assignments",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("upload_profile_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["upload_profile_id"], ["upload_profiles.id"], name="fk_upload_profile_assignments_profile", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_upload_profile_assignments_user", ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("upload_profile_id", "user_id", name="uq_upload_profile_assignment_user"),
        )
    _create_index_if_missing(conn, "ix_upload_profile_assignments_upload_profile_id", "upload_profile_assignments", ["upload_profile_id"])
    _create_index_if_missing(conn, "ix_upload_profile_assignments_user_id", "upload_profile_assignments", ["user_id"])
    _create_index_if_missing(conn, "ix_upload_profile_assignments_active", "upload_profile_assignments", ["active"])
    _create_index_if_missing(conn, "ix_upload_profile_assignments_user_active", "upload_profile_assignments", ["user_id", "active"])

    if "project_upload_profiles" in _table_names(conn) and "project_upload_profile_assignments" in _table_names(conn):
        conn.execute(
            text(
                """
                INSERT INTO upload_profile_assignments (upload_profile_id, user_id, active, created_at, updated_at)
                SELECT DISTINCT ON (pup.upload_profile_id, pupa.user_id)
                    pup.upload_profile_id,
                    pupa.user_id,
                    bool_or(pupa.active) OVER (PARTITION BY pup.upload_profile_id, pupa.user_id),
                    now(),
                    now()
                FROM project_upload_profile_assignments pupa
                JOIN project_upload_profiles pup ON pup.id = pupa.project_upload_profile_id
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM upload_profile_assignments existing
                    WHERE existing.upload_profile_id = pup.upload_profile_id
                      AND existing.user_id = pupa.user_id
                )
                ORDER BY pup.upload_profile_id, pupa.user_id, pupa.active DESC, pupa.id ASC
                """
            )
        )

    if "project_upload_profile_assignments" in _table_names(conn):
        op.drop_table("project_upload_profile_assignments")
    if "project_upload_profiles" in _table_names(conn):
        op.drop_table("project_upload_profiles")

    _drop_index_if_exists(conn, "ix_upload_profiles_active_name", "upload_profiles")
