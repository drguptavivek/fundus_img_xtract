"""correct encounter set type v1 targets

Revision ID: a6d9e8f7c5b4
Revises: f5a4b3c2d1e0
Create Date: 2026-05-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a6d9e8f7c5b4"
down_revision: Union[str, Sequence[str], None] = "f5a4b3c2d1e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


EST_TABLE = "encounter_set_types"
IMAGE_SCHEMES_TABLE = "encounter_set_type_image_grading_schemes"


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


def _unique_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    return {constraint["name"] for constraint in inspect(conn).get_unique_constraints(table_name)}


def _create_index_if_missing(conn, name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    if table_name in _table_names(conn) and not op.get_context().dialect.has_index(conn, table_name, name):
        op.create_index(name, table_name, columns, unique=unique)


def _drop_index_if_exists(conn, name: str, table_name: str) -> None:
    if table_name in _table_names(conn) and op.get_context().dialect.has_index(conn, table_name, name):
        op.drop_index(name, table_name=table_name)


def upgrade() -> None:
    conn = op.get_bind()
    if EST_TABLE not in _table_names(conn):
        return

    columns = _column_names(conn, EST_TABLE)
    if "encounter_grading_scheme_id" not in columns:
        op.add_column(EST_TABLE, sa.Column("encounter_grading_scheme_id", sa.Integer(), nullable=True))
    if "asset_rules_json" not in columns:
        op.add_column(
            EST_TABLE,
            sa.Column(
                "asset_rules_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text(
                    """'{"allow_clinical_images": true, "min_clinical_images": null, "max_clinical_images": null, "allow_document_uploads": false, "allow_pdf_uploads": false, "allow_document_image_uploads": false, "max_documents": null, "max_pdfs": null, "max_document_images": null, "allow_report_uploads": false, "allow_report_pdfs": false, "allow_report_images": false, "max_reports": null}'::jsonb"""
                ),
            ),
        )

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

    if IMAGE_SCHEMES_TABLE not in _table_names(conn):
        op.create_table(
            IMAGE_SCHEMES_TABLE,
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
    _create_index_if_missing(conn, "ix_est_image_grading_scheme_type_active", IMAGE_SCHEMES_TABLE, ["encounter_set_type_id", "active"])
    _create_index_if_missing(conn, "ix_est_image_grading_scheme_default", IMAGE_SCHEMES_TABLE, ["encounter_set_type_id", "is_default"])
    _create_index_if_missing(conn, "ix_encounter_set_type_image_grading_schemes_disease_id", IMAGE_SCHEMES_TABLE, ["disease_id"])

    if "target_scheme_id" in _column_names(conn, EST_TABLE):
        if "fk_encounter_set_types_target_scheme_id_diseases" in _fk_names(conn, EST_TABLE):
            op.drop_constraint("fk_encounter_set_types_target_scheme_id_diseases", EST_TABLE, type_="foreignkey")
        _drop_index_if_exists(conn, "ix_encounter_set_types_target_scheme_id", EST_TABLE)
        op.drop_column(EST_TABLE, "target_scheme_id")


def downgrade() -> None:
    conn = op.get_bind()
    if EST_TABLE not in _table_names(conn):
        return

    if IMAGE_SCHEMES_TABLE in _table_names(conn):
        op.drop_table(IMAGE_SCHEMES_TABLE)

    columns = _column_names(conn, EST_TABLE)
    if "target_scheme_id" not in columns:
        op.add_column(EST_TABLE, sa.Column("target_scheme_id", sa.Integer(), nullable=True))
    if "fk_encounter_set_types_target_scheme_id_diseases" not in _fk_names(conn, EST_TABLE):
        op.create_foreign_key(
            "fk_encounter_set_types_target_scheme_id_diseases",
            EST_TABLE,
            "diseases",
            ["target_scheme_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    _create_index_if_missing(conn, "ix_encounter_set_types_target_scheme_id", EST_TABLE, ["target_scheme_id"])

    if "fk_encounter_set_types_encounter_grading_scheme_id_diseases" in _fk_names(conn, EST_TABLE):
        op.drop_constraint("fk_encounter_set_types_encounter_grading_scheme_id_diseases", EST_TABLE, type_="foreignkey")
    _drop_index_if_exists(conn, "ix_encounter_set_types_encounter_grading_scheme_id", EST_TABLE)
    if "asset_rules_json" in _column_names(conn, EST_TABLE):
        op.drop_column(EST_TABLE, "asset_rules_json")
    if "encounter_grading_scheme_id" in _column_names(conn, EST_TABLE):
        op.drop_column(EST_TABLE, "encounter_grading_scheme_id")
