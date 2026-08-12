"""synchronize EncounterSet image hospital custody

Revision ID: e3f4a5b6c7d8
Revises: da06b3c4d5e7
Create Date: 2026-08-12 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, Sequence[str], None] = "da06b3c4d5e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


IMAGE_TRIGGER = "trg_encounter_set_images_sync_hospital"
ENCOUNTER_TRIGGER = "trg_patient_encounters_sync_image_hospital"
IMAGE_FUNCTION = "sync_encounter_set_image_hospital"
ENCOUNTER_FUNCTION = "sync_encounter_set_images_for_encounter_lab"


def _required_tables_exist() -> bool:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    return {"encounter_set_images", "patient_encounters", "lab_units"}.issubset(tables)


def upgrade() -> None:
    if not _required_tables_exist():
        return

    # Repair every derivable row, including stale non-NULL values.
    op.execute(sa.text("""
        UPDATE encounter_set_images AS image
           SET hospital_id = lab.hospital_id
          FROM patient_encounters AS encounter
          JOIN lab_units AS lab ON lab.id = encounter.lab_unit_id
         WHERE image.patient_encounter_id = encounter.id
           AND image.hospital_id IS DISTINCT FROM lab.hospital_id
    """))

    # Make the database authoritative for direct image inserts/relocations.
    op.execute(sa.text(f"""
        CREATE OR REPLACE FUNCTION {IMAGE_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            SELECT lab.hospital_id
              INTO NEW.hospital_id
              FROM patient_encounters AS encounter
              JOIN lab_units AS lab ON lab.id = encounter.lab_unit_id
             WHERE encounter.id = NEW.patient_encounter_id;
            RETURN NEW;
        END;
        $$
    """))
    op.execute(sa.text(f"DROP TRIGGER IF EXISTS {IMAGE_TRIGGER} ON encounter_set_images"))
    op.execute(sa.text(f"""
        CREATE TRIGGER {IMAGE_TRIGGER}
        BEFORE INSERT OR UPDATE OF patient_encounter_id, hospital_id
        ON encounter_set_images
        FOR EACH ROW
        EXECUTE FUNCTION {IMAGE_FUNCTION}()
    """))

    # Keep existing child rows synchronized when an encounter changes lab custody.
    op.execute(sa.text(f"""
        CREATE OR REPLACE FUNCTION {ENCOUNTER_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            UPDATE encounter_set_images AS image
               SET hospital_id = lab.hospital_id
              FROM lab_units AS lab
             WHERE image.patient_encounter_id = NEW.id
               AND lab.id = NEW.lab_unit_id
               AND image.hospital_id IS DISTINCT FROM lab.hospital_id;
            RETURN NEW;
        END;
        $$
    """))
    op.execute(sa.text(f"DROP TRIGGER IF EXISTS {ENCOUNTER_TRIGGER} ON patient_encounters"))
    op.execute(sa.text(f"""
        CREATE TRIGGER {ENCOUNTER_TRIGGER}
        AFTER UPDATE OF lab_unit_id
        ON patient_encounters
        FOR EACH ROW
        WHEN (OLD.lab_unit_id IS DISTINCT FROM NEW.lab_unit_id)
        EXECUTE FUNCTION {ENCOUNTER_FUNCTION}()
    """))


def downgrade() -> None:
    if not _required_tables_exist():
        return
    op.execute(sa.text(f"DROP TRIGGER IF EXISTS {ENCOUNTER_TRIGGER} ON patient_encounters"))
    op.execute(sa.text(f"DROP TRIGGER IF EXISTS {IMAGE_TRIGGER} ON encounter_set_images"))
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS {ENCOUNTER_FUNCTION}()"))
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS {IMAGE_FUNCTION}()"))
