"""add encounter set import mapper revisions

Revision ID: 91a4c6e8f2b0
Revises: 900fc1af1ed3
Create Date: 2026-09-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "91a4c6e8f2b0"
down_revision: Union[str, Sequence[str], None] = "900fc1af1ed3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "encounter_set_import_mapper_revisions" not in inspector.get_table_names():
        op.create_table(
            "encounter_set_import_mapper_revisions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("mapper_uuid", sa.String(36), nullable=False),
            sa.Column("encounter_set_type_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
            sa.Column("schema_fingerprint", sa.String(64), nullable=False),
            sa.Column("source_header_fingerprint", sa.String(64), nullable=False),
            sa.Column("source_headers_json", postgresql.JSONB(), nullable=False),
            sa.Column("mapping_json", postgresql.JSONB(), nullable=False),
            sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cloned_from_revision_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["encounter_set_type_id"], ["encounter_set_types.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["cloned_from_revision_id"], ["encounter_set_import_mapper_revisions.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("mapper_uuid", "revision", name="uq_encounter_set_import_mapper_revision"),
            sa.CheckConstraint("status IN ('draft', 'finalized', 'retired')", name="ck_encounter_set_import_mapper_status"),
            sa.CheckConstraint("use_count >= 0", name="ck_encounter_set_import_mapper_use_count"),
        )
        op.create_index("ix_encounter_set_import_mapper_revisions_mapper_uuid", "encounter_set_import_mapper_revisions", ["mapper_uuid"])
        op.create_index("ix_encounter_set_import_mapper_revisions_encounter_set_type_id", "encounter_set_import_mapper_revisions", ["encounter_set_type_id"])
        op.create_index("ix_encounter_set_import_mapper_revisions_status", "encounter_set_import_mapper_revisions", ["status"])
        op.create_index("ix_encounter_set_import_mapper_type_status", "encounter_set_import_mapper_revisions", ["encounter_set_type_id", "status"])
    inspector = sa.inspect(op.get_bind())
    if "encounter_set_import_mapper_audits" not in inspector.get_table_names():
        op.create_table(
            "encounter_set_import_mapper_audits",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("mapper_revision_id", sa.Integer(), nullable=True),
            sa.Column("mapper_uuid", sa.String(36), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("action", sa.String(32), nullable=False),
            sa.Column("snapshot_json", postgresql.JSONB(), nullable=False),
            sa.Column("actor_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["mapper_revision_id"], ["encounter_set_import_mapper_revisions.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_encounter_set_import_mapper_audits_mapper_revision_id", "encounter_set_import_mapper_audits", ["mapper_revision_id"])
        op.create_index("ix_encounter_set_import_mapper_audits_mapper_uuid", "encounter_set_import_mapper_audits", ["mapper_uuid"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "encounter_set_import_mapper_audits" in inspector.get_table_names():
        op.drop_table("encounter_set_import_mapper_audits")
    inspector = sa.inspect(op.get_bind())
    if "encounter_set_import_mapper_revisions" in inspector.get_table_names():
        op.drop_table("encounter_set_import_mapper_revisions")
