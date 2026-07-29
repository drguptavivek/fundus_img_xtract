"""Add encounter referral suggestion column.

Revision ID: e2f4a6b8c0d1
Revises: d1e2f3a4b5c6
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "e2f4a6b8c0d1"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


TABLE = "patient_encounters"
ATTACHMENTS_TABLE = "encounter_set_attachments"
COLUMN = "referral_suggestion"
UPDATED_COLUMN = "referral_suggestion_updated_at"
CHECK_NAME = "ck_patient_encounters_referral_suggestion"
INDEX_NAME = "ix_patient_encounters_referral_suggestion"


def _tables(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _columns(conn, table: str) -> set[str]:
    if table not in _tables(conn):
        return set()
    return {column["name"] for column in inspect(conn).get_columns(table)}


def _constraints(conn, table: str) -> set[str]:
    if table not in _tables(conn):
        return set()
    return {constraint["name"] for constraint in inspect(conn).get_check_constraints(table)}


def _indexes(conn, table: str) -> set[str]:
    if table not in _tables(conn):
        return set()
    return {index["name"] for index in inspect(conn).get_indexes(table)}


def upgrade():
    conn = op.get_bind()
    tables = _tables(conn)
    if TABLE not in tables:
        return

    columns = _columns(conn, TABLE)
    if COLUMN not in columns:
        op.add_column(
            TABLE,
            sa.Column(COLUMN, sa.String(length=16), nullable=False, server_default="missing"),
        )
    if UPDATED_COLUMN not in columns:
        op.add_column(TABLE, sa.Column(UPDATED_COLUMN, sa.DateTime(timezone=True), nullable=True))

    if CHECK_NAME not in _constraints(conn, TABLE):
        op.create_check_constraint(
            CHECK_NAME,
            TABLE,
            f"{COLUMN} IN ('yes','no','missing')",
        )
    if INDEX_NAME not in _indexes(conn, TABLE):
        op.create_index(INDEX_NAME, TABLE, [COLUMN])

    if ATTACHMENTS_TABLE in tables:
        _backfill_from_attachment_metadata(conn)


def downgrade():
    conn = op.get_bind()
    if TABLE not in _tables(conn):
        return

    if INDEX_NAME in _indexes(conn, TABLE):
        op.drop_index(INDEX_NAME, table_name=TABLE)
    if CHECK_NAME in _constraints(conn, TABLE):
        op.drop_constraint(CHECK_NAME, TABLE, type_="check")
    columns = _columns(conn, TABLE)
    if UPDATED_COLUMN in columns:
        op.drop_column(TABLE, UPDATED_COLUMN)
    if COLUMN in columns:
        op.drop_column(TABLE, COLUMN)


def _backfill_from_attachment_metadata(conn) -> None:
    positive_condition = """
        (esa.metadata_json ->> 'refer_required')::boolean IS TRUE
        OR (esa.metadata_json ->> 'ai_suggested_refer')::boolean IS TRUE
        OR (esa.metadata_json ->> 'gma_suggested_refer')::boolean IS TRUE
        OR lower(coalesce(esa.metadata_json #>> '{ocr,dr_report,dr_data,result}', '')) LIKE 'signs of dr detected%'
        OR lower(coalesce(esa.metadata_json #>> '{ocr,glaucoma_report,glaucoma_data,result}', '')) LIKE '%referral suggested%'
        OR lower(coalesce(esa.metadata_json #>> '{ocr,glaucoma_report,glaucoma_data,result}', '')) LIKE '%refer immediately%'
        OR lower(coalesce(esa.metadata_json #>> '{ocr,glaucoma_report,glaucoma_data,result}', '')) LIKE 'referable glaucoma%'
        OR lower(coalesce(esa.metadata_json #>> '{ocr,glaucoma_report,glaucoma_data,result}', '')) LIKE 'referable glacuoma%'
    """
    negative_condition = """
        (esa.metadata_json ->> 'refer_required')::boolean IS FALSE
        OR (esa.metadata_json ->> 'ai_suggested_refer')::boolean IS FALSE
        OR (esa.metadata_json ->> 'gma_suggested_refer')::boolean IS FALSE
        OR lower(coalesce(esa.metadata_json #>> '{ocr,dr_report,dr_data,result}', '')) LIKE 'no signs of dr detected%'
        OR lower(coalesce(esa.metadata_json #>> '{ocr,glaucoma_report,glaucoma_data,result}', '')) LIKE '%no referable glaucoma%'
    """
    conn.execute(
        sa.text(
            f"""
            UPDATE {TABLE} pe
            SET {COLUMN} = 'yes',
                {UPDATED_COLUMN} = now()
            WHERE EXISTS (
                SELECT 1
                FROM {ATTACHMENTS_TABLE} esa
                WHERE esa.patient_encounter_id = pe.id
                  AND ({positive_condition})
            )
            """
        )
    )
    conn.execute(
        sa.text(
            f"""
            UPDATE {TABLE} pe
            SET {COLUMN} = 'no',
                {UPDATED_COLUMN} = now()
            WHERE pe.{COLUMN} = 'missing'
              AND EXISTS (
                  SELECT 1
                  FROM {ATTACHMENTS_TABLE} esa
                  WHERE esa.patient_encounter_id = pe.id
                    AND ({negative_condition})
              )
            """
        )
    )
