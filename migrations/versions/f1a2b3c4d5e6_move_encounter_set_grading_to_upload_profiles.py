"""move encounter set grading to upload profiles

Revision ID: f1a2b3c4d5e6
Revises: e0f1a2b3c4d5
Create Date: 2026-05-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e0f1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


EST_TABLE = "encounter_set_types"
LEGACY_EST_IMAGE_SCHEMES_TABLE = "encounter_set_type_image_grading_schemes"
PROFILE_EST_TABLE = "upload_profile_encounter_set_types"
PROFILE_EST_IMAGE_SCHEMES_TABLE = "upload_profile_est_image_grading_schemes"


def _table_names(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _column_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    return {column["name"] for column in inspect(conn).get_columns(table_name)}


def _fk_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    return {fk["name"] for fk in inspect(conn).get_foreign_keys(table_name)}


def _create_index_if_missing(conn, name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    if table_name in _table_names(conn) and not op.get_context().dialect.has_index(conn, table_name, name):
        op.create_index(name, table_name, columns, unique=unique)


def _drop_index_if_exists(conn, name: str, table_name: str) -> None:
    if table_name in _table_names(conn) and op.get_context().dialect.has_index(conn, table_name, name):
        op.drop_index(name, table_name=table_name)


def _drop_fk_if_exists(conn, name: str, table_name: str) -> None:
    if table_name in _table_names(conn) and name in _fk_names(conn, table_name):
        op.drop_constraint(name, table_name, type_="foreignkey")


def upgrade() -> None:
    conn = op.get_bind()
    tables = _table_names(conn)

    if PROFILE_EST_TABLE in tables:
        columns = _column_names(conn, PROFILE_EST_TABLE)
        if "encounter_grading_scheme_id" not in columns:
            op.add_column(PROFILE_EST_TABLE, sa.Column("encounter_grading_scheme_id", sa.Integer(), nullable=True))
        if "default_image_grading_scheme_id" not in columns:
            op.add_column(PROFILE_EST_TABLE, sa.Column("default_image_grading_scheme_id", sa.Integer(), nullable=True))
        if "updated_at" not in columns:
            op.add_column(
                PROFILE_EST_TABLE,
                sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            )

        fks = _fk_names(conn, PROFILE_EST_TABLE)
        if "fk_upload_profile_est_encounter_grading_scheme_id_diseases" not in fks:
            op.create_foreign_key(
                "fk_upload_profile_est_encounter_grading_scheme_id_diseases",
                PROFILE_EST_TABLE,
                "diseases",
                ["encounter_grading_scheme_id"],
                ["id"],
                ondelete="RESTRICT",
            )
        if "fk_upload_profile_est_default_image_grading_scheme_id_diseases" not in fks:
            op.create_foreign_key(
                "fk_upload_profile_est_default_image_grading_scheme_id_diseases",
                PROFILE_EST_TABLE,
                "diseases",
                ["default_image_grading_scheme_id"],
                ["id"],
                ondelete="RESTRICT",
            )
        _create_index_if_missing(conn, "ix_upload_profile_est_encounter_grading_scheme_id", PROFILE_EST_TABLE, ["encounter_grading_scheme_id"])
        _create_index_if_missing(conn, "ix_upload_profile_est_default_image_grading_scheme_id", PROFILE_EST_TABLE, ["default_image_grading_scheme_id"])

    if PROFILE_EST_IMAGE_SCHEMES_TABLE not in tables:
        op.create_table(
            PROFILE_EST_IMAGE_SCHEMES_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("upload_profile_encounter_set_type_id", sa.Integer(), nullable=False),
            sa.Column("disease_id", sa.Integer(), nullable=False),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(
                ["upload_profile_encounter_set_type_id"],
                [f"{PROFILE_EST_TABLE}.id"],
                name="fk_up_est_img_scheme_profile_est",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(["disease_id"], ["diseases.id"], name="fk_up_est_img_scheme_disease", ondelete="RESTRICT"),
            sa.UniqueConstraint("upload_profile_encounter_set_type_id", "disease_id", name="uq_up_est_image_grading_scheme"),
        )
    _create_index_if_missing(
        conn,
        "ix_up_est_img_scheme_mapping_active",
        PROFILE_EST_IMAGE_SCHEMES_TABLE,
        ["upload_profile_encounter_set_type_id", "active"],
    )
    _create_index_if_missing(
        conn,
        "ix_up_est_img_scheme_default",
        PROFILE_EST_IMAGE_SCHEMES_TABLE,
        ["upload_profile_encounter_set_type_id", "is_default"],
    )
    _create_index_if_missing(conn, "ix_upload_profile_est_image_grading_schemes_disease_id", PROFILE_EST_IMAGE_SCHEMES_TABLE, ["disease_id"])

    if LEGACY_EST_IMAGE_SCHEMES_TABLE in _table_names(conn):
        op.drop_table(LEGACY_EST_IMAGE_SCHEMES_TABLE)

    if EST_TABLE in _table_names(conn):
        _drop_fk_if_exists(conn, "fk_encounter_set_types_encounter_grading_scheme_id_diseases", EST_TABLE)
        _drop_index_if_exists(conn, "ix_encounter_set_types_encounter_grading_scheme_id", EST_TABLE)
        if "encounter_grading_scheme_id" in _column_names(conn, EST_TABLE):
            op.drop_column(EST_TABLE, "encounter_grading_scheme_id")


def downgrade() -> None:
    conn = op.get_bind()

    if EST_TABLE in _table_names(conn):
        if "encounter_grading_scheme_id" not in _column_names(conn, EST_TABLE):
            op.add_column(EST_TABLE, sa.Column("encounter_grading_scheme_id", sa.Integer(), nullable=True))
        if "fk_encounter_set_types_encounter_grading_scheme_id_diseases" not in _fk_names(conn, EST_TABLE):
            op.create_foreign_key(
                "fk_encounter_set_types_encounter_grading_scheme_id_diseases",
                EST_TABLE,
                "diseases",
                ["encounter_grading_scheme_id"],
                ["id"],
                ondelete="RESTRICT",
            )
        _create_index_if_missing(conn, "ix_encounter_set_types_encounter_grading_scheme_id", EST_TABLE, ["encounter_grading_scheme_id"])

    if LEGACY_EST_IMAGE_SCHEMES_TABLE not in _table_names(conn):
        op.create_table(
            LEGACY_EST_IMAGE_SCHEMES_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("encounter_set_type_id", sa.Integer(), nullable=False),
            sa.Column("disease_id", sa.Integer(), nullable=False),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["encounter_set_type_id"], [f"{EST_TABLE}.id"], name="fk_est_image_scheme_type", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["disease_id"], ["diseases.id"], name="fk_est_image_scheme_disease", ondelete="RESTRICT"),
            sa.UniqueConstraint("encounter_set_type_id", "disease_id", name="uq_est_image_grading_scheme"),
        )
    _create_index_if_missing(conn, "ix_est_image_grading_scheme_type_active", LEGACY_EST_IMAGE_SCHEMES_TABLE, ["encounter_set_type_id", "active"])
    _create_index_if_missing(conn, "ix_est_image_grading_scheme_default", LEGACY_EST_IMAGE_SCHEMES_TABLE, ["encounter_set_type_id", "is_default"])

    if PROFILE_EST_IMAGE_SCHEMES_TABLE in _table_names(conn):
        op.drop_table(PROFILE_EST_IMAGE_SCHEMES_TABLE)

    if PROFILE_EST_TABLE in _table_names(conn):
        _drop_fk_if_exists(conn, "fk_upload_profile_est_default_image_grading_scheme_id_diseases", PROFILE_EST_TABLE)
        _drop_fk_if_exists(conn, "fk_upload_profile_est_encounter_grading_scheme_id_diseases", PROFILE_EST_TABLE)
        _drop_index_if_exists(conn, "ix_upload_profile_est_default_image_grading_scheme_id", PROFILE_EST_TABLE)
        _drop_index_if_exists(conn, "ix_upload_profile_est_encounter_grading_scheme_id", PROFILE_EST_TABLE)
        columns = _column_names(conn, PROFILE_EST_TABLE)
        for column_name in ("updated_at", "default_image_grading_scheme_id", "encounter_grading_scheme_id"):
            if column_name in columns:
                op.drop_column(PROFILE_EST_TABLE, column_name)
