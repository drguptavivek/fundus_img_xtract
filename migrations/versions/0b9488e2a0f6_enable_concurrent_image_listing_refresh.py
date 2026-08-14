"""enable concurrent image listing refresh

Revision ID: 0b9488e2a0f6
Revises: 7cb461952afe
Create Date: 2026-08-14 09:29:50.014961

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0b9488e2a0f6'
down_revision: Union[str, Sequence[str], None] = '7cb461952afe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MAX_IDENT_LEN = 63


def _index_name(mv_name: str, suffix: str) -> str:
    """Keep this historical migration independent of application helpers."""
    suffix = suffix.strip("_")
    max_base_len = _MAX_IDENT_LEN - len(suffix) - 1
    base = mv_name[:max_base_len].rstrip("_")
    return f"{base}_{suffix}"


def _image_listing_views(conn) -> list[str]:
    return list(
        conn.execute(
            sa.text(
                "SELECT matviewname FROM pg_matviews "
                "WHERE schemaname = current_schema() "
                "AND matviewname LIKE 'mvw_image_listing_%_v2' "
                "ORDER BY matviewname"
            )
        ).scalars()
    )


def _replace_task_id_index(conn, mv_name: str, *, unique: bool) -> None:
    preparer = conn.dialect.identifier_preparer
    quoted_view = preparer.quote(mv_name)
    index_name = _index_name(mv_name, "task_id")
    quoted_index = preparer.quote(index_name)

    if unique:
        duplicate_task_id = conn.execute(
            sa.text(
                f"SELECT task_id FROM {quoted_view} "
                "GROUP BY task_id HAVING count(*) > 1 LIMIT 1"
            )
        ).scalar()
        if duplicate_task_id is not None:
            raise RuntimeError(
                f"Cannot enable concurrent refresh for {mv_name}: duplicate task_id "
                f"{duplicate_task_id}"
            )

    conn.execute(sa.text(f"DROP INDEX IF EXISTS {quoted_index}"))
    qualifier = "UNIQUE " if unique else ""
    conn.execute(
        sa.text(
            f"CREATE {qualifier}INDEX {quoted_index} "
            f"ON {quoted_view} (task_id)"
        )
    )


def upgrade() -> None:
    """Give every populated disease listing MV a full-row unique key."""
    conn = op.get_bind()
    for mv_name in _image_listing_views(conn):
        _replace_task_id_index(conn, mv_name, unique=True)


def downgrade() -> None:
    """Restore the prior non-unique lookup indexes."""
    conn = op.get_bind()
    for mv_name in _image_listing_views(conn):
        _replace_task_id_index(conn, mv_name, unique=False)
