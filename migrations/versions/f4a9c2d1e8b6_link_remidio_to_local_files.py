"""link remidio to local files

Revision ID: f4a9c2d1e8b6
Revises: d2a6b3c4e5f7
Create Date: 2026-04-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "f4a9c2d1e8b6"
down_revision: Union[str, Sequence[str], None] = "d2a6b3c4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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

    if "patient_encounter_id" not in _column_names(conn, "remidio_exams"):
        op.add_column("remidio_exams", sa.Column("patient_encounter_id", sa.Integer(), nullable=True))
    if "fk_remidio_exams_patient_encounter_id" not in _fk_names(conn, "remidio_exams"):
        op.create_foreign_key(
            "fk_remidio_exams_patient_encounter_id",
            "remidio_exams",
            "patient_encounters",
            ["patient_encounter_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "uq_remidio_exam_patient_encounter_id" not in _unique_names(conn, "remidio_exams"):
        op.create_unique_constraint("uq_remidio_exam_patient_encounter_id", "remidio_exams", ["patient_encounter_id"])
    _create_index_if_missing(conn, "ix_remidio_exams_patient_encounter_id", "remidio_exams", ["patient_encounter_id"])

    if "encounter_file_id" not in _column_names(conn, "remidio_images"):
        op.add_column("remidio_images", sa.Column("encounter_file_id", sa.Integer(), nullable=True))
    if "downloaded_at" not in _column_names(conn, "remidio_images"):
        op.add_column("remidio_images", sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True))
    if "download_error" not in _column_names(conn, "remidio_images"):
        op.add_column("remidio_images", sa.Column("download_error", sa.Text(), nullable=True))
    if "fk_remidio_images_encounter_file_id" not in _fk_names(conn, "remidio_images"):
        op.create_foreign_key(
            "fk_remidio_images_encounter_file_id",
            "remidio_images",
            "encounter_files",
            ["encounter_file_id"],
            ["id"],
            ondelete="SET NULL",
        )
    _create_index_if_missing(conn, "ix_remidio_images_encounter_file_id", "remidio_images", ["encounter_file_id"])

    if "encounter_file_pdf_id" not in _column_names(conn, "remidio_reports"):
        op.add_column("remidio_reports", sa.Column("encounter_file_pdf_id", sa.Integer(), nullable=True))
    if "downloaded_at" not in _column_names(conn, "remidio_reports"):
        op.add_column("remidio_reports", sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True))
    if "download_error" not in _column_names(conn, "remidio_reports"):
        op.add_column("remidio_reports", sa.Column("download_error", sa.Text(), nullable=True))
    if "fk_remidio_reports_encounter_file_pdf_id" not in _fk_names(conn, "remidio_reports"):
        op.create_foreign_key(
            "fk_remidio_reports_encounter_file_pdf_id",
            "remidio_reports",
            "encounter_file_pdfs",
            ["encounter_file_pdf_id"],
            ["id"],
            ondelete="SET NULL",
        )
    _create_index_if_missing(conn, "ix_remidio_reports_encounter_file_pdf_id", "remidio_reports", ["encounter_file_pdf_id"])


def downgrade() -> None:
    conn = op.get_bind()

    _drop_index_if_exists(conn, "ix_remidio_reports_encounter_file_pdf_id", "remidio_reports")
    if "fk_remidio_reports_encounter_file_pdf_id" in _fk_names(conn, "remidio_reports"):
        op.drop_constraint("fk_remidio_reports_encounter_file_pdf_id", "remidio_reports", type_="foreignkey")
    for column_name in ("download_error", "downloaded_at", "encounter_file_pdf_id"):
        if column_name in _column_names(conn, "remidio_reports"):
            op.drop_column("remidio_reports", column_name)

    _drop_index_if_exists(conn, "ix_remidio_images_encounter_file_id", "remidio_images")
    if "fk_remidio_images_encounter_file_id" in _fk_names(conn, "remidio_images"):
        op.drop_constraint("fk_remidio_images_encounter_file_id", "remidio_images", type_="foreignkey")
    for column_name in ("download_error", "downloaded_at", "encounter_file_id"):
        if column_name in _column_names(conn, "remidio_images"):
            op.drop_column("remidio_images", column_name)

    _drop_index_if_exists(conn, "ix_remidio_exams_patient_encounter_id", "remidio_exams")
    if "uq_remidio_exam_patient_encounter_id" in _unique_names(conn, "remidio_exams"):
        op.drop_constraint("uq_remidio_exam_patient_encounter_id", "remidio_exams", type_="unique")
    if "fk_remidio_exams_patient_encounter_id" in _fk_names(conn, "remidio_exams"):
        op.drop_constraint("fk_remidio_exams_patient_encounter_id", "remidio_exams", type_="foreignkey")
    if "patient_encounter_id" in _column_names(conn, "remidio_exams"):
        op.drop_column("remidio_exams", "patient_encounter_id")
