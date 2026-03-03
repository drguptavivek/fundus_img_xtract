"""allow_not_gradable_direct_image_verification_status

Revision ID: 4fd8e6f6d2b1
Revises: 216d32163cf6
Create Date: 2026-03-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "4fd8e6f6d2b1"
down_revision: Union[str, Sequence[str], None] = "216d32163cf6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_di_verify_status'
            ) THEN
                ALTER TABLE direct_image_verifications
                    DROP CONSTRAINT ck_di_verify_status;
            END IF;

            ALTER TABLE direct_image_verifications
                ADD CONSTRAINT ck_di_verify_status
                CHECK (verified_status IN ('verified', 'unverified', 'pending', 'not_gradable'));
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            UPDATE direct_image_verifications
            SET verified_status = 'unverified'
            WHERE verified_status = 'not_gradable';

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_di_verify_status'
            ) THEN
                ALTER TABLE direct_image_verifications
                    DROP CONSTRAINT ck_di_verify_status;
            END IF;

            ALTER TABLE direct_image_verifications
                ADD CONSTRAINT ck_di_verify_status
                CHECK (verified_status IN ('verified', 'unverified', 'pending'));
        END $$;
        """
    )
