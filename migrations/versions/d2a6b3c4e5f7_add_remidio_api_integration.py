"""add remidio api integration

Revision ID: d2a6b3c4e5f7
Revises: c4e8a9f2d1b0
Create Date: 2026-04-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d2a6b3c4e5f7"
down_revision: Union[str, Sequence[str], None] = "c4e8a9f2d1b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _create_index_if_missing(conn, name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    if table_name in _table_names(conn) and not op.get_context().dialect.has_index(conn, table_name, name):
        op.create_index(name, table_name, columns, unique=unique)


def _drop_index_if_exists(conn, name: str, table_name: str) -> None:
    if table_name in _table_names(conn) and op.get_context().dialect.has_index(conn, table_name, name):
        op.drop_index(name, table_name=table_name)


def upgrade() -> None:
    conn = op.get_bind()
    tables = _table_names(conn)

    if "remidio_connections" not in tables:
        op.create_table(
            "remidio_connections",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=True),
            sa.Column("base_url", sa.String(length=500), nullable=False),
            sa.Column("client_name", sa.String(length=100), nullable=False),
            sa.Column("client_identification_token_encrypted", sa.Text(), nullable=False),
            sa.Column("email_encrypted", sa.Text(), nullable=False),
            sa.Column("password_encrypted", sa.Text(), nullable=False),
            sa.Column("secret_salt", sa.String(length=64), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_auth_token_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_remidio_connections_project_id_projects", ondelete="RESTRICT"),
            sa.UniqueConstraint("name", name="uq_remidio_connections_name"),
        )
    _create_index_if_missing(conn, "ix_remidio_connections_project_id", "remidio_connections", ["project_id"])
    _create_index_if_missing(conn, "ix_remidio_connections_active", "remidio_connections", ["active"])
    _create_index_if_missing(conn, "ix_remidio_connections_project_active", "remidio_connections", ["project_id", "active"])

    if "remidio_sites" not in _table_names(conn):
        op.create_table(
            "remidio_sites",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("remidio_connection_id", sa.Integer(), nullable=False),
            sa.Column("remidio_site_id", sa.String(length=64), nullable=False),
            sa.Column("site_name", sa.String(length=255), nullable=True),
            sa.Column("site_domain", sa.String(length=255), nullable=True),
            sa.Column("site_custom_identifier", sa.String(length=255), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["remidio_connection_id"], ["remidio_connections.id"], name="fk_remidio_sites_connection_id", ondelete="CASCADE"),
            sa.UniqueConstraint("remidio_connection_id", "remidio_site_id", name="uq_remidio_site_connection_site_id"),
            sa.UniqueConstraint("remidio_connection_id", "site_custom_identifier", name="uq_remidio_site_connection_custom_identifier"),
        )
    _create_index_if_missing(conn, "ix_remidio_sites_remidio_connection_id", "remidio_sites", ["remidio_connection_id"])
    _create_index_if_missing(conn, "ix_remidio_sites_site_custom_identifier", "remidio_sites", ["site_custom_identifier"])
    _create_index_if_missing(conn, "ix_remidio_sites_active", "remidio_sites", ["active"])
    _create_index_if_missing(conn, "ix_remidio_sites_connection_active", "remidio_sites", ["remidio_connection_id", "active"])

    if "remidio_routing_rules" not in _table_names(conn):
        op.create_table(
            "remidio_routing_rules",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("remidio_connection_id", sa.Integer(), nullable=False),
            sa.Column("remidio_site_id", sa.Integer(), nullable=True),
            sa.Column("site_custom_identifier", sa.String(length=255), nullable=False),
            sa.Column("remidio_device_type", sa.String(length=64), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("lab_unit_id", sa.Integer(), nullable=False),
            sa.Column("camera_id", sa.Integer(), nullable=False),
            sa.Column("default_disease_id", sa.Integer(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["remidio_connection_id"], ["remidio_connections.id"], name="fk_remidio_routing_connection_id", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["remidio_site_id"], ["remidio_sites.id"], name="fk_remidio_routing_site_id", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_remidio_routing_project_id_projects", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["lab_unit_id"], ["lab_units.id"], name="fk_remidio_routing_lab_unit_id_lab_units", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], name="fk_remidio_routing_camera_id_cameras", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["default_disease_id"], ["diseases.id"], name="fk_remidio_routing_default_disease_id_diseases", ondelete="RESTRICT"),
            sa.UniqueConstraint(
                "remidio_connection_id",
                "site_custom_identifier",
                "remidio_device_type",
                "project_id",
                "lab_unit_id",
                "camera_id",
                name="uq_remidio_routing_rule_target",
            ),
        )
    for column_name in (
        "remidio_connection_id",
        "remidio_site_id",
        "project_id",
        "lab_unit_id",
        "camera_id",
        "default_disease_id",
        "active",
    ):
        _create_index_if_missing(conn, f"ix_remidio_routing_rules_{column_name}", "remidio_routing_rules", [column_name])
    _create_index_if_missing(conn, "ix_remidio_routing_connection_site_device", "remidio_routing_rules", ["remidio_connection_id", "site_custom_identifier", "remidio_device_type"])
    _create_index_if_missing(conn, "ix_remidio_routing_project_active", "remidio_routing_rules", ["project_id", "active"])

    if "remidio_exams" not in _table_names(conn):
        op.create_table(
            "remidio_exams",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("remidio_connection_id", sa.Integer(), nullable=False),
            sa.Column("remidio_site_id", sa.Integer(), nullable=True),
            sa.Column("remidio_exam_id", sa.String(length=64), nullable=False),
            sa.Column("site_custom_identifier", sa.String(length=255), nullable=True),
            sa.Column("remidio_numeric_site_id", sa.String(length=64), nullable=True),
            sa.Column("remidio_patient_id", sa.String(length=64), nullable=True),
            sa.Column("remidio_patient_mrn", sa.String(length=128), nullable=True),
            sa.Column("exam_local_id", sa.String(length=255), nullable=True),
            sa.Column("exam_custom_id", sa.String(length=255), nullable=True),
            sa.Column("device_types", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("exam_state", sa.String(length=64), nullable=True),
            sa.Column("exam_date_ms", sa.BigInteger(), nullable=True),
            sa.Column("exam_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("pull_source", sa.String(length=64), nullable=False),
            sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("pulled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["remidio_connection_id"], ["remidio_connections.id"], name="fk_remidio_exams_connection_id", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["remidio_site_id"], ["remidio_sites.id"], name="fk_remidio_exams_site_id", ondelete="SET NULL"),
            sa.UniqueConstraint("remidio_connection_id", "remidio_exam_id", name="uq_remidio_exam_connection_exam_id"),
        )
    for column_name in (
        "remidio_connection_id",
        "remidio_site_id",
        "site_custom_identifier",
        "remidio_numeric_site_id",
        "remidio_patient_id",
        "remidio_patient_mrn",
        "exam_date",
    ):
        _create_index_if_missing(conn, f"ix_remidio_exams_{column_name}", "remidio_exams", [column_name])
    _create_index_if_missing(conn, "ix_remidio_exams_connection_date", "remidio_exams", ["remidio_connection_id", "exam_date"])
    _create_index_if_missing(conn, "ix_remidio_exams_connection_patient", "remidio_exams", ["remidio_connection_id", "remidio_patient_mrn"])

    if "remidio_images" not in _table_names(conn):
        op.create_table(
            "remidio_images",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("remidio_exam_id", sa.Integer(), nullable=False),
            sa.Column("remidio_image_id", sa.String(length=64), nullable=False),
            sa.Column("device_type", sa.String(length=64), nullable=True),
            sa.Column("image_bucket", sa.String(length=64), nullable=True),
            sa.Column("image_variant", sa.String(length=32), nullable=True),
            sa.Column("laterality", sa.String(length=32), nullable=True),
            sa.Column("field", sa.String(length=64), nullable=True),
            sa.Column("quality", sa.String(length=64), nullable=True),
            sa.Column("width", sa.Integer(), nullable=True),
            sa.Column("height", sa.Integer(), nullable=True),
            sa.Column("remidio_path", sa.String(length=1000), nullable=True),
            sa.Column("remidio_thumbnail_path", sa.String(length=1000), nullable=True),
            sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["remidio_exam_id"], ["remidio_exams.id"], name="fk_remidio_images_exam_id", ondelete="CASCADE"),
            sa.UniqueConstraint("remidio_exam_id", "remidio_image_id", name="uq_remidio_image_exam_image_id"),
        )
    for column_name in ("remidio_exam_id", "device_type", "laterality", "field"):
        _create_index_if_missing(conn, f"ix_remidio_images_{column_name}", "remidio_images", [column_name])
    _create_index_if_missing(conn, "ix_remidio_images_exam_device", "remidio_images", ["remidio_exam_id", "device_type"])

    if "remidio_reports" not in _table_names(conn):
        op.create_table(
            "remidio_reports",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("remidio_exam_id", sa.Integer(), nullable=False),
            sa.Column("remidio_report_id", sa.String(length=64), nullable=False),
            sa.Column("report_type", sa.String(length=64), nullable=False),
            sa.Column("report_local_id", sa.String(length=255), nullable=True),
            sa.Column("generated_date_ms", sa.BigInteger(), nullable=True),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("remidio_path", sa.String(length=1000), nullable=True),
            sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["remidio_exam_id"], ["remidio_exams.id"], name="fk_remidio_reports_exam_id", ondelete="CASCADE"),
            sa.UniqueConstraint("remidio_exam_id", "remidio_report_id", "report_type", name="uq_remidio_report_exam_report_type"),
        )
    _create_index_if_missing(conn, "ix_remidio_reports_remidio_exam_id", "remidio_reports", ["remidio_exam_id"])
    _create_index_if_missing(conn, "ix_remidio_reports_exam_type", "remidio_reports", ["remidio_exam_id", "report_type"])


def downgrade() -> None:
    conn = op.get_bind()

    for name, table_name in (
        ("ix_remidio_reports_exam_type", "remidio_reports"),
        ("ix_remidio_reports_remidio_exam_id", "remidio_reports"),
        ("ix_remidio_images_exam_device", "remidio_images"),
        ("ix_remidio_images_field", "remidio_images"),
        ("ix_remidio_images_laterality", "remidio_images"),
        ("ix_remidio_images_device_type", "remidio_images"),
        ("ix_remidio_images_remidio_exam_id", "remidio_images"),
        ("ix_remidio_exams_connection_patient", "remidio_exams"),
        ("ix_remidio_exams_connection_date", "remidio_exams"),
        ("ix_remidio_exams_exam_date", "remidio_exams"),
        ("ix_remidio_exams_remidio_patient_mrn", "remidio_exams"),
        ("ix_remidio_exams_remidio_patient_id", "remidio_exams"),
        ("ix_remidio_exams_remidio_numeric_site_id", "remidio_exams"),
        ("ix_remidio_exams_site_custom_identifier", "remidio_exams"),
        ("ix_remidio_exams_remidio_site_id", "remidio_exams"),
        ("ix_remidio_exams_remidio_connection_id", "remidio_exams"),
        ("ix_remidio_routing_project_active", "remidio_routing_rules"),
        ("ix_remidio_routing_connection_site_device", "remidio_routing_rules"),
        ("ix_remidio_routing_rules_active", "remidio_routing_rules"),
        ("ix_remidio_routing_rules_default_disease_id", "remidio_routing_rules"),
        ("ix_remidio_routing_rules_camera_id", "remidio_routing_rules"),
        ("ix_remidio_routing_rules_lab_unit_id", "remidio_routing_rules"),
        ("ix_remidio_routing_rules_project_id", "remidio_routing_rules"),
        ("ix_remidio_routing_rules_remidio_site_id", "remidio_routing_rules"),
        ("ix_remidio_routing_rules_remidio_connection_id", "remidio_routing_rules"),
        ("ix_remidio_sites_connection_active", "remidio_sites"),
        ("ix_remidio_sites_active", "remidio_sites"),
        ("ix_remidio_sites_site_custom_identifier", "remidio_sites"),
        ("ix_remidio_sites_remidio_connection_id", "remidio_sites"),
        ("ix_remidio_connections_project_active", "remidio_connections"),
        ("ix_remidio_connections_active", "remidio_connections"),
        ("ix_remidio_connections_project_id", "remidio_connections"),
    ):
        _drop_index_if_exists(conn, name, table_name)

    for table_name in (
        "remidio_reports",
        "remidio_images",
        "remidio_exams",
        "remidio_routing_rules",
        "remidio_sites",
        "remidio_connections",
    ):
        if table_name in _table_names(conn):
            op.drop_table(table_name)
