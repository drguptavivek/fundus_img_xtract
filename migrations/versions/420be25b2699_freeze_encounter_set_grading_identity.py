"""freeze encounter set grading identity

Revision ID: 420be25b2699
Revises: 1b2c3d4e5f60
Create Date: 2026-08-10 09:59:34.326391

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '420be25b2699'
down_revision: Union[str, Sequence[str], None] = '1b2c3d4e5f60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def _constraints(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(table)
        if constraint.get("name")
    }


def _indexes(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {
        index["name"]
        for index in inspector.get_indexes(table)
        if index.get("name")
    }


def _foreign_keys(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {
        foreign_key["name"]
        for foreign_key in inspector.get_foreign_keys(table)
        if foreign_key.get("name")
    }


def upgrade() -> None:
    """Freeze allocation identity and permit package-owned target identities."""
    if "encounter_set_type_id" not in _columns("encounter_set_grading_packages"):
        op.add_column(
            "encounter_set_grading_packages",
            sa.Column("encounter_set_type_id", sa.Integer(), nullable=True),
        )
    if "fk_es_grading_package_encounter_set_type" not in _foreign_keys(
        "encounter_set_grading_packages"
    ):
        op.create_foreign_key(
            "fk_es_grading_package_encounter_set_type",
            "encounter_set_grading_packages",
            "encounter_set_types",
            ["encounter_set_type_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    if "ix_encounter_set_grading_packages_encounter_set_type_id" not in _indexes(
        "encounter_set_grading_packages"
    ):
        op.create_index(
            "ix_encounter_set_grading_packages_encounter_set_type_id",
            "encounter_set_grading_packages",
            ["encounter_set_type_id"],
        )

    op.execute(sa.text("""
        UPDATE encounter_set_grading_packages runtime
        SET encounter_set_type_id = profile_type.encounter_set_type_id,
            policy_snapshot_json = jsonb_set(
                COALESCE(runtime.policy_snapshot_json, '{}'::jsonb),
                '{encounter_set_type}',
                jsonb_build_object(
                    'id', encounter_type.id,
                    'name', encounter_type.name,
                    'code', encounter_type.code
                ),
                true
            )
        FROM upload_profile_est_grading_packages policy
        JOIN upload_profile_encounter_set_types profile_type
          ON profile_type.id = policy.upload_profile_encounter_set_type_id
        JOIN encounter_set_types encounter_type
          ON encounter_type.id = profile_type.encounter_set_type_id
        WHERE runtime.upload_profile_est_grading_package_id = policy.id
          AND (
              runtime.encounter_set_type_id IS NULL
              OR runtime.policy_snapshot_json->'encounter_set_type' IS NULL
          )
    """))

    for constraint_name in (
        "uq_task_patient_encounter_disease",
        "uq_task_encounter_set_image_disease",
        "uq_task_encounter_set_package_target",
    ):
        if constraint_name in _constraints("grading_tasks"):
            op.drop_constraint(constraint_name, "grading_tasks", type_="unique")

    indexes = _indexes("grading_tasks")
    index_definitions = (
        (
            "uq_task_patient_encounter_disease_unscoped",
            ["patient_encounter_id", "disease_id"],
            "encounter_set_package_id IS NULL AND patient_encounter_id IS NOT NULL",
        ),
        (
            "uq_task_encounter_set_image_disease_unscoped",
            ["encounter_set_image_id", "disease_id"],
            "encounter_set_package_id IS NULL AND encounter_set_image_id IS NOT NULL",
        ),
        (
            "uq_task_package_encounter_target",
            [
                "encounter_set_package_id",
                "patient_encounter_id",
                "disease_id",
                "grading_target_level",
            ],
            "encounter_set_package_id IS NOT NULL AND patient_encounter_id IS NOT NULL",
        ),
        (
            "uq_task_package_image_target",
            [
                "encounter_set_package_id",
                "encounter_set_image_id",
                "disease_id",
                "grading_target_level",
            ],
            "encounter_set_package_id IS NOT NULL AND encounter_set_image_id IS NOT NULL",
        ),
    )
    for name, columns, predicate in index_definitions:
        if name not in indexes:
            op.create_index(
                name,
                "grading_tasks",
                columns,
                unique=True,
                postgresql_where=sa.text(predicate),
            )

    # Records created by the previous immediate-consensus implementation must
    # re-enter the protected Resident2 revision period when it is still open.
    op.execute(sa.text("""
        DELETE FROM consensus consensus_row
        USING grading_tasks task, encounter_set_grading_submissions resident2_event
        WHERE consensus_row.task_id = task.id
          AND task.encounter_set_package_id = resident2_event.encounter_set_package_id
          AND consensus_row.method = 'match'
          AND resident2_event.role_slot = 'resident2'
          AND resident2_event.submission_kind = 'initial'
          AND resident2_event.created_at > now() - interval '12 hours'
    """))
    op.execute(sa.text("""
        UPDATE encounter_set_grading_scopes scope
        SET state = 'resident2_done', updated_at = now()
        FROM encounter_set_grading_submissions resident2_event
        WHERE resident2_event.encounter_set_package_id = scope.encounter_set_package_id
          AND resident2_event.role_slot = 'resident2'
          AND resident2_event.submission_kind = 'initial'
          AND resident2_event.created_at > now() - interval '12 hours'
          AND NOT EXISTS (
              SELECT 1
              FROM grading_tasks task
              JOIN grades grade ON grade.task_id = task.id
              WHERE task.encounter_set_scope_id = scope.id
                AND grade.role_slot = 'arbitrator'
          )
    """))
    op.execute(sa.text("""
        UPDATE grading_tasks task
        SET state = 'resident2_done'
        FROM encounter_set_grading_scopes scope
        WHERE task.encounter_set_scope_id = scope.id
          AND scope.state = 'resident2_done'
    """))
    op.execute(sa.text("""
        UPDATE encounter_set_grading_packages package
        SET state = 'resident2_done', completed_at = NULL, updated_at = now(),
            revision_number = revision_number + 1
        WHERE EXISTS (
            SELECT 1 FROM encounter_set_grading_scopes scope
            WHERE scope.encounter_set_package_id = package.id
              AND scope.state = 'resident2_done'
        )
    """))


def downgrade() -> None:
    """Remove frozen identity while preserving package-owned task data."""
    for name in (
        "uq_task_package_image_target",
        "uq_task_package_encounter_target",
        "uq_task_encounter_set_image_disease_unscoped",
        "uq_task_patient_encounter_disease_unscoped",
    ):
        if name in _indexes("grading_tasks"):
            op.drop_index(name, table_name="grading_tasks")

    # Restore the former global constraints only when post-upgrade data does
    # not contain valid cross-package duplicates that they cannot represent.
    duplicate_encounters = op.get_bind().execute(sa.text("""
        SELECT 1 FROM grading_tasks
        WHERE patient_encounter_id IS NOT NULL
        GROUP BY patient_encounter_id, disease_id HAVING count(*) > 1 LIMIT 1
    """)).scalar()
    duplicate_images = op.get_bind().execute(sa.text("""
        SELECT 1 FROM grading_tasks
        WHERE encounter_set_image_id IS NOT NULL
        GROUP BY encounter_set_image_id, disease_id HAVING count(*) > 1 LIMIT 1
    """)).scalar()
    if not duplicate_encounters:
        op.create_unique_constraint(
            "uq_task_patient_encounter_disease",
            "grading_tasks",
            ["patient_encounter_id", "disease_id"],
        )
    if not duplicate_images:
        op.create_unique_constraint(
            "uq_task_encounter_set_image_disease",
            "grading_tasks",
            ["encounter_set_image_id", "disease_id"],
        )

    if "encounter_set_type_id" in _columns("encounter_set_grading_packages"):
        if "ix_encounter_set_grading_packages_encounter_set_type_id" in _indexes(
            "encounter_set_grading_packages"
        ):
            op.drop_index(
                "ix_encounter_set_grading_packages_encounter_set_type_id",
                table_name="encounter_set_grading_packages",
            )
        if "fk_es_grading_package_encounter_set_type" in _foreign_keys(
            "encounter_set_grading_packages"
        ):
            op.drop_constraint(
                "fk_es_grading_package_encounter_set_type",
                "encounter_set_grading_packages",
                type_="foreignkey",
            )
        op.drop_column("encounter_set_grading_packages", "encounter_set_type_id")
