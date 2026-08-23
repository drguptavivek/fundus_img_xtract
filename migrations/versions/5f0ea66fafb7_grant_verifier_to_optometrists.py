"""grant verifier to optometrists

Verification was conferred by the `optometrist` role. It now has a role of
its own, so every active optometrist receives `verifier` and `optometrist`
stops conferring verification in the same change. Nobody gains or loses the
ability to verify on the day this runs.

`optometrist` keeps its other powers, such as uploads and WAI runs.

Revision ID: 5f0ea66fafb7
Revises: d5e6f7a8b9c0
Create Date: 2026-08-23

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "5f0ea66fafb7"
down_revision: Union[str, Sequence[str], None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Give every active optometrist the verifier role."""
    bind = op.get_bind()
    bind.execute(sa.text(
        "INSERT INTO roles (name) SELECT 'verifier' "
        "WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'verifier')"
    ))
    bind.execute(sa.text(
        """
        INSERT INTO user_roles (user_id, role_id)
        SELECT ur.user_id, (SELECT id FROM roles WHERE name = 'verifier')
        FROM user_roles ur
        JOIN roles r ON r.id = ur.role_id
        JOIN users u ON u.id = ur.user_id
        WHERE r.name = 'optometrist'
          AND u.is_active
          AND NOT EXISTS (
            SELECT 1 FROM user_roles existing
            JOIN roles vr ON vr.id = existing.role_id
            WHERE existing.user_id = ur.user_id AND vr.name = 'verifier'
          )
        """
    ))


def downgrade() -> None:
    """Remove verifier from users who hold it only by way of this grant.

    A user who also holds optometrist had verifier assigned here, so the
    assignment is withdrawn. Anyone granted verifier independently, without
    optometrist, keeps it.
    """
    bind = op.get_bind()
    bind.execute(sa.text(
        """
        DELETE FROM user_roles
        WHERE role_id = (SELECT id FROM roles WHERE name = 'verifier')
          AND user_id IN (
            SELECT ur.user_id FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            WHERE r.name = 'optometrist'
          )
        """
    ))
