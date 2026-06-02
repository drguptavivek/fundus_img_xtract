"""rename verification metadata flag to editable

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f8
Create Date: 2026-05-30 05:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FIELDS_TABLE = "upload_metadata_field_definitions"
EST_TABLE = "encounter_set_types"
OLD_COLUMN = "required_for_verification_default"
NEW_COLUMN = "editable_during_verification_default"
OLD_SCHEMA_KEY = "required_for_verification"
NEW_SCHEMA_KEY = "editable_during_verification"


def _table_names(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _column_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    return {column["name"] for column in inspect(conn).get_columns(table_name)}


def _rewrite_schema_key(conn, *, old_key: str, new_key: str) -> None:
    if EST_TABLE not in _table_names(conn):
        return
    conn.execute(
        text(
            f"""
            UPDATE {EST_TABLE}
            SET metadata_schema_json = jsonb_set(
                COALESCE(metadata_schema_json, '{{"fields":[]}}'::jsonb),
                '{{fields}}',
                COALESCE(
                    (
                        SELECT jsonb_agg(
                            CASE
                                WHEN field ? :old_key AND NOT field ? :new_key
                                    THEN (field - :old_key) || jsonb_build_object(:new_key, field -> :old_key)
                                ELSE field - :old_key
                            END
                            ORDER BY ordinality
                        )
                        FROM jsonb_array_elements(COALESCE(metadata_schema_json -> 'fields', '[]'::jsonb))
                            WITH ORDINALITY AS fields(field, ordinality)
                    ),
                    '[]'::jsonb
                ),
                true
            )
            WHERE COALESCE(metadata_schema_json -> 'fields', '[]'::jsonb) @> jsonb_build_array(jsonb_build_object(:old_key, true))
               OR COALESCE(metadata_schema_json -> 'fields', '[]'::jsonb) @> jsonb_build_array(jsonb_build_object(:old_key, false))
            """
        ),
        {"old_key": old_key, "new_key": new_key},
    )


def upgrade() -> None:
    conn = op.get_bind()
    columns = _column_names(conn, FIELDS_TABLE)
    if FIELDS_TABLE in _table_names(conn):
        if OLD_COLUMN in columns and NEW_COLUMN not in columns:
            op.alter_column(FIELDS_TABLE, OLD_COLUMN, new_column_name=NEW_COLUMN)
        elif NEW_COLUMN not in columns:
            op.add_column(
                FIELDS_TABLE,
                sa.Column(NEW_COLUMN, sa.Boolean(), nullable=False, server_default=sa.text("false")),
            )
        elif OLD_COLUMN in columns:
            conn.execute(
                text(
                    f"""
                    UPDATE {FIELDS_TABLE}
                    SET {NEW_COLUMN} = {NEW_COLUMN} OR {OLD_COLUMN}
                    """
                )
            )
            op.drop_column(FIELDS_TABLE, OLD_COLUMN)

    _rewrite_schema_key(conn, old_key=OLD_SCHEMA_KEY, new_key=NEW_SCHEMA_KEY)


def downgrade() -> None:
    conn = op.get_bind()
    columns = _column_names(conn, FIELDS_TABLE)
    if FIELDS_TABLE in _table_names(conn):
        if NEW_COLUMN in columns and OLD_COLUMN not in columns:
            op.alter_column(FIELDS_TABLE, NEW_COLUMN, new_column_name=OLD_COLUMN)
        elif OLD_COLUMN not in columns:
            op.add_column(
                FIELDS_TABLE,
                sa.Column(OLD_COLUMN, sa.Boolean(), nullable=False, server_default=sa.text("false")),
            )
        elif NEW_COLUMN in columns:
            conn.execute(
                text(
                    f"""
                    UPDATE {FIELDS_TABLE}
                    SET {OLD_COLUMN} = {OLD_COLUMN} OR {NEW_COLUMN}
                    """
                )
            )
            op.drop_column(FIELDS_TABLE, NEW_COLUMN)

    _rewrite_schema_key(conn, old_key=NEW_SCHEMA_KEY, new_key=OLD_SCHEMA_KEY)
