"""add monocular encounter metadata field

Revision ID: e4239b5d72ac
Revises: 6f2d8a9c1b47
Create Date: 2026-08-18 12:58:22.641055

"""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4239b5d72ac'
down_revision: Union[str, Sequence[str], None] = '6f2d8a9c1b47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    field_id = bind.execute(
        sa.text("SELECT id FROM upload_metadata_field_definitions WHERE key = :key"),
        {"key": "is_monocular"},
    ).scalar_one_or_none()
    if field_id is None:
        field_id = bind.execute(
            sa.text(
                """
                INSERT INTO upload_metadata_field_definitions
                    (scope, key, label, field_type, description,
                     required_at_upload_default, editable_during_verification_default,
                     visible_to_grader_default, is_pii_default, active, created_at, updated_at)
                VALUES
                    ('patient', :key, 'Patient is monocular', 'boolean',
                     'True only when the patient genuinely has one eye.',
                     false, true, false, true, true, now(), now())
                RETURNING id
                """
            ),
            {"key": "is_monocular"},
        ).scalar_one()

    row = bind.execute(
        sa.text("SELECT id, metadata_schema_json FROM encounter_set_types WHERE code = 'remidio_api_standard'")
    ).mappings().first()
    if row is not None:
        schema = row["metadata_schema_json"] or {"fields": []}
        fields = list(schema.get("fields") or [])
        if not any(field.get("key") == "is_monocular" for field in fields if isinstance(field, dict)):
            fields.append({
                "field_definition_id": field_id,
                "key": "is_monocular",
                "label": "Patient is monocular",
                "sctid": None,
                "scope": "patient",
                "type": "boolean",
                "display_order": max((int(field.get("display_order") or 0) for field in fields if isinstance(field, dict)), default=0) + 1,
                "selection_mode": None,
                "options": None,
                "description": "True only when the patient genuinely has one eye.",
                "validation_regex": None,
                "validation_error_message": None,
                "required_at_upload": False,
                "editable_during_verification": True,
                "visible_to_grader": False,
                "is_pii": True,
            })
            bind.execute(
                sa.text("UPDATE encounter_set_types SET metadata_schema_json = CAST(:schema AS jsonb) WHERE id = :id"),
                {"schema": json.dumps({**schema, "fields": fields}), "id": row["id"]},
            )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, metadata_schema_json FROM encounter_set_types")).mappings().all()
    for row in rows:
        schema = row["metadata_schema_json"] or {"fields": []}
        fields = [field for field in (schema.get("fields") or []) if field.get("key") != "is_monocular"]
        if len(fields) != len(schema.get("fields") or []):
            bind.execute(
                sa.text("UPDATE encounter_set_types SET metadata_schema_json = CAST(:schema AS jsonb) WHERE id = :id"),
                {"schema": json.dumps({**schema, "fields": fields}), "id": row["id"]},
            )
    bind.execute(
        sa.text("DELETE FROM upload_metadata_field_definitions WHERE key = :key"),
        {"key": "is_monocular"},
    )
