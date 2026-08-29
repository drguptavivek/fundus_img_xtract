"""lean authorization cutover

Revision ID: 90059e4f7ba5
Revises: 0d3edcf7bc3b
Create Date: 2026-08-28 10:08:31.867892

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '90059e4f7ba5'
down_revision: Union[str, Sequence[str], None] = '0d3edcf7bc3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add project-site facts and normalize legacy project permissions."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Seed the two roles introduced by the clean authorization cutover. PII
    # export is direct, exact-scope project authority; User Manager is a
    # classical hospital-scoped role appointed only by Admin.
    bind.execute(
        sa.text(
            "INSERT INTO roles (name) VALUES ('pii_exporter'), ('user_manager') "
            "ON CONFLICT (name) DO NOTHING"
        )
    )

    project_lab_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("project_lab_units")
    }
    for column_name in (
        "sites_can_export_grades",
        "sites_can_create_datasets",
        "sites_can_share_datasets",
    ):
        if column_name not in project_lab_columns:
            op.add_column(
                "project_lab_units",
                sa.Column(
                    column_name,
                    sa.Boolean(),
                    server_default=sa.text("false"),
                    nullable=False,
                ),
            )

    # Legacy datasets have no trustworthy record of whether their creator had
    # project-wide or site-specific authority. Keep them active, but make their
    # management provenance explicit: only Admin manages them after cutover.
    if inspector.has_table("curated_datasets"):
        dataset_columns = {
            column["name"] for column in sa.inspect(bind).get_columns("curated_datasets")
        }
        if "admin_managed" not in dataset_columns:
            op.add_column(
                "curated_datasets",
                sa.Column(
                    "admin_managed",
                    sa.Boolean(),
                    server_default=sa.text("true"),
                    nullable=False,
                ),
            )
            bind.execute(sa.text("UPDATE curated_datasets SET admin_managed = true"))
            op.alter_column(
                "curated_datasets",
                "admin_managed",
                server_default=sa.text("false"),
            )
        dataset_columns = {
            column["name"] for column in sa.inspect(bind).get_columns("curated_datasets")
        }
        if "context_kind" not in dataset_columns:
            op.add_column(
                "curated_datasets",
                sa.Column("context_kind", sa.String(length=16), nullable=True),
            )
            bind.execute(
                sa.text(
                    "UPDATE curated_datasets SET context_kind = 'classical' "
                    "WHERE admin_managed = true"
                )
            )
        if "project_id" not in dataset_columns:
            op.add_column(
                "curated_datasets",
                sa.Column("project_id", sa.Integer(), nullable=True),
            )
            op.create_foreign_key(
                "fk_curated_datasets_project_id_projects",
                "curated_datasets",
                "projects",
                ["project_id"],
                ["id"],
                ondelete="RESTRICT",
            )
            op.create_index(
                "ix_curated_datasets_project_id",
                "curated_datasets",
                ["project_id"],
            )
        dataset_checks = {
            constraint["name"]
            for constraint in sa.inspect(bind).get_check_constraints("curated_datasets")
        }
        if "ck_curated_datasets_authorization_context" not in dataset_checks:
            op.create_check_constraint(
                "ck_curated_datasets_authorization_context",
                "curated_datasets",
                "admin_managed = true OR "
                "(context_kind = 'classical' AND project_id IS NULL) OR "
                "(context_kind = 'project' AND project_id IS NOT NULL)",
            )

    # Convert the retired per-user capability flags into the same exact
    # project-role relationship used everywhere else. Upload is intentionally
    # absent: its authority is the active upload-profile assignment.
    if inspector.has_table("project_encounter_set_permissions"):
        # Keep only the facts needed to make this migration's downgrade
        # lossless. The lean application never reads this rollback ledger.
        if not inspector.has_table("authz_v2_rollback_upload_permissions"):
            op.create_table(
                "authz_v2_rollback_upload_permissions",
                sa.Column("project_id", sa.Integer(), nullable=False),
                sa.Column("user_id", sa.Integer(), nullable=False),
                sa.Column("lab_unit_id", sa.Integer(), nullable=False),
                sa.Column("active", sa.Boolean(), nullable=False),
                sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
                sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
                sa.PrimaryKeyConstraint(
                    "project_id", "user_id", "lab_unit_id",
                    name="pk_authz_v2_rollback_upload_permissions",
                ),
            )
        bind.execute(
            sa.text(
                """
                INSERT INTO authz_v2_rollback_upload_permissions
                    (project_id, user_id, lab_unit_id, active,
                     created_at, updated_at)
                SELECT project_id, user_id, lab_unit_id, active,
                       created_at, updated_at
                  FROM project_encounter_set_permissions
                 WHERE can_upload = true
                ON CONFLICT (project_id, user_id, lab_unit_id)
                DO UPDATE SET
                    active = EXCLUDED.active,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at
                """
            )
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO project_role_grants
                    (project_id, user_id, role_id, scope_type, hospital_id,
                     lab_unit_id, active, created_at, updated_at)
                SELECT permission.project_id,
                       permission.user_id,
                       role_row.id,
                       'lab_unit',
                       CAST(NULL AS INTEGER),
                       permission.lab_unit_id,
                       permission.active,
                       permission.created_at,
                       permission.updated_at
                  FROM project_encounter_set_permissions permission
                  JOIN project_lab_units project_lab
                    ON project_lab.project_id = permission.project_id
                   AND project_lab.lab_unit_id = permission.lab_unit_id
                   AND project_lab.active = true
                  JOIN roles role_row ON (
                       (role_row.name = 'collaborator' AND permission.can_browse = true)
                    OR (role_row.name = 'verifier' AND permission.can_verify = true)
                    OR (role_row.name = 'discrepancy_reviewer' AND permission.can_review_discrepancies = true)
                    OR (role_row.name = 'data_exporter' AND permission.can_export_data = true)
                    OR (role_row.name = 'analytics_viewer' AND permission.can_view_analytics = true)
                    OR (role_row.name = 'dataset_creator' AND permission.can_create_datasets = true)
                    OR (role_row.name = 'regrade_adjudicator' AND permission.can_adjudicate_regrades = true)
                  )
                ON CONFLICT (project_id, user_id, role_id, lab_unit_id)
                  WHERE scope_type = 'lab_unit'
                DO UPDATE SET
                    active = project_role_grants.active OR EXCLUDED.active,
                    updated_at = GREATEST(
                        project_role_grants.updated_at,
                        EXCLUDED.updated_at
                    )
                """
            )
        )
        unresolved_permissions = bind.execute(
            sa.text(
                """
                SELECT COUNT(*)
                  FROM project_encounter_set_permissions permission
                  JOIN LATERAL (
                    VALUES
                      ('collaborator', permission.can_browse),
                      ('verifier', permission.can_verify),
                      ('discrepancy_reviewer', permission.can_review_discrepancies),
                      ('data_exporter', permission.can_export_data),
                      ('analytics_viewer', permission.can_view_analytics),
                      ('dataset_creator', permission.can_create_datasets),
                      ('regrade_adjudicator', permission.can_adjudicate_regrades)
                  ) mapped(role_name, enabled) ON mapped.enabled = true
                 WHERE permission.active = true
                   AND NOT EXISTS (
                     SELECT 1
                       FROM project_role_grants target
                       JOIN roles target_role ON target_role.id = target.role_id
                       JOIN project_lab_units project_lab
                         ON project_lab.project_id = permission.project_id
                        AND project_lab.lab_unit_id = permission.lab_unit_id
                        AND project_lab.active = true
                      WHERE target.project_id = permission.project_id
                        AND target.user_id = permission.user_id
                        AND target_role.name = mapped.role_name
                        AND target.scope_type = 'lab_unit'
                        AND target.lab_unit_id = permission.lab_unit_id
                        AND target.active = true
                   )
                """
            )
        ).scalar_one()
        if unresolved_permissions:
            raise RuntimeError(
                "Lean authorization migration could not preserve active legacy permissions"
            )

    # Project hospital grants are expanded to exact configured Project-Lab
    # Units.  The broad legacy rows are then removed so there is one live
    # representation of project scope.
    grant_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("project_role_grants")
    }
    if "hospital_id" in grant_columns:
        bind.execute(
            sa.text(
                """
                INSERT INTO project_role_grants
                    (project_id, user_id, role_id, scope_type, hospital_id,
                     lab_unit_id, active, created_at, updated_at)
                SELECT DISTINCT grant_row.project_id,
                       grant_row.user_id,
                       grant_row.role_id,
                       'lab_unit',
                       CAST(NULL AS INTEGER),
                       project_lab.lab_unit_id,
                       grant_row.active,
                       grant_row.created_at,
                       grant_row.updated_at
                  FROM project_role_grants grant_row
                  JOIN project_lab_units project_lab
                    ON project_lab.project_id = grant_row.project_id
                   AND project_lab.active = true
                  JOIN lab_units lab ON lab.id = project_lab.lab_unit_id
                 WHERE grant_row.scope_type = 'hospital'
                   AND lab.hospital_id = grant_row.hospital_id
                ON CONFLICT (project_id, user_id, role_id, lab_unit_id)
                  WHERE scope_type = 'lab_unit'
                DO UPDATE SET
                    active = project_role_grants.active OR EXCLUDED.active,
                    updated_at = GREATEST(
                        project_role_grants.updated_at,
                        EXCLUDED.updated_at
                    )
                """
            )
        )
        unresolved_hospital_grants = bind.execute(
            sa.text(
                """
                SELECT COUNT(*)
                  FROM project_role_grants hospital_grant
                 WHERE hospital_grant.scope_type = 'hospital'
                   AND hospital_grant.active = true
                   AND (
                     NOT EXISTS (
                       SELECT 1
                         FROM project_lab_units configured_lab
                         JOIN lab_units lab ON lab.id = configured_lab.lab_unit_id
                        WHERE configured_lab.project_id = hospital_grant.project_id
                          AND configured_lab.active = true
                          AND lab.hospital_id = hospital_grant.hospital_id
                     )
                     OR EXISTS (
                       SELECT 1
                         FROM project_lab_units configured_lab
                         JOIN lab_units lab ON lab.id = configured_lab.lab_unit_id
                        WHERE configured_lab.project_id = hospital_grant.project_id
                          AND configured_lab.active = true
                          AND lab.hospital_id = hospital_grant.hospital_id
                          AND NOT EXISTS (
                            SELECT 1
                              FROM project_role_grants target
                             WHERE target.project_id = hospital_grant.project_id
                               AND target.user_id = hospital_grant.user_id
                               AND target.role_id = hospital_grant.role_id
                               AND target.scope_type = 'lab_unit'
                               AND target.lab_unit_id = configured_lab.lab_unit_id
                               AND target.active = true
                          )
                     )
                   )
                """
            )
        ).scalar_one()
        if unresolved_hospital_grants:
            raise RuntimeError(
                "Lean authorization migration could not preserve active hospital grants"
            )
        bind.execute(
            sa.text("DELETE FROM project_role_grants WHERE scope_type = 'hospital'")
        )

        # Hospital is not a project-grant scope in the lean model. Remove the
        # column and old three-way constraints after expanding the data.
        grant_indexes = {
            index["name"] for index in sa.inspect(bind).get_indexes("project_role_grants")
        }
        for index_name in (
            "uq_project_role_grants_hospital_scope",
            "ix_project_role_grants_hospital_id",
        ):
            if index_name in grant_indexes:
                op.drop_index(index_name, table_name="project_role_grants")
        grant_checks = {
            constraint["name"]
            for constraint in sa.inspect(bind).get_check_constraints("project_role_grants")
        }
        for constraint_name in (
            "ck_project_role_grants_scope_target",
            "ck_project_role_grants_scope_type",
        ):
            if constraint_name in grant_checks:
                op.drop_constraint(
                    constraint_name,
                    "project_role_grants",
                    type_="check",
                )
        grant_foreign_keys = {
            constraint["name"]
            for constraint in sa.inspect(bind).get_foreign_keys("project_role_grants")
        }
        hospital_fk = "fk_project_role_grants_hospital_id_hospitals"
        if hospital_fk in grant_foreign_keys:
            op.drop_constraint(
                hospital_fk,
                "project_role_grants",
                type_="foreignkey",
            )
        op.drop_column("project_role_grants", "hospital_id")
        op.create_check_constraint(
            "ck_project_role_grants_scope_type",
            "project_role_grants",
            "scope_type IN ('project','lab_unit')",
        )
        op.create_check_constraint(
            "ck_project_role_grants_scope_target",
            "project_role_grants",
            "(scope_type = 'project' AND lab_unit_id IS NULL) OR "
            "(scope_type = 'lab_unit' AND lab_unit_id IS NOT NULL)",
        )

    # A prior migration copied upload assignments into broad fileUploader
    # project grants. Upload authority now exists only in exact, active upload
    # profile assignments; retaining these grants would survive revocation.
    bind.execute(
        sa.text(
            """
            DELETE FROM project_role_grants grant_row
             USING roles role_row
             WHERE grant_row.role_id = role_row.id
               AND lower(role_row.name) = 'fileuploader'
            """
        )
    )

    if inspector.has_table("project_encounter_set_permissions"):
        op.drop_table("project_encounter_set_permissions")


