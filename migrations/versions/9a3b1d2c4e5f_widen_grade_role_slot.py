"""Allow regrade_adj in grades.role_slot constraint.

Revision ID: 9a3b1d2c4e5f
Revises: c33fff63a0b2
Create Date: 2026-02-07 13:45:00.000000
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9a3b1d2c4e5f"
down_revision: Union[str, Sequence[str], None] = "c33fff63a0b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_grade_role_slot_valid'
            ) THEN
                ALTER TABLE grades DROP CONSTRAINT ck_grade_role_slot_valid;
            END IF;

            ALTER TABLE grades
            ADD CONSTRAINT ck_grade_role_slot_valid
            CHECK (role_slot IN ('resident','resident2','arbitrator','ai','review','regrade_adj'));
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_grade_role_slot_valid'
            ) THEN
                ALTER TABLE grades DROP CONSTRAINT ck_grade_role_slot_valid;
            END IF;

            ALTER TABLE grades
            ADD CONSTRAINT ck_grade_role_slot_valid
            CHECK (role_slot IN ('resident','resident2','arbitrator','ai','review'));
        END $$;
        """
    )
