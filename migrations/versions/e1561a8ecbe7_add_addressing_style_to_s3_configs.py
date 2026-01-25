"""add addressing_style to s3_configs

Revision ID: e1561a8ecbe7
Revises: da3d9ac89e74
Create Date: 2026-01-25 16:32:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = 'e1561a8ecbe7'
down_revision = '4b7b1e398a79'  # add_multi_tenant_s3_support
branch_labels = None
depends_on = None


def upgrade():
    # Add addressing_style column with default value
    op.add_column(
        's3_configs',
        sa.Column(
            'addressing_style',
            sa.String(20),
            nullable=False,
            server_default='auto'
        )
    )

    # Add check constraint for addressing_style values
    op.execute("""
        ALTER TABLE s3_configs
        ADD CONSTRAINT ck_s3_config_addressing_style
        CHECK (addressing_style IN ('auto', 'virtual', 'path'))
    """)


def downgrade():
    # Drop check constraint
    op.execute("""
        ALTER TABLE s3_configs
        DROP CONSTRAINT IF EXISTS ck_s3_config_addressing_style
    """)

    # Drop column
    op.drop_column('s3_configs', 'addressing_style')
