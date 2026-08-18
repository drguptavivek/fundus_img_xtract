"""Align MadhuNetrAI DME labels with the active local grade catalog.

Some existing databases use the concise DME impressions ``No DME`` and
``DME Present`` while newer seeded databases use the RDR-style M0/M1 labels.
The remote output mapping must reference impressions that actually exist in
the local catalog, so select the first active compatible impression without
overwriting unrelated/custom provider labels.

Revision ID: 32cbc2e0fe5f
Revises: e4239b5d72ac
Create Date: 2026-08-18 13:07:28.179891

"""
from typing import Sequence, Union

import json

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '32cbc2e0fe5f'
down_revision: Union[str, Sequence[str], None] = 'e4239b5d72ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Map each provider DME label to an active compatible local grade."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT target.id, target.label_mapping_json, target.disease_id
            FROM encounter_ai_output_targets AS target
            JOIN ai_models AS model ON model.id = target.ai_model_id
            WHERE target.target_key = 'dme'
              AND model.name = 'madhunetra_17aug2026'
              AND model.version = '17aug2026'
            """
        )
    ).mappings().all()

    for row in rows:
        mapping = dict(row["label_mapping_json"] or {})
        changed = False
        for provider_label, candidates in (
            ("No DME", ("No DME", "M0 No DME")),
            ("DME", ("DME Present", "M1 Referable Diabetic Maculopathy")),
        ):
            local_grade = bind.execute(
                sa.text(
                    """
                    SELECT impression
                    FROM disease_gradings
                    WHERE disease_id = :disease_id
                      AND is_active = true
                      AND impression = ANY(:candidates)
                    ORDER BY array_position(:candidates, impression)
                    LIMIT 1
                    """
                ),
                {"disease_id": row["disease_id"], "candidates": list(candidates)},
            ).scalar_one_or_none()
            if local_grade is not None and mapping.get(provider_label) != local_grade:
                mapping[provider_label] = local_grade
                changed = True
        if changed:
            bind.execute(
                sa.text(
                    """
                    UPDATE encounter_ai_output_targets
                    SET label_mapping_json = CAST(:mapping AS jsonb), updated_at = now()
                    WHERE id = :target_id
                    """
                ),
                {"mapping": json.dumps(mapping), "target_id": row["id"]},
            )


def downgrade() -> None:
    """Restore the original MadhuNetrAI DME seed mappings."""
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE encounter_ai_output_targets AS target
            SET label_mapping_json = jsonb_set(
                    jsonb_set(target.label_mapping_json, '{No DME}', to_jsonb('M0 No DME'::text)),
                    '{DME}',
                    to_jsonb('M1 Referable Diabetic Maculopathy'::text)
                ),
                updated_at = now()
            FROM ai_models AS model
            WHERE model.id = target.ai_model_id
              AND target.target_key = 'dme'
              AND model.name = 'madhunetra_17aug2026'
              AND model.version = '17aug2026'
              AND target.label_mapping_json ->> 'No DME' = 'No DME'
              AND target.label_mapping_json ->> 'DME' = 'DME Present'
            """
        )
    )
