"""persist encounter set grading scopes

Revision ID: 005758850601
Revises: 59822efe899b
Create Date: 2026-08-10 04:53:18.728198
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "005758850601"
down_revision: Union[str, Sequence[str], None] = "59822efe899b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def _indexes(table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}


def _constraints(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    rows = (
        inspector.get_check_constraints(table)
        + inspector.get_unique_constraints(table)
        + inspector.get_foreign_keys(table)
    )
    return {item.get("name") for item in rows if item.get("name")}


def _add_column(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def _create_index(name: str, table: str, columns: list[str], *, unique: bool = False) -> None:
    if name not in _indexes(table):
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    _add_column("upload_profile_est_grading_packages", sa.Column("policy_revision", sa.Integer(), server_default="1", nullable=False))
    _add_column("upload_profile_est_grading_packages", sa.Column("scope_config_json", postgresql.JSONB(), nullable=True))

    for column in (
        sa.Column("root_scope_disease_id", sa.Integer(), nullable=True),
        sa.Column("policy_schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("policy_revision", sa.Integer(), nullable=True),
        sa.Column("policy_snapshot_json", postgresql.JSONB(), nullable=True),
        sa.Column("record_origin", sa.String(32), server_default="native", nullable=False),
        sa.Column("revision_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("resident_user_id", sa.Integer(), nullable=True),
        sa.Column("resident2_user_id", sa.Integer(), nullable=True),
        sa.Column("arbitrator_user_id", sa.Integer(), nullable=True),
    ):
        _add_column("encounter_set_grading_packages", column)

    package_constraints = _constraints("encounter_set_grading_packages")
    if "ck_encounter_set_grading_package_origin" not in package_constraints:
        op.create_check_constraint(
            "ck_encounter_set_grading_package_origin",
            "encounter_set_grading_packages",
            "record_origin IN ('native','legacy_reconstructed','legacy_partial')",
        )
    for name, local, remote, ondelete in (
        ("fk_esgp_root_scope_disease", "root_scope_disease_id", "diseases", "RESTRICT"),
        ("fk_esgp_resident_user", "resident_user_id", "users", "SET NULL"),
        ("fk_esgp_resident2_user", "resident2_user_id", "users", "SET NULL"),
        ("fk_esgp_arbitrator_user", "arbitrator_user_id", "users", "SET NULL"),
    ):
        if name not in package_constraints:
            op.create_foreign_key(name, "encounter_set_grading_packages", remote, [local], ["id"], ondelete=ondelete)
    for column in ("root_scope_disease_id", "resident_user_id", "resident2_user_id", "arbitrator_user_id"):
        _create_index(f"ix_encounter_set_grading_packages_{column}", "encounter_set_grading_packages", [column])

    if not _has_table("encounter_set_grading_scopes"):
        op.create_table(
            "encounter_set_grading_scopes",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("uuid", sa.String(36), nullable=False),
            sa.Column("encounter_set_package_id", sa.Integer(), nullable=False),
            sa.Column("scope_disease_id", sa.Integer(), nullable=True),
            sa.Column("image_grading_scheme_id", sa.Integer(), nullable=True),
            sa.Column("encounter_grading_scheme_id", sa.Integer(), nullable=False),
            sa.Column("parent_scope_disease_id", sa.Integer(), nullable=True),
            sa.Column("link_role", sa.String(16), server_default="root", nullable=False),
            sa.Column("state", sa.String(24), server_default="pending", nullable=False),
            sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
            sa.Column("scope_snapshot_json", postgresql.JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["encounter_set_package_id"], ["encounter_set_grading_packages.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["scope_disease_id"], ["diseases.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["image_grading_scheme_id"], ["diseases.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["encounter_grading_scheme_id"], ["diseases.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["parent_scope_disease_id"], ["diseases.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("encounter_set_package_id", "scope_disease_id", name="uq_es_grading_scope_package_disease"),
            sa.CheckConstraint("link_role IN ('root','linked','unified')", name="ck_es_grading_scope_link_role"),
            sa.CheckConstraint("state IN ('pending','resident_done','resident2_done','arbitration','final')", name="ck_es_grading_scope_state"),
        )
    for column in ("uuid", "encounter_set_package_id", "scope_disease_id", "image_grading_scheme_id", "encounter_grading_scheme_id", "parent_scope_disease_id", "state"):
        _create_index(
            f"ix_encounter_set_grading_scopes_{column}",
            "encounter_set_grading_scopes",
            [column],
            unique=column == "uuid",
        )

    _add_column("grading_tasks", sa.Column("encounter_set_scope_id", sa.Integer(), nullable=True))
    if "fk_grading_tasks_encounter_set_scope" not in _constraints("grading_tasks"):
        op.create_foreign_key(
            "fk_grading_tasks_encounter_set_scope",
            "grading_tasks",
            "encounter_set_grading_scopes",
            ["encounter_set_scope_id"],
            ["id"],
            ondelete="CASCADE",
        )
    _create_index("ix_grading_tasks_encounter_set_scope_id", "grading_tasks", ["encounter_set_scope_id"])

    for column in (
        sa.Column("consensus_scope", sa.String(32), server_default="image", nullable=False),
        sa.Column("encounter_set_package_id", sa.Integer(), nullable=True),
        sa.Column("encounter_set_scope_id", sa.Integer(), nullable=True),
        sa.Column("scope_disease_id", sa.Integer(), nullable=True),
        sa.Column("scope_disease_name", sa.String(255), nullable=True),
    ):
        _add_column("consensus", column)
    consensus_constraints = _constraints("consensus")
    for name, remote, local in (
        ("fk_consensus_es_package", "encounter_set_grading_packages", "encounter_set_package_id"),
        ("fk_consensus_es_scope", "encounter_set_grading_scopes", "encounter_set_scope_id"),
        ("fk_consensus_scope_disease", "diseases", "scope_disease_id"),
    ):
        if name not in consensus_constraints:
            op.create_foreign_key(name, "consensus", remote, [local], ["id"], ondelete="SET NULL")
    if "ck_consensus_scope_valid" not in consensus_constraints:
        op.create_check_constraint("ck_consensus_scope_valid", "consensus", "consensus_scope IN ('image','encounter_set_unified','encounter_set_disease')")
    if "ck_consensus_disease_scope_present" not in consensus_constraints:
        op.create_check_constraint("ck_consensus_disease_scope_present", "consensus", "consensus_scope <> 'encounter_set_disease' OR scope_disease_id IS NOT NULL")
    for column in ("consensus_scope", "encounter_set_package_id", "encounter_set_scope_id", "scope_disease_id"):
        _create_index(f"ix_consensus_{column}", "consensus", [column])

    _create_submission_tables()
    _backfill_policy_configs()
    _backfill_runtime_records()


def _create_submission_tables() -> None:
    if not _has_table("encounter_set_grading_submissions"):
        op.create_table(
            "encounter_set_grading_submissions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("uuid", sa.String(36), nullable=False),
            sa.Column("encounter_set_package_id", sa.Integer(), nullable=False),
            sa.Column("grader_user_id", sa.Integer(), nullable=False),
            sa.Column("role_slot", sa.String(16), nullable=False),
            sa.Column("submission_kind", sa.String(16), server_default="initial", nullable=False),
            sa.Column("package_revision", sa.Integer(), nullable=False),
            sa.Column("is_complete", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("source", sa.String(32), server_default="native", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["encounter_set_package_id"], ["encounter_set_grading_packages.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["grader_user_id"], ["users.id"], ondelete="RESTRICT"),
            sa.CheckConstraint("role_slot IN ('resident','resident2','arbitrator')", name="ck_es_grading_submission_role"),
            sa.CheckConstraint("submission_kind IN ('initial','revision','legacy_import')", name="ck_es_grading_submission_kind"),
            sa.CheckConstraint("source IN ('native','legacy_backfill')", name="ck_es_grading_submission_source"),
        )
    for column in ("uuid", "encounter_set_package_id", "grader_user_id", "role_slot", "created_at"):
        _create_index(f"ix_encounter_set_grading_submissions_{column}", "encounter_set_grading_submissions", [column], unique=column == "uuid")

    if not _has_table("encounter_set_grading_submission_items"):
        op.create_table(
            "encounter_set_grading_submission_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("submission_id", sa.Integer(), nullable=False),
            sa.Column("encounter_set_scope_id", sa.Integer(), nullable=True),
            sa.Column("task_id", sa.Integer(), nullable=False),
            sa.Column("grade_id", sa.Integer(), nullable=True),
            sa.Column("target_level", sa.String(24), nullable=False),
            sa.Column("scope_kind", sa.String(32), nullable=False),
            sa.Column("scope_disease_id", sa.Integer(), nullable=True),
            sa.Column("scope_disease_name", sa.String(255), nullable=True),
            sa.Column("disease_grading_id", sa.Integer(), nullable=False),
            sa.Column("grade_name", sa.String(64), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("selected_features_json", sa.Text(), nullable=True),
            sa.Column("feature_geometry_json", postgresql.JSONB(), nullable=True),
            sa.Column("target_snapshot_json", postgresql.JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["submission_id"], ["encounter_set_grading_submissions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["encounter_set_scope_id"], ["encounter_set_grading_scopes.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["task_id"], ["grading_tasks.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["grade_id"], ["grades.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["scope_disease_id"], ["diseases.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["disease_grading_id"], ["disease_gradings.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("submission_id", "task_id", name="uq_es_grading_submission_item_task"),
            sa.CheckConstraint("target_level IN ('image','encounter')", name="ck_es_grading_submission_item_target"),
            sa.CheckConstraint("scope_kind IN ('encounter_set_unified','encounter_set_disease')", name="ck_es_grading_submission_item_scope"),
        )
    for name, column in (
        ("ix_esgsi_submission", "submission_id"),
        ("ix_esgsi_scope", "encounter_set_scope_id"),
        ("ix_esgsi_task", "task_id"),
        ("ix_esgsi_grade", "grade_id"),
        ("ix_esgsi_scope_disease", "scope_disease_id"),
    ):
        _create_index(name, "encounter_set_grading_submission_items", [column])


def _backfill_policy_configs() -> None:
    op.execute(sa.text("""
        UPDATE upload_profile_est_grading_packages p
        SET scope_config_json = CASE
          WHEN p.grading_mode = 'unified' THEN jsonb_build_object(
            'schema_version', 1,
            'root_image_grading_scheme_id', NULL,
            'scopes', jsonb_build_array(jsonb_build_object(
              'scope_disease_id', NULL,
              'image_grading_scheme_ids', COALESCE((
                SELECT jsonb_agg(i.disease_id ORDER BY i.display_order, i.id)
                FROM upload_profile_est_package_image_schemes i
                WHERE i.package_id = p.id AND i.active
              ), '[]'::jsonb),
              'encounter_grading_scheme_id', (
                SELECT e.disease_id FROM upload_profile_est_package_encounter_schemes e
                WHERE e.package_id = p.id AND e.active ORDER BY e.display_order, e.id LIMIT 1
              ),
              'parent_scope_disease_id', NULL,
              'link_role', 'unified'
            ))
          )
          ELSE jsonb_build_object(
            'schema_version', 1,
            'root_image_grading_scheme_id', (
              SELECT i.disease_id FROM upload_profile_est_package_image_schemes i
              WHERE i.package_id = p.id AND i.active ORDER BY i.display_order, i.id LIMIT 1
            ),
            'scopes', jsonb_build_array(jsonb_build_object(
              'scope_disease_id', (
                SELECT i.disease_id FROM upload_profile_est_package_image_schemes i
                WHERE i.package_id = p.id AND i.active ORDER BY i.display_order, i.id LIMIT 1
              ),
              'image_grading_scheme_ids', jsonb_build_array((
                SELECT i.disease_id FROM upload_profile_est_package_image_schemes i
                WHERE i.package_id = p.id AND i.active ORDER BY i.display_order, i.id LIMIT 1
              )),
              'encounter_grading_scheme_id', (
                SELECT e.disease_id FROM upload_profile_est_package_encounter_schemes e
                WHERE e.package_id = p.id AND e.active ORDER BY e.display_order, e.id LIMIT 1
              ),
              'parent_scope_disease_id', NULL,
              'link_role', 'root'
            ))
          )
        END
        WHERE p.scope_config_json IS NULL
          AND (SELECT count(*) FROM upload_profile_est_package_encounter_schemes e WHERE e.package_id = p.id AND e.active) = 1
          AND (p.grading_mode = 'unified' OR (
            SELECT count(*) FROM upload_profile_est_package_image_schemes i WHERE i.package_id = p.id AND i.active
          ) = 1)
    """))


def _backfill_runtime_records() -> None:
    op.execute(sa.text("""
        UPDATE encounter_set_grading_packages p
        SET record_origin = CASE
          WHEN (SELECT count(*) FROM grading_tasks t WHERE t.encounter_set_package_id = p.id AND t.grading_target_level = 'encounter') = 1
            THEN 'legacy_reconstructed'
          ELSE 'legacy_partial'
        END
        WHERE p.policy_snapshot_json IS NULL
    """))
    op.execute(sa.text("""
        INSERT INTO encounter_set_grading_scopes (
          uuid, encounter_set_package_id, scope_disease_id,
          image_grading_scheme_id, encounter_grading_scheme_id,
          parent_scope_disease_id, link_role, state, display_order,
          scope_snapshot_json, created_at, updated_at
        )
        SELECT gen_random_uuid()::text, p.id,
          CASE WHEN p.grading_mode = 'disease_specific' THEN image_task.disease_id ELSE NULL END,
          CASE WHEN p.grading_mode = 'disease_specific' THEN image_task.disease_id ELSE NULL END,
          encounter_task.disease_id, NULL,
          CASE WHEN p.grading_mode = 'disease_specific' THEN 'root' ELSE 'unified' END,
          p.state, 0,
          jsonb_build_object(
            'scope_disease_id', CASE WHEN p.grading_mode = 'disease_specific' THEN image_task.disease_id ELSE NULL END,
            'image_grading_scheme_ids', CASE WHEN image_task.disease_id IS NULL THEN '[]'::jsonb ELSE jsonb_build_array(image_task.disease_id) END,
            'encounter_grading_scheme_id', encounter_task.disease_id,
            'parent_scope_disease_id', NULL,
            'link_role', CASE WHEN p.grading_mode = 'disease_specific' THEN 'root' ELSE 'unified' END
          ), p.created_at, p.updated_at
        FROM encounter_set_grading_packages p
        JOIN LATERAL (
          SELECT min(t.disease_id) AS disease_id
          FROM grading_tasks t
          WHERE t.encounter_set_package_id = p.id AND t.grading_target_level = 'encounter'
          HAVING count(*) = 1
        ) encounter_task ON true
        LEFT JOIN LATERAL (
          SELECT min(t.disease_id) AS disease_id
          FROM grading_tasks t
          WHERE t.encounter_set_package_id = p.id AND t.grading_target_level = 'image'
          HAVING count(DISTINCT t.disease_id) <= 1
        ) image_task ON true
        WHERE NOT EXISTS (
          SELECT 1 FROM encounter_set_grading_scopes s WHERE s.encounter_set_package_id = p.id
        )
          AND (p.grading_mode = 'unified' OR image_task.disease_id IS NOT NULL)
    """))
    op.execute(sa.text("""
        UPDATE grading_tasks t
        SET encounter_set_scope_id = s.id
        FROM encounter_set_grading_scopes s
        WHERE t.encounter_set_package_id = s.encounter_set_package_id
          AND t.encounter_set_scope_id IS NULL
          AND (s.scope_disease_id IS NULL OR t.grading_target_level = 'encounter' OR t.disease_id = s.scope_disease_id)
    """))
    op.execute(sa.text("""
        UPDATE encounter_set_grading_packages p
        SET root_scope_disease_id = s.scope_disease_id
        FROM encounter_set_grading_scopes s
        WHERE s.encounter_set_package_id = p.id AND s.link_role = 'root'
          AND p.root_scope_disease_id IS NULL
    """))
    for role_slot, owner_column in (
        ("resident", "resident_user_id"),
        ("resident2", "resident2_user_id"),
        ("arbitrator", "arbitrator_user_id"),
    ):
        op.execute(sa.text(f"""
            UPDATE encounter_set_grading_packages p
            SET {owner_column} = owners.grader_user_id
            FROM (
              SELECT t.encounter_set_package_id, min(g.grader_user_id) AS grader_user_id
              FROM grading_tasks t JOIN grades g ON g.task_id = t.id
              WHERE g.role_slot = :role_slot AND t.encounter_set_package_id IS NOT NULL
              GROUP BY t.encounter_set_package_id
              HAVING count(DISTINCT g.grader_user_id) = 1
            ) owners
            WHERE owners.encounter_set_package_id = p.id AND p.{owner_column} IS NULL
        """).bindparams(role_slot=role_slot))
    op.execute(sa.text("""
        UPDATE encounter_set_grading_packages p
        SET policy_snapshot_json = jsonb_build_object(
          'schema_version', 1,
          'policy_revision', NULL,
          'package', jsonb_build_object(
            'config_id', p.upload_profile_est_grading_package_id,
            'name', p.name, 'code', p.code,
            'applicability', p.applicability,
            'grading_mode', p.grading_mode,
            'root_scope_disease_id', p.root_scope_disease_id,
            'source', COALESCE(p.metadata_json->>'source', 'legacy')
          ),
          'grading_definitions', COALESCE((
            SELECT jsonb_object_agg(definition.disease_id::text, definition.payload)
            FROM (
              SELECT d.id AS disease_id, jsonb_build_object(
                'id', d.id, 'name', d.name, 'grading_scope', d.grading_scope,
                'labels', COALESCE((
                  SELECT jsonb_agg(jsonb_build_object(
                    'id', dg.id, 'impression', dg.impression,
                    'guidelines', dg.guidelines, 'is_ungradable', dg.is_ungradable,
                    'display_order', dg.display_order,
                    'features', COALESCE((
                      SELECT jsonb_agg(jsonb_build_object(
                        'id', gf.id, 'label', gf.label, 'display_order', gf.sr_no
                      ) ORDER BY gf.sr_no, gf.id)
                      FROM gradings_features gf WHERE gf.disease_grading_id = dg.id
                    ), '[]'::jsonb)
                  ) ORDER BY dg.display_order, dg.id)
                  FROM disease_gradings dg WHERE dg.disease_id = d.id
                ), '[]'::jsonb)
              ) AS payload
              FROM diseases d
              WHERE d.id IN (
                SELECT DISTINCT t.disease_id FROM grading_tasks t WHERE t.encounter_set_package_id = p.id
              )
            ) definition
          ), '{}'::jsonb)
        )
        WHERE p.policy_snapshot_json IS NULL
    """))


def downgrade() -> None:
    for table in ("encounter_set_grading_submission_items", "encounter_set_grading_submissions"):
        if _has_table(table):
            op.drop_table(table)
    if "encounter_set_scope_id" in _columns("grading_tasks"):
        op.drop_column("grading_tasks", "encounter_set_scope_id")
    for column in ("scope_disease_name", "scope_disease_id", "encounter_set_scope_id", "encounter_set_package_id", "consensus_scope"):
        if column in _columns("consensus"):
            op.drop_column("consensus", column)
    if _has_table("encounter_set_grading_scopes"):
        op.drop_table("encounter_set_grading_scopes")
    for column in ("arbitrator_user_id", "resident2_user_id", "resident_user_id", "revision_number", "record_origin", "policy_snapshot_json", "policy_revision", "policy_schema_version", "root_scope_disease_id"):
        if column in _columns("encounter_set_grading_packages"):
            op.drop_column("encounter_set_grading_packages", column)
    for column in ("scope_config_json", "policy_revision"):
        if column in _columns("upload_profile_est_grading_packages"):
            op.drop_column("upload_profile_est_grading_packages", column)
