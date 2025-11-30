"""allow task_review consensus method

Revision ID: d7e3fb45da1d
Revises: 2e82ab9a8980
Create Date: 2025-11-30 10:15:09.147519

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd7e3fb45da1d'
down_revision: Union[str, Sequence[str], None] = '2e82ab9a8980'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('ck_consensus_method_valid', 'consensus', type_='check')
    op.create_check_constraint(
        'ck_consensus_method_valid',
        'consensus',
        "method IN ('match','adjudication','task_review')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_consensus_method_valid', 'consensus', type_='check')
    op.create_check_constraint(
        'ck_consensus_method_valid',
        'consensus',
        "method IN ('match','adjudication')",
    )
