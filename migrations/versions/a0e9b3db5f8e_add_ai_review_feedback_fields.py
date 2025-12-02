"""add ai review feedback fields to grades

Revision ID: a0e9b3db5f8e
Revises: 9e44b7b02b8c
Create Date: 2026-04-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a0e9b3db5f8e"
down_revision: Union[str, Sequence[str], None] = "9e44b7b02b8c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add AI review feedback fields and constraint."""
    op.add_column("grades", sa.Column("ai_review_status", sa.String(length=32), nullable=True))
    op.add_column("grades", sa.Column("ai_review_comment", sa.Text(), nullable=True))
    op.add_column(
        "grades",
        sa.Column("ai_reviewed_by_user_id", sa.Integer(), nullable=True),
    )
    op.add_column("grades", sa.Column("ai_reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_grades_ai_reviewed_by_user_id"), "grades", ["ai_reviewed_by_user_id"], unique=False)
    op.create_foreign_key(
        "fk_grades_ai_reviewed_by_user_id_users",
        "grades",
        "users",
        ["ai_reviewed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_grade_ai_review_status_valid",
        "grades",
        "ai_review_status IS NULL OR ai_review_status IN ('ok','minor_miss','major_miss')",
    )


def downgrade() -> None:
    """Remove AI review feedback fields and constraint."""
    op.drop_constraint("ck_grade_ai_review_status_valid", "grades", type_="check")
    op.drop_constraint("fk_grades_ai_reviewed_by_user_id_users", "grades", type_="foreignkey")
    op.drop_index(op.f("ix_grades_ai_reviewed_by_user_id"), table_name="grades")
    op.drop_column("grades", "ai_reviewed_at")
    op.drop_column("grades", "ai_reviewed_by_user_id")
    op.drop_column("grades", "ai_review_comment")
    op.drop_column("grades", "ai_review_status")
