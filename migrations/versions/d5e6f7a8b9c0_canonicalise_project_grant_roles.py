"""canonicalise project grant roles

Project role grants were created with the historical names
``principal_investigator``, ``co_investigator`` and ``coordinator`` while
authorization policies are written against the canonical ``project_pi`` and
``collaborator``. That mismatch was being papered over by an alias table.
This converts the grants themselves so there is one set of role names, and
the aliasing can be removed.

Global user roles are untouched: no user holds any of these three names. The
legacy project_investigators table keeps its own names behind a check
constraint; every one of its rows already has a matching grant, so the
compatibility path that read it is removed rather than migrated.

Revision ID: d5e6f7a8b9c0
Revises: c2d3e4f5a6b7
Create Date: 2026-08-23

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# legacy name -> canonical name
CANONICAL = {
    "principal_investigator": "project_pi",
    "co_investigator": "collaborator",
    "coordinator": "collaborator",
}


def _role_ids(bind) -> dict[str, int]:
    rows = bind.execute(
        sa.text("SELECT name, id FROM roles WHERE name = ANY(:names)"),
        {"names": sorted(set(CANONICAL) | set(CANONICAL.values()))},
    ).fetchall()
    return {name: role_id for name, role_id in rows}


def upgrade() -> None:
    """Point every project role grant at its canonical role."""
    bind = op.get_bind()
    ids = _role_ids(bind)
    for legacy, canonical in CANONICAL.items():
        legacy_id, canonical_id = ids.get(legacy), ids.get(canonical)
        if legacy_id is None or canonical_id is None:
            continue
        # A user may already hold the canonical role on the same scope; drop
        # the legacy duplicate rather than violating the uniqueness of a grant.
        bind.execute(
            sa.text(
                """
                DELETE FROM project_role_grants legacy
                WHERE legacy.role_id = :legacy_id
                  AND EXISTS (
                    SELECT 1 FROM project_role_grants existing
                    WHERE existing.role_id = :canonical_id
                      AND existing.project_id = legacy.project_id
                      AND existing.user_id = legacy.user_id
                      AND existing.scope_type = legacy.scope_type
                      AND existing.hospital_id IS NOT DISTINCT FROM legacy.hospital_id
                      AND existing.lab_unit_id IS NOT DISTINCT FROM legacy.lab_unit_id
                  )
                """
            ),
            {"legacy_id": legacy_id, "canonical_id": canonical_id},
        )
        bind.execute(
            sa.text("UPDATE project_role_grants SET role_id = :canonical_id WHERE role_id = :legacy_id"),
            {"legacy_id": legacy_id, "canonical_id": canonical_id},
        )



def downgrade() -> None:
    """Restore the historical names.

    ``co_investigator`` and ``coordinator`` both mapped onto ``collaborator``,
    so that direction cannot be recovered exactly; every collaborator grant is
    returned to ``co_investigator``, which is the name all such grants
    carried before this migration.
    """
    bind = op.get_bind()
    ids = _role_ids(bind)
    pairs = [("project_pi", "principal_investigator"), ("collaborator", "co_investigator")]
    for canonical, legacy in pairs:
        canonical_id, legacy_id = ids.get(canonical), ids.get(legacy)
        if canonical_id is None or legacy_id is None:
            continue
        bind.execute(
            sa.text("UPDATE project_role_grants SET role_id = :legacy_id WHERE role_id = :canonical_id"),
            {"canonical_id": canonical_id, "legacy_id": legacy_id},
        )
