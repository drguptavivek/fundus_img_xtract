"""add encounter file camera and zip enabled cameras

Revision ID: b3d4e5f6a7b8
Revises: a4c1d9e7b2f3
Create Date: 2026-04-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


# revision identifiers, used by Alembic.
revision: str = "b3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "a4c1d9e7b2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(conn, table_name: str) -> set[str]:
    inspector = inspect(conn)
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    conn = op.get_bind()
    columns = _column_names(conn, "cameras")
    if "is_zip_upload_enabled" not in columns:
        op.add_column(
            "cameras",
            sa.Column(
                "is_zip_upload_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )

    columns = _column_names(conn, "encounter_files")
    if "camera_id" not in columns:
        op.add_column(
            "encounter_files",
            sa.Column("camera_id", sa.Integer(), nullable=True),
        )

    if not op.get_context().dialect.has_index(conn, "cameras", "ix_cameras_is_zip_upload_enabled"):
        op.create_index("ix_cameras_is_zip_upload_enabled", "cameras", ["is_zip_upload_enabled"], unique=False)

    if "camera_id" in _column_names(conn, "encounter_files"):
        fk_names = {fk["name"] for fk in inspect(conn).get_foreign_keys("encounter_files")}
        if "fk_encounter_files_camera_id_cameras" not in fk_names:
            op.create_foreign_key(
                "fk_encounter_files_camera_id_cameras",
                "encounter_files",
                "cameras",
                ["camera_id"],
                ["id"],
            )
    if not op.get_context().dialect.has_index(conn, "encounter_files", "ix_encounter_files_camera_id"):
        op.create_index("ix_encounter_files_camera_id", "encounter_files", ["camera_id"], unique=False)

    op.execute(
        text(
            """
            INSERT INTO cameras (name, is_zip_upload_enabled)
            SELECT 'Remedio Pristine', TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM cameras WHERE lower(name) = lower('Remedio Pristine')
            )
            """
        )
    )
    op.execute(
        text(
            """
            UPDATE cameras
            SET is_zip_upload_enabled = TRUE
            WHERE lower(name) IN (lower('Remedio FOP'), lower('Remedio Pristine'))
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()

    op.execute(
        text(
            """
            UPDATE cameras
            SET is_zip_upload_enabled = FALSE
            WHERE lower(name) IN (lower('Remedio FOP'), lower('Remedio Pristine'))
            """
        )
    )
    op.execute(
        text(
            """
            DELETE FROM cameras
            WHERE lower(name) = lower('Remedio Pristine')
            """
        )
    )

    if op.get_context().dialect.has_index(conn, "encounter_files", "ix_encounter_files_camera_id"):
        op.drop_index("ix_encounter_files_camera_id", table_name="encounter_files")

    fk_names = {fk["name"] for fk in inspect(conn).get_foreign_keys("encounter_files")}
    if "fk_encounter_files_camera_id_cameras" in fk_names:
        op.drop_constraint("fk_encounter_files_camera_id_cameras", "encounter_files", type_="foreignkey")

    if "camera_id" in _column_names(conn, "encounter_files"):
        op.drop_column("encounter_files", "camera_id")

    if op.get_context().dialect.has_index(conn, "cameras", "ix_cameras_is_zip_upload_enabled"):
        op.drop_index("ix_cameras_is_zip_upload_enabled", table_name="cameras")

    if "is_zip_upload_enabled" in _column_names(conn, "cameras"):
        op.drop_column("cameras", "is_zip_upload_enabled")
