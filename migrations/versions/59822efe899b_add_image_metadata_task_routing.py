"""add image metadata task routing

Revision ID: 59822efe899b
Revises: d4f6a8b2c1e9
Create Date: 2026-08-08 07:10:21.104646

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '59822efe899b'
down_revision: Union[str, Sequence[str], None] = 'd4f6a8b2c1e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    table_name = "upload_profile_est_package_image_schemes"
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if "metadata_field_key" not in columns:
        op.add_column(table_name, sa.Column("metadata_field_key", sa.String(length=128), nullable=True))
    if "metadata_match_value" not in columns:
        op.add_column(table_name, sa.Column("metadata_match_value", sa.String(length=255), nullable=True))

    inspector = sa.inspect(conn)
    check_names = {check["name"] for check in inspector.get_check_constraints(table_name)}
    if "ck_up_est_pkg_image_metadata_rule_complete" not in check_names:
        op.create_check_constraint(
            "ck_up_est_pkg_image_metadata_rule_complete",
            table_name,
            "((metadata_field_key IS NULL AND metadata_match_value IS NULL) OR "
            "(metadata_field_key IS NOT NULL AND btrim(metadata_field_key) <> '' AND "
            "metadata_match_value IS NOT NULL AND btrim(metadata_match_value) <> ''))",
        )


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    table_name = "upload_profile_est_package_image_schemes"
    inspector = sa.inspect(conn)
    check_names = {check["name"] for check in inspector.get_check_constraints(table_name)}
    if "ck_up_est_pkg_image_metadata_rule_complete" in check_names:
        op.drop_constraint("ck_up_est_pkg_image_metadata_rule_complete", table_name, type_="check")

    columns = {column["name"] for column in sa.inspect(conn).get_columns(table_name)}
    if "metadata_match_value" in columns:
        op.drop_column(table_name, "metadata_match_value")
    if "metadata_field_key" in columns:
        op.drop_column(table_name, "metadata_field_key")
