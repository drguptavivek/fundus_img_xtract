"""add maintained project_id to grading_tasks with resolver and guard triggers

Revision ID: 0d3edcf7bc3b
Revises: 5f0ea66fafb7
Create Date: 2026-08-25 17:25:45.300850

Owning project was previously derived at read time by outer-joining six source
tables and coalescing their ``project_id``. Every pending-count and queue query
paid that join, and the same precedence was duplicated in Python
(``grading_allocation.resolver._source_project_ids``) so tasks could be filtered
after loading. This denormalises the resolved value onto ``grading_tasks``.

Safety rests on one invariant: a task's owning project never changes after the
task exists. That already holds - ``remidio_encounter_migration.service`` is the
only path that reassigns an encounter's project, and it deletes the encounter's
grading tasks and packages *before* reassigning. The guard trigger added here
turns that ordering from a convention into an enforced constraint, so a future
caller cannot silently strand the denormalised value.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0d3edcf7bc3b'
down_revision: Union[str, Sequence[str], None] = '5f0ea66fafb7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Same six sources, in the same precedence, as
# grading_allocation.resolver._source_project_ids.
RESOLVE_SQL = """
CREATE OR REPLACE FUNCTION grading_task_resolve_project_id(
    p_patient_encounter_id integer,
    p_encounter_set_image_id integer,
    p_encounter_file_id integer,
    p_direct_image_upload_id integer
) RETURNS integer
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(
        (SELECT project_id FROM patient_encounters WHERE id = p_patient_encounter_id),
        (SELECT project_id FROM encounter_set_images WHERE id = p_encounter_set_image_id),
        (SELECT pe.project_id FROM encounter_set_images si
            JOIN patient_encounters pe ON pe.id = si.patient_encounter_id
            WHERE si.id = p_encounter_set_image_id),
        (SELECT project_id FROM encounter_files WHERE id = p_encounter_file_id),
        (SELECT pe.project_id FROM encounter_files ef
            JOIN patient_encounters pe ON pe.id = ef.patient_encounter_id
            WHERE ef.id = p_encounter_file_id),
        (SELECT project_id FROM direct_image_uploads WHERE id = p_direct_image_upload_id)
    );
$$;
"""

APPLY_SQL = """
CREATE OR REPLACE FUNCTION grading_tasks_apply_project_id()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.project_id := grading_task_resolve_project_id(
        NEW.patient_encounter_id,
        NEW.encounter_set_image_id,
        NEW.encounter_file_id,
        NEW.direct_image_upload_id
    );
    RETURN NEW;
END;
$$;
"""

# Refuses to move a source row to a different project while grading tasks still
# reference it. Callers must delete or re-home the tasks first, which is what
# the Remidio encounter migration already does.
GUARD_SQL = """
CREATE OR REPLACE FUNCTION grading_source_project_change_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_tasks integer;
BEGIN
    IF NEW.project_id IS NOT DISTINCT FROM OLD.project_id THEN
        RETURN NEW;
    END IF;

    IF TG_TABLE_NAME = 'patient_encounters' THEN
        SELECT count(*) INTO v_tasks FROM grading_tasks t
        WHERE t.patient_encounter_id = OLD.id
           OR t.encounter_set_image_id IN (
                SELECT id FROM encounter_set_images WHERE patient_encounter_id = OLD.id)
           OR t.encounter_file_id IN (
                SELECT id FROM encounter_files WHERE patient_encounter_id = OLD.id);
    ELSIF TG_TABLE_NAME = 'encounter_set_images' THEN
        SELECT count(*) INTO v_tasks FROM grading_tasks t
        WHERE t.encounter_set_image_id = OLD.id;
    ELSIF TG_TABLE_NAME = 'encounter_files' THEN
        SELECT count(*) INTO v_tasks FROM grading_tasks t
        WHERE t.encounter_file_id = OLD.id;
    ELSIF TG_TABLE_NAME = 'direct_image_uploads' THEN
        SELECT count(*) INTO v_tasks FROM grading_tasks t
        WHERE t.direct_image_upload_id = OLD.id;
    ELSE
        v_tasks := 0;
    END IF;

    IF v_tasks > 0 THEN
        RAISE EXCEPTION
            'Cannot change %.project_id (id=%) while % grading task(s) reference it; '
            'delete or re-home the tasks first.',
            TG_TABLE_NAME, OLD.id, v_tasks
            USING ERRCODE = 'raise_exception';
    END IF;

    RETURN NEW;
