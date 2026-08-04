"""add project annotation policy

Revision ID: 8a7b6c5d4e3f
Revises: 7e6f5a4b3c2d
Create Date: 2026-08-02 22:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "8a7b6c5d4e3f"
down_revision: Union[str, Sequence[str], None] = "7e6f5a4b3c2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TOOL_CHECK = "tool_key IN ('box','rect','polygon','brush_mask','ellipse','pyramid')"
LOCALIZATION_CHECK = "localization IN ('none','box','segmentation','box_or_segmentation')"


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if "project_annotation_policies" not in tables:
        op.create_table(
            "project_annotation_policies",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("default_localization", sa.String(32), server_default="box_or_segmentation", nullable=False),
            sa.Column("preferred_tool_key", sa.String(32), server_default="box", nullable=False),
            sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
            sa.Column("created_by_id", sa.Integer(), nullable=True),
            sa.Column("updated_by_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("revision >= 1", name="ck_project_annotation_policy_revision"),
            sa.CheckConstraint("default_localization IN ('none','box','segmentation','box_or_segmentation')", name="ck_project_annotation_policy_localization"),
            sa.CheckConstraint("preferred_tool_key IN ('box','rect','polygon','brush_mask','ellipse','pyramid')", name="ck_project_annotation_policy_preferred_tool"),
            sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("project_id", name="uq_project_annotation_policies_project_id"),
        )
        op.create_index("ix_project_annotation_policies_project_id", "project_annotation_policies", ["project_id"], unique=True)

    tables = _tables()
    if "project_annotation_tools" not in tables:
        op.create_table(
            "project_annotation_tools",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("policy_id", sa.Integer(), nullable=False),
            sa.Column("tool_key", sa.String(32), nullable=False),
            sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("settings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.CheckConstraint(TOOL_CHECK, name="ck_project_annotation_tool_key"),
            sa.ForeignKeyConstraint(["policy_id"], ["project_annotation_policies.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("policy_id", "tool_key", name="uq_project_annotation_tool"),
        )
        op.create_index("ix_project_annotation_tools_policy_id", "project_annotation_tools", ["policy_id"])

    tables = _tables()
    if "project_annotation_classes" not in tables:
        op.create_table(
            "project_annotation_classes",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("policy_id", sa.Integer(), nullable=False),
            sa.Column("key", sa.String(64), nullable=False),
            sa.Column("localization", sa.String(32), nullable=False),
            sa.Column("multiple_instances", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint(LOCALIZATION_CHECK, name="ck_project_annotation_class_localization"),
            sa.ForeignKeyConstraint(["policy_id"], ["project_annotation_policies.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("policy_id", "key", name="uq_project_annotation_class_key"),
        )
        op.create_index("ix_project_annotation_classes_policy_id", "project_annotation_classes", ["policy_id"])
        op.create_index("ix_project_annotation_classes_policy_active", "project_annotation_classes", ["policy_id", "active"])

def downgrade() -> None:
    for table_name in (
        # These three tables existed in an uncommitted draft of this revision.
        # Keeping them here makes downgrade safe for development databases that
        # applied that draft before the policy model was simplified.
        "project_annotation_feature_override_tools",
        "project_annotation_feature_overrides",
        "project_annotation_class_tools",
        "project_annotation_classes",
        "project_annotation_tools",
        "project_annotation_policies",
    ):
        if table_name in _tables():
            op.drop_table(table_name)
