"""Add Strabismus disease with encounter-set grading and 5-gaze positions

Revision ID: 50d6eca5967e
Revises: fab9ac5d5532
Create Date: 2026-01-31 12:51:36.081227

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column


# revision identifiers, used by Alembic.
revision: str = '50d6eca5967e'
down_revision: Union[str, Sequence[str], None] = 'fab9ac5d5532'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add Strabismus disease with encounter-set grading."""
    # Get database connection for checking existence
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Check if Strabismus already exists (idempotent)
    existing_diseases = conn.execute(
        sa.text("SELECT id, name FROM diseases WHERE name = 'Strabismus'")
    ).fetchall()

    if existing_diseases:
        # Strabismus already exists, skip
        return

    # Insert Strabismus disease with encounter-set grading scope
    # Using the next available ID (or let the database assign it)
    conn.execute(
        sa.text("""
            INSERT INTO diseases (name, grading_scope)
            VALUES ('Strabismus', 'encounter')
        """)
    )

    # Get the inserted Strabismus disease ID
    strabismus_id_result = conn.execute(
        sa.text("SELECT id FROM diseases WHERE name = 'Strabismus'")
    ).first()
    strabismus_id = strabismus_id_result[0] if strabismus_id_result else None

    if strabismus_id:
        # Insert Strabismus grading labels
        grading_labels = [
            ('No Strabismus', 1, 'No strabismus detected - eyes aligned'),
            ('Esotropia', 2, 'Inward deviation of one eye'),
            ('Exotropia', 3, 'Outward deviation of one eye'),
            ('Hypertropia', 4, 'Upward deviation of one eye'),
            ('Hypotropia', 5, 'Downward deviation of one eye'),
            ('Intermittent', 6, 'Intermittent strabismus - not constant'),
            ('Microtropia', 7, 'Small angle strabismus'),
            ('Surgical', 8, 'Post-surgical status or requires surgery'),
        ]

        for impression, display_order, guidelines in grading_labels:
            conn.execute(
                sa.text("""
                    INSERT INTO disease_gradings (disease_id, impression, display_order, guidelines, is_active)
                    VALUES (:disease_id, :impression, :display_order, :guidelines, TRUE)
                """),
                {"disease_id": strabismus_id, "impression": impression,
                 "display_order": display_order, "guidelines": guidelines}
            )


def downgrade() -> None:
    """Downgrade schema - remove Strabismus disease and its grading labels."""
    conn = op.get_bind()

    # Delete Strabismus grading labels first (foreign key constraint)
    conn.execute(
        sa.text("""
            DELETE FROM disease_gradings
            WHERE disease_id = (SELECT id FROM diseases WHERE name = 'Strabismus')
        """)
    )

    # Delete Strabismus disease
    conn.execute(
        sa.text("DELETE FROM diseases WHERE name = 'Strabismus'")
    )