def downgrade() -> None:
    """Remove lean-only persisted facts without deleting user relationships."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("curated_datasets"):
        dataset_columns = {
            column["name"] for column in inspector.get_columns("curated_datasets")
        }
        dataset_checks = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("curated_datasets")
        }
        if "ck_curated_datasets_authorization_context" in dataset_checks:
            op.drop_constraint(
                "ck_curated_datasets_authorization_context",
                "curated_datasets",
                type_="check",
            )
        if "project_id" in dataset_columns:
            op.drop_index("ix_curated_datasets_project_id", table_name="curated_datasets")
            op.drop_column("curated_datasets", "project_id")
        if "context_kind" in dataset_columns:
            op.drop_column("curated_datasets", "context_kind")
        if "admin_managed" in dataset_columns:
            op.drop_column("curated_datasets", "admin_managed")
        inspector = sa.inspect(bind)
    grant_columns = {
        column["name"] for column in inspector.get_columns("project_role_grants")
    }
    if "hospital_id" not in grant_columns:
        grant_checks = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("project_role_grants")
        }
        for constraint_name in (
            "ck_project_role_grants_scope_target",
            "ck_project_role_grants_scope_type",
        ):
            if constraint_name in grant_checks:
                op.drop_constraint(
                    constraint_name,
                    "project_role_grants",
                    type_="check",
                )
        op.add_column(
            "project_role_grants",
            sa.Column("hospital_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_project_role_grants_hospital_id_hospitals",
            "project_role_grants",
            "hospitals",
            ["hospital_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(
            "ix_project_role_grants_hospital_id",
            "project_role_grants",
            ["hospital_id"],
        )
        op.create_index(
            "uq_project_role_grants_hospital_scope",
            "project_role_grants",
            ["project_id", "user_id", "role_id", "hospital_id"],
            unique=True,
            postgresql_where=sa.text("scope_type = 'hospital'"),
        )
        op.create_check_constraint(
            "ck_project_role_grants_scope_type",
            "project_role_grants",
            "scope_type IN ('project','hospital','lab_unit')",
        )
        op.create_check_constraint(
            "ck_project_role_grants_scope_target",
            "project_role_grants",
            "(scope_type = 'project' AND hospital_id IS NULL AND lab_unit_id IS NULL) OR "
            "(scope_type = 'hospital' AND hospital_id IS NOT NULL AND lab_unit_id IS NULL) OR "
            "(scope_type = 'lab_unit' AND hospital_id IS NULL AND lab_unit_id IS NOT NULL)",
        )
        inspector = sa.inspect(bind)
    if not inspector.has_table("project_encounter_set_permissions"):
        op.create_table(
            "project_encounter_set_permissions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("lab_unit_id", sa.Integer(), nullable=False),
            sa.Column("can_browse", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("can_verify", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("can_upload", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("can_review_discrepancies", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("can_export_data", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("can_view_analytics", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("can_create_datasets", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("can_adjudicate_regrades", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["lab_unit_id"], ["lab_units.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "project_id", "user_id", "lab_unit_id",
                name="uq_project_encounter_set_permission",
            ),
        )
        op.create_index(
            "ix_project_encounter_set_permissions_lookup",
            "project_encounter_set_permissions",
            ["user_id", "project_id", "lab_unit_id", "active"],
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO project_encounter_set_permissions
                    (project_id, user_id, lab_unit_id, can_browse, can_verify,
                     can_upload, can_review_discrepancies, can_export_data,
                     can_view_analytics, can_create_datasets,
                     can_adjudicate_regrades, active, created_at, updated_at)
                SELECT grant_row.project_id,
                       grant_row.user_id,
                       grant_row.lab_unit_id,
                       bool_or(role_row.name = 'collaborator' AND grant_row.active),
                       bool_or(role_row.name = 'verifier' AND grant_row.active),
                       false,
                       bool_or(role_row.name = 'discrepancy_reviewer' AND grant_row.active),
                       bool_or(role_row.name = 'data_exporter' AND grant_row.active),
                       bool_or(role_row.name = 'analytics_viewer' AND grant_row.active),
                       bool_or(role_row.name = 'dataset_creator' AND grant_row.active),
                       bool_or(role_row.name = 'regrade_adjudicator' AND grant_row.active),
                       bool_or(grant_row.active),
                       min(grant_row.created_at),
                       max(grant_row.updated_at)
                  FROM project_role_grants grant_row
                  JOIN roles role_row ON role_row.id = grant_row.role_id
                 WHERE grant_row.scope_type = 'lab_unit'
                   AND role_row.name IN (
                       'collaborator', 'verifier', 'discrepancy_reviewer',
                       'data_exporter', 'analytics_viewer', 'dataset_creator',
                       'regrade_adjudicator'
                   )
                 GROUP BY grant_row.project_id, grant_row.user_id,
                          grant_row.lab_unit_id
                """
            )
        )

    inspector = sa.inspect(bind)
    if inspector.has_table("authz_v2_rollback_upload_permissions"):
        bind.execute(
            sa.text(
                """
                INSERT INTO project_encounter_set_permissions
                    (project_id, user_id, lab_unit_id, can_browse, can_verify,
                     can_upload, can_review_discrepancies, can_export_data,
                     can_view_analytics, can_create_datasets,
                     can_adjudicate_regrades, active, created_at, updated_at)
                SELECT rollback.project_id,
                       rollback.user_id,
                       rollback.lab_unit_id,
                       false,
                       false,
                       true,
                       false,
                       false,
                       false,
                       false,
                       false,
                       rollback.active,
                       rollback.created_at,
                       rollback.updated_at
                  FROM authz_v2_rollback_upload_permissions rollback
                ON CONFLICT (project_id, user_id, lab_unit_id)
                DO UPDATE SET
                    can_upload = true,
                    active = EXCLUDED.active,
                    created_at = LEAST(
                        project_encounter_set_permissions.created_at,
                        EXCLUDED.created_at
                    ),
                    updated_at = GREATEST(
                        project_encounter_set_permissions.updated_at,
                        EXCLUDED.updated_at
                    )
                """
            )
        )

    # Restore the prior release's derived uploader grants when rolling back.
    # The authoritative assignments remain present throughout the cutover.
    bind.execute(
        sa.text(
            """
            INSERT INTO project_role_grants
                (project_id, user_id, role_id, scope_type, hospital_id,
                 lab_unit_id, active, created_at, updated_at)
            SELECT project_profile.project_id,
                   assignment.user_id,
                   role_row.id,
                   'lab_unit',
                   CAST(NULL AS INTEGER),
                   assignment.lab_unit_id,
                   bool_or(
                       assignment.active
                       AND project_profile.active
                       AND upload_profile.active
                   ),
                   now(),
                   now()
              FROM project_upload_profile_assignments assignment
              JOIN project_upload_profiles project_profile
                ON project_profile.id = assignment.project_upload_profile_id
              JOIN upload_profiles upload_profile
                ON upload_profile.id = project_profile.upload_profile_id
              JOIN roles role_row ON lower(role_row.name) = 'fileuploader'
             GROUP BY project_profile.project_id, assignment.user_id,
                      role_row.id, assignment.lab_unit_id
            ON CONFLICT (project_id, user_id, role_id, lab_unit_id)
              WHERE scope_type = 'lab_unit'
            DO UPDATE SET
                active = EXCLUDED.active,
                updated_at = EXCLUDED.updated_at
            """
        )
    )
    if inspector.has_table("authz_v2_rollback_upload_permissions"):
        bind.execute(
            sa.text(
                """
                INSERT INTO project_role_grants
                    (project_id, user_id, role_id, scope_type, hospital_id,
                     lab_unit_id, active, created_at, updated_at)
                SELECT rollback.project_id,
                       rollback.user_id,
                       role_row.id,
                       'lab_unit',
                       CAST(NULL AS INTEGER),
                       rollback.lab_unit_id,
                       rollback.active,
                       rollback.created_at,
                       rollback.updated_at
                  FROM authz_v2_rollback_upload_permissions rollback
                  JOIN roles role_row
                    ON lower(role_row.name) = 'fileuploader'
                ON CONFLICT (project_id, user_id, role_id, lab_unit_id)
                  WHERE scope_type = 'lab_unit'
                DO UPDATE SET
                    active = project_role_grants.active OR EXCLUDED.active,
                    updated_at = GREATEST(
                        project_role_grants.updated_at,
                        EXCLUDED.updated_at
                    )
                """
            )
        )
        op.drop_table("authz_v2_rollback_upload_permissions")
    if inspector.has_table("project_lab_units"):
        columns = {
            column["name"] for column in inspector.get_columns("project_lab_units")
        }
        for column_name in (
            "sites_can_share_datasets",
            "sites_can_create_datasets",
            "sites_can_export_grades",
        ):
            if column_name in columns:
                op.drop_column("project_lab_units", column_name)
