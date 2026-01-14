"""add_hospital_isolation_to_users_fix

Revision ID: 1517278bfc85
Revises: 7399d7a901ce
Create Date: 2026-01-14 04:54:45.353407

Adds hospital_id and is_master_admin columns to users table for hospital isolation.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1517278bfc85'
down_revision: Union[str, Sequence[str], None] = '7399d7a901ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Add hospital isolation columns to users table."""
    # Add is_master_admin column first (no FK)
    op.add_column(
        'users',
        sa.Column('is_master_admin', sa.Boolean(), nullable=False, server_default='false')
    )

    # Add hospital_id column with FK to hospitals table
    op.add_column(
        'users',
        sa.Column(
            'hospital_id',
            sa.Integer(),
            nullable=True
        )
    )
    op.create_foreign_key(
        'fk_users_hospital_id',
        'users', 'hospitals',
        ['hospital_id'], ['id'],
        ondelete='RESTRICT'
    )
    op.create_index(
        'ix_users_hospital_id',
        'users',
        ['hospital_id']
    )


def downgrade() -> None:
    """Downgrade schema: Remove hospital isolation columns from users table."""
    op.drop_index('ix_users_hospital_id', table_name='users')
    op.drop_constraint('fk_users_hospital_id', 'users', type_='foreignkey')
    op.drop_column('users', 'hospital_id')
    op.drop_column('users', 'is_master_admin')