END;
$$;
"""

GUARDED_TABLES = (
    "patient_encounters",
    "encounter_set_images",
    "encounter_files",
    "direct_image_uploads",
)


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    columns = {col["name"] for col in inspector.get_columns("grading_tasks")}
    if "project_id" not in columns:
        op.add_column(
            "grading_tasks",
            sa.Column("project_id", sa.Integer(), nullable=True),
        )

    fks = {fk.get("name") for fk in inspector.get_foreign_keys("grading_tasks")}
    if "fk_grading_tasks_project_id" not in fks:
        op.create_foreign_key(
            "fk_grading_tasks_project_id",
            "grading_tasks",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.execute(sa.text(RESOLVE_SQL))
    op.execute(sa.text(APPLY_SQL))
    op.execute(sa.text(GUARD_SQL))

    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_grading_tasks_apply_project_id ON grading_tasks"
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_grading_tasks_apply_project_id
            BEFORE INSERT OR UPDATE OF
                patient_encounter_id, encounter_set_image_id,
                encounter_file_id, direct_image_upload_id
            ON grading_tasks
            FOR EACH ROW
            EXECUTE FUNCTION grading_tasks_apply_project_id()
            """
        )
    )

    for table in GUARDED_TABLES:
        op.execute(
            sa.text(
                f"DROP TRIGGER IF EXISTS trg_{table}_project_change_guard ON {table}"
            )
        )
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER trg_{table}_project_change_guard
                BEFORE UPDATE OF project_id ON {table}
                FOR EACH ROW
                EXECUTE FUNCTION grading_source_project_change_guard()
                """
            )
        )

    # Backfill existing rows through the same resolver the trigger uses.
    op.execute(
        sa.text(
            """
            UPDATE grading_tasks
               SET project_id = grading_task_resolve_project_id(
                       patient_encounter_id, encounter_set_image_id,
                       encounter_file_id, direct_image_upload_id)
             WHERE project_id IS DISTINCT FROM grading_task_resolve_project_id(
                       patient_encounter_id, encounter_set_image_id,
                       encounter_file_id, direct_image_upload_id)
            """
        )
    )

    indexes = {ix["name"] for ix in inspector.get_indexes("grading_tasks")}
    if "ix_grading_tasks_project_disease_lab_state" not in indexes:
        op.create_index(
            "ix_grading_tasks_project_disease_lab_state",
            "grading_tasks",
            ["project_id", "disease_id", "lab_unit_id", "state"],
        )


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    for table in GUARDED_TABLES:
        op.execute(
            sa.text(
                f"DROP TRIGGER IF EXISTS trg_{table}_project_change_guard ON {table}"
            )
        )
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_grading_tasks_apply_project_id ON grading_tasks"
        )
    )
    op.execute(sa.text("DROP FUNCTION IF EXISTS grading_source_project_change_guard()"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS grading_tasks_apply_project_id()"))
    op.execute(
        sa.text(
            "DROP FUNCTION IF EXISTS grading_task_resolve_project_id("
            "integer, integer, integer, integer)"
        )
    )

    indexes = {ix["name"] for ix in inspector.get_indexes("grading_tasks")}
    if "ix_grading_tasks_project_disease_lab_state" in indexes:
        op.drop_index(
            "ix_grading_tasks_project_disease_lab_state",
            table_name="grading_tasks",
        )

    fks = {fk.get("name") for fk in inspector.get_foreign_keys("grading_tasks")}
    if "fk_grading_tasks_project_id" in fks:
        op.drop_constraint(
            "fk_grading_tasks_project_id", "grading_tasks", type_="foreignkey"
        )

    columns = {col["name"] for col in inspector.get_columns("grading_tasks")}
    if "project_id" in columns:
        op.drop_column("grading_tasks", "project_id")
