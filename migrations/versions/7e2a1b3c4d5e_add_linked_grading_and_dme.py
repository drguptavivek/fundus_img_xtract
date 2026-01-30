"""Add linked grading configuration and DME gradings

Revision ID: 7e2a1b3c4d5e
Revises: f1b2c3d4e5f6
Create Date: 2026-01-30 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "7e2a1b3c4d5e"
down_revision: Union[str, Sequence[str], None] = "f1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS linked_disease_gradings (
            id SERIAL PRIMARY KEY,
            primary_disease_id INTEGER NOT NULL,
            linked_disease_id INTEGER NOT NULL,
            display_order INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_linked_disease_primary'
            ) THEN
                ALTER TABLE linked_disease_gradings
                    ADD CONSTRAINT fk_linked_disease_primary
                    FOREIGN KEY (primary_disease_id) REFERENCES diseases(id);
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_linked_disease_linked'
            ) THEN
                ALTER TABLE linked_disease_gradings
                    ADD CONSTRAINT fk_linked_disease_linked
                    FOREIGN KEY (linked_disease_id) REFERENCES diseases(id);
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'uq_linked_disease_pair'
            ) THEN
                ALTER TABLE linked_disease_gradings
                    ADD CONSTRAINT uq_linked_disease_pair
                    UNIQUE (primary_disease_id, linked_disease_id);
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'uq_linked_disease_unique'
            ) THEN
                ALTER TABLE linked_disease_gradings
                    ADD CONSTRAINT uq_linked_disease_unique
                    UNIQUE (linked_disease_id);
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'ck_linked_disease_not_self'
            ) THEN
                ALTER TABLE linked_disease_gradings
                    ADD CONSTRAINT ck_linked_disease_not_self
                    CHECK (primary_disease_id <> linked_disease_id);
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_linked_disease_primary_active
            ON linked_disease_gradings(primary_disease_id, is_active);
        """
    )

    op.execute(
        """
        DO $$
        DECLARE
            dme_id INTEGER;
            dr_id INTEGER;
            m1_id INTEGER;
        BEGIN
            SELECT id INTO dme_id FROM diseases WHERE name = 'DME' LIMIT 1;
            IF dme_id IS NULL THEN
                INSERT INTO diseases (name) VALUES ('DME') RETURNING id INTO dme_id;
            END IF;

            IF dme_id IS NOT NULL THEN
                IF NOT EXISTS (
                    SELECT 1 FROM disease_gradings
                    WHERE disease_id = dme_id AND impression = 'M0 No DME'
                ) THEN
                    INSERT INTO disease_gradings (disease_id, impression, display_order, is_active, guidelines)
                    VALUES (dme_id, 'M0 No DME', 1, TRUE, 'No diabetic macular edema.');
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM disease_gradings
                    WHERE disease_id = dme_id AND impression = 'M1 Referable Diabetic Maculopathy'
                ) THEN
                    INSERT INTO disease_gradings (disease_id, impression, display_order, is_active, guidelines)
                    VALUES (
                        dme_id,
                        'M1 Referable Diabetic Maculopathy',
                        2,
                        TRUE,
                        '<ul><li>Exudate within 1 disc diameter (DD) of the centre of the fovea, OR</li><li>A group of exudates within the macula (area ≥ half the disc area) and this area is all within the macular area.</li></ul>'
                    );
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM disease_gradings
                    WHERE disease_id = dme_id AND impression = 'Not Gradable'
                ) THEN
                    INSERT INTO disease_gradings (disease_id, impression, display_order, is_active, guidelines)
                    VALUES (dme_id, 'Not Gradable', 3, TRUE, 'If cannot grade, mark as not gradable. Note reasons in remarks.');
                END IF;

                SELECT id INTO m1_id FROM disease_gradings
                WHERE disease_id = dme_id AND impression = 'M1 Referable Diabetic Maculopathy'
                LIMIT 1;

                IF m1_id IS NOT NULL THEN
                    IF NOT EXISTS (
                        SELECT 1 FROM gradings_features
                        WHERE disease_grading_id = m1_id AND label = 'Exudate within 1 disc diameter of the centre of the fovea'
                    ) THEN
                        INSERT INTO gradings_features (disease_grading_id, sr_no, label)
                        VALUES (m1_id, 1, 'Exudate within 1 disc diameter of the centre of the fovea');
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM gradings_features
                        WHERE disease_grading_id = m1_id AND label = 'Group of exudates within macula (area ≥ half disc area) within macular area'
                    ) THEN
                        INSERT INTO gradings_features (disease_grading_id, sr_no, label)
                        VALUES (
                            m1_id,
                            2,
                            'Group of exudates within macula (area ≥ half disc area) within macular area'
                        );
                    END IF;
                END IF;
            END IF;

            SELECT id INTO dr_id FROM diseases
            WHERE LOWER(name) IN ('diabetic retinopathy', 'dr')
            ORDER BY id
            LIMIT 1;

            IF dr_id IS NOT NULL AND dme_id IS NOT NULL THEN
                IF NOT EXISTS (
                    SELECT 1 FROM linked_disease_gradings
                    WHERE primary_disease_id = dr_id AND linked_disease_id = dme_id
                ) THEN
                    INSERT INTO linked_disease_gradings
                        (primary_disease_id, linked_disease_id, display_order, is_active)
                    VALUES (dr_id, dme_id, 1, TRUE);
                END IF;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        DO $$
        DECLARE
            dme_id INTEGER;
            dr_id INTEGER;
        BEGIN
            SELECT id INTO dme_id FROM diseases WHERE name = 'DME' LIMIT 1;
            SELECT id INTO dr_id FROM diseases WHERE LOWER(name) IN ('diabetic retinopathy', 'dr') ORDER BY id LIMIT 1;

            IF dr_id IS NOT NULL AND dme_id IS NOT NULL THEN
                DELETE FROM linked_disease_gradings
                WHERE primary_disease_id = dr_id AND linked_disease_id = dme_id;
            END IF;

            IF dme_id IS NOT NULL THEN
                IF NOT EXISTS (SELECT 1 FROM grading_tasks WHERE disease_id = dme_id) THEN
                    DELETE FROM gradings_features
                    WHERE disease_grading_id IN (
                        SELECT id FROM disease_gradings WHERE disease_id = dme_id
                    );
                    DELETE FROM disease_gradings WHERE disease_id = dme_id;
                    DELETE FROM diseases WHERE id = dme_id;
                END IF;
            END IF;
        END $$;
        """
    )

    op.execute("DROP TABLE IF EXISTS linked_disease_gradings;")
