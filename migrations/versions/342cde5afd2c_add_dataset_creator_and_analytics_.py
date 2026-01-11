"""Add dataset_creator and analytics_viewer roles

Revision ID: 342cde5afd2c
Revises: 413938207fa4
Create Date: 2026-01-11 08:19:01.870182

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '342cde5afd2c'
down_revision: Union[str, Sequence[str], None] = '413938207fa4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



from sqlalchemy.sql import table, column

roles_table = table('roles',
    column('id', sa.Integer),
    column('name', sa.String)
)

def upgrade() -> None:
    """Upgrade schema."""
    op.bulk_insert(roles_table,
        [
            {'name': 'dataset_creator'},
            {'name': 'analytics_viewer'}
        ]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM roles WHERE name IN ('dataset_creator', 'analytics_viewer')")
