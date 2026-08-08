"""add review submission history

Revision ID: d4f6a8b2c1e9
Revises: c8a4e2f1d9b7
Create Date: 2026-08-08 06:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from utils.mvw_image_listing_v2 import _build_mv_sql, _create_indexes_sql, _mv_name


revision: str = "d4f6a8b2c1e9"
down_revision: Union[str, Sequence[str], None] = "c8a4e2f1d9b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_NAME = "review_submission_history"


def _rebuild_views(*, prefer_updated_role_grade: bool) -> None:
    conn = op.get_bind()
    views = list(
        conn.execute(
            sa.text(
                "SELECT matviewname FROM pg_matviews WHERE schemaname=current_schema() "
                "AND matviewname LIKE 'mvw_image_listing_%_v2'"
            )
        ).scalars()
    )
    for name in views:
        quoted_name = conn.dialect.identifier_preparer.quote(name)
        conn.execute(sa.text(f"DROP MATERIALIZED VIEW {quoted_name}"))
    diseases = conn.execute(sa.text("SELECT id, name FROM diseases ORDER BY id")).all()
    for disease_id, disease_name in diseases:
        mv_name = _mv_name(str(disease_name), int(disease_id))
        conn.execute(
            sa.text(
                _build_mv_sql(
                    mv_name,
                    int(disease_id),
                    str(disease_name),
                    include_encounter_set_images=True,
                    prefer_updated_role_grade=prefer_updated_role_grade,
                )
            )
        )
        for index_sql in _create_indexes_sql(mv_name, include_encounter_set_images=True):
            conn.execute(sa.text(index_sql))


def upgrade() -> None:
    conn = op.get_bind()
    if TABLE_NAME not in inspect(conn).get_table_names():
        op.create_table(
            TABLE_NAME,
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("request_id", sa.String(36), nullable=False),
            sa.Column("task_id", sa.Integer(), nullable=False),
            sa.Column("actor_user_id", sa.Integer(), nullable=False),
            sa.Column("action_type", sa.String(32), nullable=False),
            sa.Column("source", sa.String(64), nullable=False),
            sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("before_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("after_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("version_tokens_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("request_id", name="uq_review_submission_history_request_id"),
        )
    indexes = {idx["name"] for idx in inspect(conn).get_indexes(TABLE_NAME)}
    for name, columns in (
        ("ix_review_submission_history_task_id", ["task_id"]),
        ("ix_review_submission_history_actor_user_id", ["actor_user_id"]),
        ("ix_review_submission_history_action_type", ["action_type"]),
        ("ix_review_submission_history_recorded_at", ["recorded_at"]),
        ("ix_review_submission_history_task_recorded", ["task_id", "recorded_at"]),
    ):
        if name not in indexes:
            op.create_index(name, TABLE_NAME, columns, unique=False)
    _rebuild_views(prefer_updated_role_grade=True)


def downgrade() -> None:
    conn = op.get_bind()
    _rebuild_views(prefer_updated_role_grade=False)
    if TABLE_NAME in inspect(conn).get_table_names():
        op.drop_table(TABLE_NAME)
