"""expand project workflow permissions

Revision ID: da06b3c4d5e7
Revises: d9f5a2b3c4d6, e2a6c4d8f1b3
Create Date: 2026-08-11 10:15:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "da06b3c4d5e7"
down_revision: Union[str, Sequence[str], None] = (
    "d9f5a2b3c4d6",
    "e2a6c4d8f1b3",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CAPABILITY_COLUMNS = (
    "can_upload",
    "can_review_discrepancies",
    "can_export_data",
    "can_view_analytics",
    "can_create_datasets",
    "can_adjudicate_regrades",
)


def _columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if "project_encounter_set_permissions" not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns("project_encounter_set_permissions")}


def upgrade() -> None:
    existing = _columns()
    for name in CAPABILITY_COLUMNS:
        if name not in existing:
            op.add_column(
                "project_encounter_set_permissions",
                sa.Column(name, sa.Boolean(), server_default="false", nullable=False),
            )
    op.execute(sa.text("""
        INSERT INTO project_encounter_set_permissions (
            project_id, user_id, lab_unit_id, can_upload, active,
            created_at, updated_at
        )
        SELECT DISTINCT
            project_profile.project_id,
            assignment.user_id,
            assignment.lab_unit_id,
            TRUE,
            TRUE,
            now(),
            now()
        FROM project_upload_profile_assignments assignment
        JOIN project_upload_profiles project_profile
          ON project_profile.id = assignment.project_upload_profile_id
        WHERE assignment.active = TRUE
          AND project_profile.active = TRUE
        ON CONFLICT (project_id, user_id, lab_unit_id)
        DO UPDATE SET can_upload = TRUE, active = TRUE, updated_at = now()
    """))


def downgrade() -> None:
    existing = _columns()
    for name in reversed(CAPABILITY_COLUMNS):
        if name in existing:
            op.drop_column("project_encounter_set_permissions", name)
