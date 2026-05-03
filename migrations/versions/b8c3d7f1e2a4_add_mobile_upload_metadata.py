"""Add mobile upload metadata

Revision ID: b8c3d7f1e2a4
Revises: a6d4c9e8b1f0
Create Date: 2026-05-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8c3d7f1e2a4"
down_revision: Union[str, Sequence[str], None] = "a6d4c9e8b1f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _add_column_if_missing(inspector, "direct_image_uploads", sa.Column("remarks", sa.Text(), nullable=True))
    _add_column_if_missing(inspector, "patient_encounters", sa.Column("remarks", sa.Text(), nullable=True))
    _add_column_if_missing(inspector, "encounter_set_images", sa.Column("remarks", sa.Text(), nullable=True))

    _add_column_if_missing(inspector, "jobs", sa.Column("upload_kind", sa.String(length=32), nullable=True))
    _add_column_if_missing(inspector, "jobs", sa.Column("upload_profile_id", sa.Integer(), nullable=True))
    _create_fk_if_missing(inspector, "jobs", "fk_jobs_upload_profile_id", "upload_profiles", ["upload_profile_id"], ["id"], ondelete="SET NULL")
    _create_index_if_missing(inspector, "jobs", "ix_jobs_upload_kind", ["upload_kind"])
    _create_index_if_missing(inspector, "jobs", "ix_jobs_upload_profile_id", ["upload_profile_id"])

    _add_column_if_missing(inspector, "job_items", sa.Column("source_type", sa.String(length=32), nullable=True))
    _add_column_if_missing(inspector, "job_items", sa.Column("source_id", sa.Integer(), nullable=True))
    _add_column_if_missing(inspector, "job_items", sa.Column("source_uuid", sa.String(length=36), nullable=True))
    _add_column_if_missing(inspector, "job_items", sa.Column("task_id", sa.Integer(), nullable=True))
    _create_index_if_missing(inspector, "job_items", "ix_job_items_source_type", ["source_type"])
    _create_index_if_missing(inspector, "job_items", "ix_job_items_source_id", ["source_id"])
    _create_index_if_missing(inspector, "job_items", "ix_job_items_source_uuid", ["source_uuid"])
    _create_index_if_missing(inspector, "job_items", "ix_job_items_task_id", ["task_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _drop_index_if_exists(inspector, "job_items", "ix_job_items_task_id")
    _drop_index_if_exists(inspector, "job_items", "ix_job_items_source_uuid")
    _drop_index_if_exists(inspector, "job_items", "ix_job_items_source_id")
    _drop_index_if_exists(inspector, "job_items", "ix_job_items_source_type")
    _drop_column_if_exists(inspector, "job_items", "task_id")
    _drop_column_if_exists(inspector, "job_items", "source_uuid")
    _drop_column_if_exists(inspector, "job_items", "source_id")
    _drop_column_if_exists(inspector, "job_items", "source_type")

    _drop_index_if_exists(inspector, "jobs", "ix_jobs_upload_profile_id")
    _drop_index_if_exists(inspector, "jobs", "ix_jobs_upload_kind")
    _drop_fk_if_exists(inspector, "jobs", "fk_jobs_upload_profile_id")
    _drop_column_if_exists(inspector, "jobs", "upload_profile_id")
    _drop_column_if_exists(inspector, "jobs", "upload_kind")

    _drop_column_if_exists(inspector, "encounter_set_images", "remarks")
    _drop_column_if_exists(inspector, "patient_encounters", "remarks")
    _drop_column_if_exists(inspector, "direct_image_uploads", "remarks")


def _columns(inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _add_column_if_missing(inspector, table_name: str, column: sa.Column) -> None:
    if column.name not in _columns(inspector, table_name):
        op.add_column(table_name, column)


def _drop_column_if_exists(inspector, table_name: str, column_name: str) -> None:
    if column_name in _columns(inspector, table_name):
        op.drop_column(table_name, column_name)


def _create_index_if_missing(inspector, table_name: str, index_name: str, columns: list[str]) -> None:
    if index_name not in {index["name"] for index in inspector.get_indexes(table_name)}:
        op.create_index(index_name, table_name, columns)


def _drop_index_if_exists(inspector, table_name: str, index_name: str) -> None:
    if index_name in {index["name"] for index in inspector.get_indexes(table_name)}:
        op.drop_index(index_name, table_name=table_name)


def _create_fk_if_missing(
    inspector,
    table_name: str,
    constraint_name: str,
    referent_table: str,
    local_cols: list[str],
    remote_cols: list[str],
    *,
    ondelete: str | None = None,
) -> None:
    if constraint_name not in {constraint["name"] for constraint in inspector.get_foreign_keys(table_name)}:
        op.create_foreign_key(constraint_name, table_name, referent_table, local_cols, remote_cols, ondelete=ondelete)


def _drop_fk_if_exists(inspector, table_name: str, constraint_name: str) -> None:
    if constraint_name in {constraint["name"] for constraint in inspector.get_foreign_keys(table_name)}:
        op.drop_constraint(constraint_name, table_name, type_="foreignkey")
