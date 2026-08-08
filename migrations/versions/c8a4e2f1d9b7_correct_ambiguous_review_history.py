"""correct ambiguous review history

Revision ID: c8a4e2f1d9b7
Revises: 536dcee9e7de
Create Date: 2026-08-08 06:30:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from scripts.review_grade_correction_20260808 import (
    apply_correction,
    refresh_image_listing_materialized_views,
    revert_correction,
)


revision: str = "c8a4e2f1d9b7"
down_revision: Union[str, Sequence[str], None] = "536dcee9e7de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the fail-closed, archive-first review-history correction."""
    connection = op.get_bind()
    result = apply_correction(connection)
    if result.get("state") in {"applied", "reapplied_from_archive"}:
        refresh_image_listing_materialized_views(connection)


def downgrade() -> None:
    """Restore archived review rows only when no later review replaced them."""
    connection = op.get_bind()
    result = revert_correction(connection)
    if result.get("review_rows_restored") or result.get("review_tags_reverted"):
        refresh_image_listing_materialized_views(connection)
