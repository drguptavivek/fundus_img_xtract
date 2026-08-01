"""include EncounterSet images in analytics views

Revision ID: 7e6f5a4b3c2d
Revises: 5d814e1789eb
Create Date: 2026-08-01 12:45:00.000000

"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

from utils.mvw_image_listing_v2 import _build_mv_sql, _create_indexes_sql, _mv_name


revision: str = "7e6f5a4b3c2d"
down_revision: Union[str, Sequence[str], None] = "5d814e1789eb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_existing_v2_views() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        text(
            """
            SELECT matviewname
            FROM pg_matviews
            WHERE schemaname = current_schema()
              AND matviewname LIKE :pattern
            ORDER BY matviewname
            """
        ),
        {"pattern": "mvw_image_listing_%_v2"},
    ).all()
    for (name,) in rows:
        if not re.fullmatch(r"[a-z0-9_]+", name):
            raise ValueError(f"Unsafe materialized view name: {name}")
        conn.execute(text(f"DROP MATERIALIZED VIEW IF EXISTS {name}"))


def _recreate_all(
    build_sql: Callable[[str, int, str], str],
    build_indexes: Callable[[str], Iterable[str]],
) -> None:
    conn = op.get_bind()
    diseases = conn.execute(text("SELECT id, name FROM diseases ORDER BY id")).all()
    for disease_id, disease_name in diseases:
        disease_id = int(disease_id)
        disease_name = str(disease_name)
        mv_name = _mv_name(disease_name, disease_id)
        conn.execute(text(build_sql(mv_name, disease_id, disease_name)))
        for index_sql in build_indexes(mv_name):
            conn.execute(text(index_sql))


def upgrade() -> None:
    """Rebuild disease views with physical EncounterSet image rows."""
    _drop_existing_v2_views()

    def build_with_encounter_set_images(
        mv_name: str, disease_id: int, disease_name: str
    ) -> str:
        return _build_mv_sql(
            mv_name,
            disease_id,
            disease_name,
            include_encounter_set_images=True,
        )

    def indexes_with_encounter_set_images(mv_name: str) -> Iterable[str]:
        return _create_indexes_sql(mv_name, include_encounter_set_images=True)

    _recreate_all(build_with_encounter_set_images, indexes_with_encounter_set_images)


def downgrade() -> None:
    """Rebuild disease views without physical EncounterSet image rows."""
    _drop_existing_v2_views()

    def build_without_encounter_set_images(
        mv_name: str, disease_id: int, disease_name: str
    ) -> str:
        return _build_mv_sql(
            mv_name,
            disease_id,
            disease_name,
            include_encounter_set_images=False,
        )

    _recreate_all(build_without_encounter_set_images, _create_indexes_sql)
