"""add unified authorization grants and audit

Revision ID: e735238d678b
Revises: 0d3edcf7bc3b
Create Date: 2026-08-26 17:54:07.494235
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e735238d678b"
down_revision: str | Sequence[str] | None = "0d3edcf7bc3b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


AUDIT_IMMUTABLE_SQL = """
CREATE OR REPLACE FUNCTION reject_authorization_audit_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'authorization audit events are append-only'
        USING ERRCODE = 'insufficient_privilege';
END;
$$;
DROP TRIGGER IF EXISTS trg_authorization_audit_immutable ON authorization_audit_events;
CREATE TRIGGER trg_authorization_audit_immutable
BEFORE UPDATE OR DELETE ON authorization_audit_events
FOR EACH ROW EXECUTE FUNCTION reject_authorization_audit_mutation();
"""


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _index_names(table: str) -> set[str]:
    return {row["name"] for row in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    """Expand the schema and perform deterministic, ID-only conversion."""
    tables = _table_names()
    if "authorization_grants" not in tables:
        op.create_table(
            "authorization_grants",
            sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column(
                "role_id",
                sa.Integer(),
                sa.ForeignKey("roles.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("scope_type", sa.String(32), nullable=False),
            sa.Column(
                "hospital_id",
                sa.Integer(),
                sa.ForeignKey("hospitals.id", ondelete="RESTRICT"),
            ),
            sa.Column(
                "lab_unit_id",
                sa.Integer(),
                sa.ForeignKey("lab_units.id", ondelete="RESTRICT"),
            ),
            sa.Column(
                "project_id",
                sa.Integer(),
                sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            ),
            sa.Column(
                "project_lab_unit_id",
                sa.Integer(),
                sa.ForeignKey("project_lab_units.id", ondelete="RESTRICT"),
            ),
            sa.Column("description", sa.String(500)),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column(
                "created_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
            ),
            sa.Column(
                "updated_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
            ),
            sa.Column(
                "deactivated_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("deactivated_at", sa.DateTime(timezone=True)),
            sa.CheckConstraint(
                "scope_type IN ('system','hospital','lab_unit','project','project_lab_unit')",
                name="ck_authorization_grants_scope_type",
            ),
            sa.CheckConstraint(
                "(scope_type = 'system' AND hospital_id IS NULL AND lab_unit_id IS NULL AND project_id IS NULL AND project_lab_unit_id IS NULL) OR "
                "(scope_type = 'hospital' AND hospital_id IS NOT NULL AND lab_unit_id IS NULL AND project_id IS NULL AND project_lab_unit_id IS NULL) OR "
                "(scope_type = 'lab_unit' AND hospital_id IS NULL AND lab_unit_id IS NOT NULL AND project_id IS NULL AND project_lab_unit_id IS NULL) OR "
                "(scope_type = 'project' AND hospital_id IS NULL AND lab_unit_id IS NULL AND project_id IS NOT NULL AND project_lab_unit_id IS NULL) OR "
                "(scope_type = 'project_lab_unit' AND hospital_id IS NULL AND lab_unit_id IS NULL AND project_id IS NULL AND project_lab_unit_id IS NOT NULL)",
                name="ck_authorization_grants_scope_target",
            ),
            sa.CheckConstraint(
                "description IS NULL OR length(btrim(description)) BETWEEN 1 AND 500",
                name="ck_authorization_grants_description",
            ),
        )

    indexes = _index_names("authorization_grants")
    index_specs = (
        (
            "uq_authorization_grants_system",
            ["user_id", "role_id"],
            "scope_type = 'system'",
            True,
        ),
        (
            "uq_authorization_grants_hospital",
            ["user_id", "role_id", "hospital_id"],
            "scope_type = 'hospital'",
            True,
        ),
        (
            "uq_authorization_grants_lab",
            ["user_id", "role_id", "lab_unit_id"],
            "scope_type = 'lab_unit'",
            True,
        ),
        (
            "uq_authorization_grants_project",
            ["user_id", "role_id", "project_id"],
            "scope_type = 'project'",
            True,
        ),
        (
            "uq_authorization_grants_project_lab",
            ["user_id", "role_id", "project_lab_unit_id"],
            "scope_type = 'project_lab_unit'",
            True,
        ),
        (
            "ix_authorization_grants_resolve",
            ["user_id", "active", "role_id", "scope_type"],
            None,
            False,
        ),
    )
    for name, columns, predicate, unique in index_specs:
        if name not in indexes:
            op.create_index(
                name,
                "authorization_grants",
                columns,
                unique=unique,
                postgresql_where=sa.text(predicate) if predicate else None,
            )

    if "authorization_audit_events" not in tables:
        op.create_table(
            "authorization_audit_events",
            sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
            sa.Column("event", sa.String(80), nullable=False),
            sa.Column("action", sa.String(160), nullable=False),
            sa.Column("outcome", sa.String(16), nullable=False),
            sa.Column(
                "actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")
            ),
            sa.Column("session_kind", sa.String(24), nullable=False),
            sa.Column("policy_path", sa.String(120)),
            sa.Column(
                "break_glass", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column("request_id", sa.String(128)),
            sa.Column("resource_type", sa.String(80)),
            sa.Column("resource_id", sa.String(128)),
            sa.Column("scope_type", sa.String(32)),
            sa.Column("scope_id", sa.String(128)),
            sa.Column("detail_json", sa.Text()),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.CheckConstraint(
                "outcome IN ('allow','deny','error')",
                name="ck_authorization_audit_outcome",
            ),
        )
    audit_indexes = _index_names("authorization_audit_events")
    for name, columns in (
        ("ix_authorization_audit_events_event", ["event"]),
        ("ix_authorization_audit_events_action", ["action"]),
        ("ix_authorization_audit_events_actor_id", ["actor_id"]),
        ("ix_authorization_audit_events_request_id", ["request_id"]),
        ("ix_authorization_audit_events_created_at", ["created_at"]),
        ("ix_authorization_audit_action_created", ["action", "created_at"]),
    ):
        if name not in audit_indexes:
            op.create_index(name, "authorization_audit_events", columns)

    if "project_lab_unit_authorization_policies" not in tables:
        op.create_table(
            "project_lab_unit_authorization_policies",
            sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
            sa.Column(
                "project_lab_unit_id",
                sa.Integer(),
                sa.ForeignKey("project_lab_units.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
            ),
            sa.Column(
                "grade_export_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "dataset_creation_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "dataset_sharing_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "created_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
            ),
            sa.Column(
                "updated_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    if "authorization_resource_scopes" not in tables:
        op.create_table(
            "authorization_resource_scopes",
            sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
            sa.Column("resource_type", sa.String(80), nullable=False),
            sa.Column("resource_id", sa.String(128), nullable=False),
            sa.Column("scope_type", sa.String(32), nullable=False),
            sa.Column(
                "hospital_id",
                sa.Integer(),
                sa.ForeignKey("hospitals.id", ondelete="RESTRICT"),
            ),
            sa.Column(
                "lab_unit_id",
                sa.Integer(),
                sa.ForeignKey("lab_units.id", ondelete="RESTRICT"),
            ),
            sa.Column(
                "project_id",
                sa.Integer(),
                sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            ),
            sa.Column(
                "project_lab_unit_id",
                sa.Integer(),
                sa.ForeignKey("project_lab_units.id", ondelete="RESTRICT"),
            ),
            sa.Column(
                "owner_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
            ),
            sa.Column(
                "requester_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
            ),
            sa.Column(
                "automation_rule_id",
                sa.Integer(),
                sa.ForeignKey(
                    "project_automated_remote_inference_rules.id",
                    ondelete="SET NULL",
                ),
            ),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column(
                "domain_valid", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column(
                "created_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
            ),
            sa.Column(
                "updated_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint(
                "resource_type", "resource_id", name="uq_authorization_resource_scope"
            ),
            sa.CheckConstraint(
                "scope_type IN ('system','hospital','lab_unit','project','project_lab_unit')",
                name="ck_authorization_resource_scopes_scope_type",
            ),
            sa.CheckConstraint(
                "(scope_type = 'system' AND hospital_id IS NULL AND lab_unit_id IS NULL AND project_id IS NULL AND project_lab_unit_id IS NULL) OR "
                "(scope_type = 'hospital' AND hospital_id IS NOT NULL AND lab_unit_id IS NULL AND project_id IS NULL AND project_lab_unit_id IS NULL) OR "
                "(scope_type = 'lab_unit' AND hospital_id IS NULL AND lab_unit_id IS NOT NULL AND project_id IS NULL AND project_lab_unit_id IS NULL) OR "
                "(scope_type = 'project' AND hospital_id IS NULL AND lab_unit_id IS NULL AND project_id IS NOT NULL AND project_lab_unit_id IS NULL) OR "
                "(scope_type = 'project_lab_unit' AND hospital_id IS NULL AND lab_unit_id IS NULL AND project_id IS NULL AND project_lab_unit_id IS NOT NULL)",
                name="ck_authorization_resource_scopes_scope_target",
            ),
        )
        op.create_index(
            "ix_authorization_resource_scopes_lookup",
            "authorization_resource_scopes",
            ["resource_type", "resource_id", "active"],
        )
    if "password_reset_credentials" not in tables:
        op.create_table(
            "password_reset_credentials",
            sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True)),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.CheckConstraint(
                "length(btrim(token_hash)) >= 32",
                name="ck_password_reset_credentials_hash",
            ),
        )
        op.create_index(
            "ix_password_reset_credentials_active",
            "password_reset_credentials",
            ["user_id", "expires_at"],
            postgresql_where=sa.text("consumed_at IS NULL"),
        )

    if "authorization_upload_profile_assignments" not in tables:
        op.create_table(
            "authorization_upload_profile_assignments",
            sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "lab_unit_id",
                sa.Integer(),
                sa.ForeignKey("lab_units.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "upload_profile_id",
                sa.Integer(),
                sa.ForeignKey("upload_profiles.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column(
                "created_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint(
                "user_id",
                "lab_unit_id",
                "upload_profile_id",
                name="uq_authorization_upload_profile_assignment",
            ),
        )
        op.create_index(
            "ix_authorization_upload_profile_assignment_lookup",
            "authorization_upload_profile_assignments",
            ["user_id", "lab_unit_id", "active"],
        )

    op.execute(
        sa.text(
            "INSERT INTO roles (name) VALUES ('user_manager'), ('pii_exporter') ON CONFLICT (name) DO NOTHING"
        )
    )

    # Preserve legacy classical upload reach as explicit exact assignments.
    # Operational upload roles retain only their stored lab memberships; a
    # system Admin retains the pre-cutover global break-glass reach.
    op.execute(
        sa.text("""
        INSERT INTO authorization_upload_profile_assignments (
            user_id, lab_unit_id, upload_profile_id, active, created_at, updated_at
        )
        SELECT DISTINCT ur.user_id, ulu.lab_unit_id, p.id, true, now(), now()
        FROM user_roles ur
        JOIN roles r ON r.id = ur.role_id
        JOIN user_lab_units ulu ON ulu.user_id = ur.user_id
        CROSS JOIN upload_profiles p
        WHERE r.name IN ('fileUploader','pregraded_uploader','optometrist')
          AND p.active
        ON CONFLICT DO NOTHING;

        INSERT INTO authorization_upload_profile_assignments (
            user_id, lab_unit_id, upload_profile_id, active, created_at, updated_at
        )
        SELECT DISTINCT ur.user_id, lu.id, p.id, true, now(), now()
        FROM user_roles ur
        JOIN roles r ON r.id = ur.role_id
        CROSS JOIN lab_units lu
        CROSS JOIN upload_profiles p
        WHERE r.name = 'admin' AND p.active
        ON CONFLICT DO NOTHING;
    """)
    )

    # Conceptual classical upload targets are exact lab resources. Profile
    # assignments remain separate and are checked additively.
    op.execute(
        sa.text("""
        INSERT INTO authorization_resource_scopes (
            resource_type, resource_id, scope_type, lab_unit_id,
            active, domain_valid, created_at, updated_at
        )
        SELECT 'upload_target', 'lab:' || lu.id::text, 'lab_unit', lu.id,
               true, true, now(), now()
        FROM lab_units lu
        ON CONFLICT (resource_type, resource_id) DO NOTHING;
    """)
    )

    # Existing datasets and ad-hoc batches must have one deterministic common
    # lineage. Empty or mixed classical/project sets stop the conversion.
    op.execute(
        sa.text("""
        DO $$ DECLARE bad_ids text;
        BEGIN
          WITH lineage AS (
            SELECT d.id,
                   count(i.id) AS item_count,
                   bool_or(t.project_id IS NULL) AS has_classical,
                   bool_or(t.project_id IS NOT NULL) AS has_project,
                   count(DISTINCT t.project_id) FILTER (WHERE t.project_id IS NOT NULL) AS project_count,
                   count(DISTINCT lu.hospital_id) AS hospital_count
            FROM curated_datasets d
            LEFT JOIN curated_dataset_items i ON i.dataset_id = d.id
            LEFT JOIN grading_tasks t ON t.id = i.task_id
            LEFT JOIN lab_units lu ON lu.id = t.lab_unit_id
            GROUP BY d.id
          )
          SELECT string_agg(id::text, ',' ORDER BY id) INTO bad_ids
          FROM lineage
          WHERE item_count = 0
             OR (has_classical AND has_project)
             OR project_count > 1
             OR (has_classical AND hospital_count <> 1);
          IF bad_ids IS NOT NULL THEN
            RAISE EXCEPTION 'AUTHZ_CONVERSION_DATASET_LINEAGE_IDS=%', bad_ids;
          END IF;
        END $$;

        DO $$ DECLARE bad_ids text;
        BEGIN
          WITH lineage AS (
            SELECT a.id,
                   count(t.id) AS task_count,
                   bool_or(t.project_id IS NULL) AS has_classical,
                   bool_or(t.project_id IS NOT NULL) AS has_project,
                   count(DISTINCT t.project_id) FILTER (WHERE t.project_id IS NOT NULL) AS project_count,
                   count(DISTINCT lu.hospital_id) AS hospital_count
            FROM ad_hoc_task_creations a
            LEFT JOIN grading_tasks t ON t.ad_hoc_id = a.id
            LEFT JOIN lab_units lu ON lu.id = t.lab_unit_id
            GROUP BY a.id
          )
          SELECT string_agg(id::text, ',' ORDER BY id) INTO bad_ids
          FROM lineage
          WHERE task_count = 0
             OR (has_classical AND has_project)
             OR project_count > 1
             OR (has_classical AND hospital_count <> 1);
          IF bad_ids IS NOT NULL THEN
            RAISE EXCEPTION 'AUTHZ_CONVERSION_AD_HOC_LINEAGE_IDS=%', bad_ids;
          END IF;
        END $$;
    """)
    )

    op.execute(
        sa.text("""
        WITH dataset_lineage AS (
          SELECT d.id, d.created_by_user_id,
                 min(t.project_id) AS project_id,
                 min(t.lab_unit_id) AS lab_unit_id,
                 min(lu.hospital_id) AS hospital_id,
                 count(DISTINCT t.lab_unit_id) AS lab_count,
                 count(DISTINCT t.project_id) FILTER (WHERE t.project_id IS NOT NULL) AS project_count
          FROM curated_datasets d
          JOIN curated_dataset_items i ON i.dataset_id = d.id
          JOIN grading_tasks t ON t.id = i.task_id
          JOIN lab_units lu ON lu.id = t.lab_unit_id
          GROUP BY d.id, d.created_by_user_id
        ), resolved AS (
          SELECT l.*,
                 CASE
                   WHEN l.project_count = 1 AND l.lab_count = 1 THEN 'project_lab_unit'
                   WHEN l.project_count = 1 THEN 'project'
                   WHEN l.lab_count = 1 THEN 'lab_unit'
                   ELSE 'hospital'
                 END AS scope_type,
                 plu.id AS project_lab_unit_id
          FROM dataset_lineage l
          LEFT JOIN project_lab_units plu
            ON plu.project_id = l.project_id AND plu.lab_unit_id = l.lab_unit_id
        )
        INSERT INTO authorization_resource_scopes (
          resource_type, resource_id, scope_type,
          hospital_id, lab_unit_id, project_id, project_lab_unit_id,
          owner_user_id, active, domain_valid, created_at, updated_at
        )
        SELECT 'dataset', id::text, scope_type,
          CASE WHEN scope_type = 'hospital' THEN hospital_id END,
          CASE WHEN scope_type = 'lab_unit' THEN lab_unit_id END,
          CASE WHEN scope_type = 'project' THEN project_id END,
          CASE WHEN scope_type = 'project_lab_unit' THEN project_lab_unit_id END,
          created_by_user_id, true, true, now(), now()
        FROM resolved
        WHERE scope_type <> 'project_lab_unit' OR project_lab_unit_id IS NOT NULL
        ON CONFLICT (resource_type, resource_id) DO NOTHING;

        WITH ad_hoc_lineage AS (
          SELECT a.id, a.created_by_id,
                 min(t.project_id) AS project_id,
                 min(t.lab_unit_id) AS lab_unit_id,
                 min(lu.hospital_id) AS hospital_id,
                 count(DISTINCT t.lab_unit_id) AS lab_count,
                 count(DISTINCT t.project_id) FILTER (WHERE t.project_id IS NOT NULL) AS project_count
          FROM ad_hoc_task_creations a
          JOIN grading_tasks t ON t.ad_hoc_id = a.id
          JOIN lab_units lu ON lu.id = t.lab_unit_id
          GROUP BY a.id, a.created_by_id
        ), resolved AS (
          SELECT l.*,
                 CASE
                   WHEN l.project_count = 1 AND l.lab_count = 1 THEN 'project_lab_unit'
                   WHEN l.project_count = 1 THEN 'project'
                   WHEN l.lab_count = 1 THEN 'lab_unit'
                   ELSE 'hospital'
                 END AS scope_type,
                 plu.id AS project_lab_unit_id
          FROM ad_hoc_lineage l
          LEFT JOIN project_lab_units plu
            ON plu.project_id = l.project_id AND plu.lab_unit_id = l.lab_unit_id
        )
        INSERT INTO authorization_resource_scopes (
          resource_type, resource_id, scope_type,
          hospital_id, lab_unit_id, project_id, project_lab_unit_id,
          owner_user_id, active, domain_valid, created_at, updated_at
        )
        SELECT 'ad_hoc_task', id::text, scope_type,
          CASE WHEN scope_type = 'hospital' THEN hospital_id END,
          CASE WHEN scope_type = 'lab_unit' THEN lab_unit_id END,
          CASE WHEN scope_type = 'project' THEN project_id END,
          CASE WHEN scope_type = 'project_lab_unit' THEN project_lab_unit_id END,
          created_by_id, true, true, now(), now()
        FROM resolved
        WHERE scope_type <> 'project_lab_unit' OR project_lab_unit_id IS NOT NULL
        ON CONFLICT (resource_type, resource_id) DO NOTHING;
    """)
    )

    # Global legacy roles need a deterministic persisted scope. Missing scope
    # evidence is an ambiguity, never permission to widen the grant.
    op.execute(
        sa.text("""
        DO $$ DECLARE bad_ids text;
        BEGIN
          SELECT string_agg(ur.user_id::text, ',' ORDER BY ur.user_id) INTO bad_ids
          FROM user_roles ur
          JOIN roles r ON r.id = ur.role_id
          JOIN users u ON u.id = ur.user_id
          WHERE r.name = 'local_admin' AND u.hospital_id IS NULL;
          IF bad_ids IS NOT NULL THEN
            RAISE EXCEPTION 'AUTHZ_CONVERSION_LOCAL_ADMIN_WITHOUT_HOSPITAL_USER_IDS=%', bad_ids;
          END IF;
        END $$;
    """)
    )
    op.execute(
        sa.text("""
        DO $$ DECLARE bad_ids text;
        BEGIN
          SELECT string_agg(ur.user_id::text, ',' ORDER BY ur.user_id) INTO bad_ids
          FROM user_roles ur
          JOIN roles r ON r.id = ur.role_id
          WHERE r.name IN (
              'data_manager','fileUploader','pregraded_uploader','ophthalmologist',
              'optometrist','verifier','analytics_viewer','dataset_creator',
              'data_exporter','discrepancy_reviewer','regrade_adjudicator','pii_exporter'
              ,'field_optometrist','field_ophthalmologist'
          )
          AND NOT EXISTS (
              SELECT 1 FROM user_lab_units ulu WHERE ulu.user_id = ur.user_id
          );
          IF bad_ids IS NOT NULL THEN
            RAISE EXCEPTION 'AUTHZ_CONVERSION_OPERATIONAL_ROLE_WITHOUT_LAB_USER_IDS=%', bad_ids;
          END IF;
        END $$;
    """)
    )

    op.execute(
        sa.text("""
        DO $$ DECLARE bad_ids text;
        BEGIN
          SELECT string_agg(
            ur.user_id::text || ':' || ur.role_id::text,
            ',' ORDER BY ur.user_id, ur.role_id
          ) INTO bad_ids
          FROM user_roles ur JOIN roles r ON r.id = ur.role_id
          WHERE r.name NOT IN (
            'admin','local_admin','data_manager','fileUploader',
            'pregraded_uploader','ophthalmologist','optometrist','verifier',
            'analytics_viewer','dataset_creator','data_exporter',
            'discrepancy_reviewer','regrade_adjudicator','pii_exporter',
            'field_optometrist','field_ophthalmologist'
          );
          IF bad_ids IS NOT NULL THEN
            RAISE EXCEPTION 'AUTHZ_CONVERSION_UNSUPPORTED_USER_ROLE_IDS=%', bad_ids;
          END IF;
        END $$;
    """)
    )

    # Project-hospital grants have no unambiguous target in the new model.
    op.execute(
        sa.text("""
        DO $$ DECLARE bad_ids text;
        BEGIN
          SELECT string_agg(id::text, ',' ORDER BY id) INTO bad_ids
          FROM project_role_grants WHERE scope_type = 'hospital';
          IF bad_ids IS NOT NULL THEN
            RAISE EXCEPTION 'AUTHZ_CONVERSION_PROJECT_HOSPITAL_IDS=%', bad_ids;
          END IF;
        END $$;
    """)
    )

    op.execute(
        sa.text("""
        DO $$ DECLARE bad_ids text;
        BEGIN
          SELECT string_agg(g.id::text, ',' ORDER BY g.id) INTO bad_ids
          FROM project_role_grants g
          JOIN roles r ON r.id = g.role_id
          WHERE (
              g.scope_type NOT IN ('project', 'lab_unit')
              OR r.name NOT IN (
                'project_pi','site_pi','project_admin','collaborator',
                'data_manager','fileUploader','pregraded_uploader','ophthalmologist',
                'optometrist','verifier','analytics_viewer','dataset_creator',
                'data_exporter','pii_exporter','discrepancy_reviewer',
                'regrade_adjudicator','field_optometrist','field_ophthalmologist'
              )
            );
          IF bad_ids IS NOT NULL THEN
            RAISE EXCEPTION 'AUTHZ_CONVERSION_UNSUPPORTED_PROJECT_GRANT_IDS=%', bad_ids;
          END IF;
        END $$;
    """)
    )

    # Every active lab-scoped project grant must resolve to one stored project site.
    op.execute(
        sa.text("""
        DO $$ DECLARE bad_ids text;
        BEGIN
          SELECT string_agg(g.id::text, ',' ORDER BY g.id) INTO bad_ids
          FROM project_role_grants g
          LEFT JOIN project_lab_units plu ON plu.project_id = g.project_id AND plu.lab_unit_id = g.lab_unit_id
          WHERE g.scope_type = 'lab_unit' AND plu.id IS NULL;
          IF bad_ids IS NOT NULL THEN
            RAISE EXCEPTION 'AUTHZ_CONVERSION_ORPHAN_PROJECT_LAB_IDS=%', bad_ids;
          END IF;
        END $$;
    """)
    )

    # Legacy upload capability is not authority without an exact active profile assignment.
    op.execute(
        sa.text("""
        DO $$ DECLARE bad_ids text;
        BEGIN
          SELECT string_agg(p.id::text, ',' ORDER BY p.id) INTO bad_ids
          FROM project_encounter_set_permissions p
          WHERE p.can_upload
            AND NOT EXISTS (
              SELECT 1 FROM project_upload_profile_assignments a
              JOIN project_upload_profiles pp ON pp.id = a.project_upload_profile_id
              WHERE a.active AND a.user_id = p.user_id AND a.lab_unit_id = p.lab_unit_id
                AND pp.project_id = p.project_id AND pp.active
            );
          IF bad_ids IS NOT NULL THEN
            RAISE EXCEPTION 'AUTHZ_CONVERSION_UPLOAD_WITHOUT_PROFILE_IDS=%', bad_ids;
          END IF;
        END $$;
    """)
    )

    # Stable-ID conversions. Descriptions intentionally contain no person data.
    op.execute(
        sa.text("""
        INSERT INTO authorization_grants (user_id, role_id, scope_type, active, created_at, updated_at)
        SELECT ur.user_id, ur.role_id, 'system', true, now(), now()
        FROM user_roles ur JOIN roles r ON r.id = ur.role_id
        WHERE r.name = 'admin'
        ON CONFLICT DO NOTHING;

        INSERT INTO authorization_grants (user_id, role_id, scope_type, hospital_id, active, created_at, updated_at)
        SELECT ur.user_id, ur.role_id, 'hospital', u.hospital_id, true, now(), now()
        FROM user_roles ur JOIN roles r ON r.id = ur.role_id JOIN users u ON u.id = ur.user_id
        WHERE r.name = 'local_admin' AND u.hospital_id IS NOT NULL
        ON CONFLICT DO NOTHING;

        INSERT INTO authorization_grants (user_id, role_id, scope_type, lab_unit_id, active, created_at, updated_at)
        SELECT ur.user_id, ur.role_id, 'lab_unit', ulu.lab_unit_id, true, now(), now()
        FROM user_roles ur JOIN roles r ON r.id = ur.role_id
        JOIN user_lab_units ulu ON ulu.user_id = ur.user_id
        WHERE r.name IN ('data_manager','fileUploader','pregraded_uploader','ophthalmologist','optometrist','verifier','analytics_viewer','dataset_creator','data_exporter','discrepancy_reviewer','regrade_adjudicator','pii_exporter','field_optometrist','field_ophthalmologist')
        ON CONFLICT DO NOTHING;

        INSERT INTO authorization_grants (user_id, role_id, scope_type, project_id, active, created_at, updated_at)
        SELECT user_id, role_id, 'project', project_id, active, created_at, updated_at
        FROM project_role_grants WHERE scope_type = 'project'
        ON CONFLICT DO NOTHING;

        INSERT INTO authorization_grants (user_id, role_id, scope_type, project_lab_unit_id, active, created_at, updated_at)
        SELECT g.user_id, g.role_id, 'project_lab_unit', plu.id, g.active, g.created_at, g.updated_at
        FROM project_role_grants g
        JOIN project_lab_units plu ON plu.project_id = g.project_id AND plu.lab_unit_id = g.lab_unit_id
        WHERE g.scope_type = 'lab_unit'
        ON CONFLICT DO NOTHING;
    """)
    )

    op.execute(
        sa.text("""
        DO $$ DECLARE bad_ids text;
        BEGIN
          WITH expected AS (
            SELECT ur.user_id, ur.role_id, 'system'::text AS scope_type,
                   NULL::integer AS target_id
            FROM user_roles ur JOIN roles r ON r.id = ur.role_id
            WHERE r.name = 'admin'
            UNION ALL
            SELECT ur.user_id, ur.role_id, 'hospital', u.hospital_id
            FROM user_roles ur JOIN roles r ON r.id = ur.role_id
            JOIN users u ON u.id = ur.user_id
            WHERE r.name = 'local_admin'
            UNION ALL
            SELECT ur.user_id, ur.role_id, 'lab_unit', ulu.lab_unit_id
            FROM user_roles ur JOIN roles r ON r.id = ur.role_id
            JOIN user_lab_units ulu ON ulu.user_id = ur.user_id
            WHERE r.name IN (
              'data_manager','fileUploader','pregraded_uploader','ophthalmologist',
              'optometrist','verifier','analytics_viewer','dataset_creator',
              'data_exporter','discrepancy_reviewer','regrade_adjudicator',
              'pii_exporter','field_optometrist','field_ophthalmologist'
            )
          )
          SELECT string_agg(
            e.user_id::text || ':' || e.role_id::text || ':' ||
              e.scope_type || ':' || coalesce(e.target_id::text, 'system'),
            ',' ORDER BY e.user_id, e.role_id, e.scope_type, e.target_id
          ) INTO bad_ids
          FROM expected e
          WHERE NOT EXISTS (
            SELECT 1 FROM authorization_grants g
            WHERE g.user_id = e.user_id AND g.role_id = e.role_id AND g.active
              AND g.scope_type = e.scope_type
              AND (
                (e.scope_type = 'system')
                OR (e.scope_type = 'hospital' AND g.hospital_id = e.target_id)
                OR (e.scope_type = 'lab_unit' AND g.lab_unit_id = e.target_id)
              )
          );
          IF bad_ids IS NOT NULL THEN
            RAISE EXCEPTION 'AUTHZ_CONVERSION_USER_ROLE_PARITY_IDS=%', bad_ids;
          END IF;
        END $$;
    """)
    )

    # Convert each legacy capability to the smallest equivalent role at the exact project site.
    capability_roles = (
        ("can_browse", "collaborator"),
        ("can_verify", "verifier"),
        ("can_upload", "fileUploader"),
        ("can_review_discrepancies", "discrepancy_reviewer"),
        ("can_export_data", "data_exporter"),
        ("can_view_analytics", "analytics_viewer"),
        ("can_create_datasets", "dataset_creator"),
        ("can_adjudicate_regrades", "regrade_adjudicator"),
    )
    for capability, role_name in capability_roles:
        op.execute(
            sa.text(f"""
            INSERT INTO authorization_grants (user_id, role_id, scope_type, project_lab_unit_id, active, created_at, updated_at)
            SELECT p.user_id, r.id, 'project_lab_unit', plu.id, p.active, p.created_at, p.updated_at
            FROM project_encounter_set_permissions p
            JOIN project_lab_units plu ON plu.project_id = p.project_id AND plu.lab_unit_id = p.lab_unit_id
            JOIN roles r ON r.name = :role_name
            WHERE p.{capability}
            ON CONFLICT DO NOTHING
        """).bindparams(role_name=role_name)
        )

        op.execute(
            sa.text(f"""
            DO $$ DECLARE bad_ids text;
            BEGIN
              SELECT string_agg(p.id::text, ',' ORDER BY p.id) INTO bad_ids
              FROM project_encounter_set_permissions p
              JOIN project_lab_units plu
                ON plu.project_id = p.project_id AND plu.lab_unit_id = p.lab_unit_id
              JOIN roles r ON r.name = :role_name
              WHERE p.{capability}
                AND NOT EXISTS (
                  SELECT 1 FROM authorization_grants g
                  WHERE g.user_id = p.user_id AND g.role_id = r.id
                    AND g.scope_type = 'project_lab_unit'
                    AND g.project_lab_unit_id = plu.id
                    AND g.active = p.active
                );
              IF bad_ids IS NOT NULL THEN
                RAISE EXCEPTION 'AUTHZ_CONVERSION_CAPABILITY_PARITY_IDS=%', bad_ids;
              END IF;
            END $$;
        """).bindparams(role_name=role_name)
        )

    op.execute(
        sa.text("""
        DO $$ DECLARE bad_ids text;
        BEGIN
          SELECT string_agg(g.id::text, ',' ORDER BY g.id) INTO bad_ids
          FROM project_role_grants g
          LEFT JOIN project_lab_units plu
            ON plu.project_id = g.project_id AND plu.lab_unit_id = g.lab_unit_id
          WHERE NOT EXISTS (
            SELECT 1 FROM authorization_grants target
            WHERE target.user_id = g.user_id AND target.role_id = g.role_id
              AND target.active = g.active
              AND (
                (g.scope_type = 'project'
                  AND target.scope_type = 'project'
                  AND target.project_id = g.project_id)
                OR
                (g.scope_type = 'lab_unit'
                  AND target.scope_type = 'project_lab_unit'
                  AND target.project_lab_unit_id = plu.id)
              )
          );
          IF bad_ids IS NOT NULL THEN
            RAISE EXCEPTION 'AUTHZ_CONVERSION_PROJECT_GRANT_PARITY_IDS=%', bad_ids;
          END IF;
        END $$;
    """)
    )

    op.execute(
        sa.text("""
        INSERT INTO project_lab_unit_authorization_policies (
            project_lab_unit_id, grade_export_enabled, dataset_creation_enabled,
            dataset_sharing_enabled, created_at, updated_at
        )
        SELECT id, false, false, false, now(), now() FROM project_lab_units
        ON CONFLICT (project_lab_unit_id) DO NOTHING
    """)
    )
    op.execute(sa.text(AUDIT_IMMUTABLE_SQL))
    op.execute(
        sa.text("""
        DO $$ DECLARE grant_count bigint; policy_count bigint;
                      user_role_count bigint; project_grant_count bigint;
                      capability_count bigint;
        BEGIN
          SELECT count(*) INTO grant_count FROM authorization_grants;
          SELECT count(*) INTO policy_count FROM project_lab_unit_authorization_policies;
          SELECT count(*) INTO user_role_count FROM user_roles;
          SELECT count(*) INTO project_grant_count FROM project_role_grants;
          SELECT coalesce(sum(
            can_browse::integer + can_verify::integer + can_upload::integer
            + can_review_discrepancies::integer + can_export_data::integer
            + can_view_analytics::integer + can_create_datasets::integer
            + can_adjudicate_regrades::integer
          ), 0) INTO capability_count FROM project_encounter_set_permissions;
          RAISE NOTICE 'AUTHZ_CONVERSION_COUNTS user_roles=% project_grants=% capabilities=% grants=% site_policies=%',
            user_role_count, project_grant_count, capability_count,
            grant_count, policy_count;
        END $$;
    """)
    )


def downgrade() -> None:
    """Remove the expansion only when no grant would be silently lost."""
    tables = _table_names()
    if "authorization_upload_profile_assignments" in tables:
        op.execute(
            sa.text("""
            DO $$ DECLARE bad_ids text;
            BEGIN
              SELECT string_agg(a.id::text, ',' ORDER BY a.id) INTO bad_ids
              FROM authorization_upload_profile_assignments a
              WHERE a.created_by_user_id IS NOT NULL OR NOT a.active
                OR NOT EXISTS (
                  SELECT 1 FROM user_roles ur
                  JOIN roles r ON r.id = ur.role_id
                  WHERE ur.user_id = a.user_id
                    AND (
                      (r.name IN ('fileUploader','pregraded_uploader','optometrist')
                       AND EXISTS (
                         SELECT 1 FROM user_lab_units ulu
                         WHERE ulu.user_id = a.user_id
                           AND ulu.lab_unit_id = a.lab_unit_id
                       ))
                      OR r.name = 'admin'
                    )
                );
              IF bad_ids IS NOT NULL THEN
                RAISE EXCEPTION 'AUTHZ_DOWNGRADE_UPLOAD_ASSIGNMENT_IDS=%', bad_ids;
              END IF;
            END $$;
        """)
        )
        op.drop_table("authorization_upload_profile_assignments")
    if "password_reset_credentials" in tables:
        op.execute(
            sa.text("""
            DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM password_reset_credentials) THEN
                RAISE EXCEPTION 'AUTHZ_DOWNGRADE_PASSWORD_RESET_CREDENTIALS_PRESENT';
              END IF;
            END $$;
        """)
        )
        op.drop_table("password_reset_credentials")
    if "authorization_resource_scopes" in tables:
        op.execute(
            sa.text("""
            DO $$ DECLARE bad_ids text;
            BEGIN
              SELECT string_agg(id::text, ',' ORDER BY id) INTO bad_ids
              FROM authorization_resource_scopes
              WHERE resource_type NOT IN ('upload_target','dataset','ad_hoc_task')
                 OR created_by_user_id IS NOT NULL
                 OR updated_by_user_id IS NOT NULL
                 OR requester_user_id IS NOT NULL
                 OR automation_rule_id IS NOT NULL
                 OR NOT active
                 OR NOT domain_valid;
              IF bad_ids IS NOT NULL THEN
                RAISE EXCEPTION 'AUTHZ_DOWNGRADE_RESOURCE_SCOPE_BINDING_IDS=%', bad_ids;
              END IF;
            END $$;
        """)
        )
        op.drop_table("authorization_resource_scopes")
    if "authorization_grants" in tables:
        op.execute(
            sa.text("""
            DO $$ DECLARE bad_ids text;
            BEGIN
              SELECT string_agg(g.id::text, ',' ORDER BY g.id) INTO bad_ids
              FROM authorization_grants g
              JOIN roles r ON r.id = g.role_id
              WHERE g.description IS NOT NULL
                OR g.created_by_user_id IS NOT NULL
                OR g.updated_by_user_id IS NOT NULL
                OR g.deactivated_by_user_id IS NOT NULL
                OR g.deactivated_at IS NOT NULL
                OR NOT (
                (g.scope_type = 'system' AND g.active AND r.name = 'admin' AND EXISTS (
                  SELECT 1 FROM user_roles ur WHERE ur.user_id = g.user_id AND ur.role_id = g.role_id
                ))
                OR
                (g.scope_type = 'hospital' AND g.active AND r.name = 'local_admin' AND EXISTS (
                  SELECT 1 FROM user_roles ur
                  JOIN users u ON u.id = ur.user_id
                  WHERE ur.user_id = g.user_id AND ur.role_id = g.role_id
                    AND u.hospital_id = g.hospital_id
                ))
                OR
                (g.scope_type = 'lab_unit' AND g.active AND EXISTS (
                  SELECT 1 FROM user_roles ur
                  JOIN user_lab_units ulu ON ulu.user_id = ur.user_id
                  WHERE ur.user_id = g.user_id AND ur.role_id = g.role_id
                    AND ulu.lab_unit_id = g.lab_unit_id
                ))
                OR
                (g.scope_type = 'project' AND EXISTS (
                  SELECT 1 FROM project_role_grants prg
                  WHERE prg.user_id = g.user_id AND prg.role_id = g.role_id
                    AND prg.project_id = g.project_id AND prg.scope_type = 'project'
                    AND prg.active = g.active
                ))
                OR
                (g.scope_type = 'project_lab_unit' AND EXISTS (
                  SELECT 1 FROM project_role_grants prg
                  JOIN project_lab_units plu
                    ON plu.project_id = prg.project_id AND plu.lab_unit_id = prg.lab_unit_id
                  WHERE prg.user_id = g.user_id AND prg.role_id = g.role_id
                    AND prg.scope_type = 'lab_unit' AND plu.id = g.project_lab_unit_id
                    AND prg.active = g.active
                ))
                OR
                (g.scope_type = 'project_lab_unit' AND EXISTS (
                  SELECT 1 FROM project_encounter_set_permissions p
                  JOIN project_lab_units plu
                    ON plu.project_id = p.project_id AND plu.lab_unit_id = p.lab_unit_id
                  WHERE p.user_id = g.user_id AND plu.id = g.project_lab_unit_id
                    AND p.active = g.active
                    AND (
                      (r.name = 'collaborator' AND p.can_browse)
                      OR (r.name = 'verifier' AND p.can_verify)
                      OR (r.name = 'fileUploader' AND p.can_upload)
                      OR (r.name = 'discrepancy_reviewer' AND p.can_review_discrepancies)
                      OR (r.name = 'data_exporter' AND p.can_export_data)
                      OR (r.name = 'analytics_viewer' AND p.can_view_analytics)
                      OR (r.name = 'dataset_creator' AND p.can_create_datasets)
                      OR (r.name = 'regrade_adjudicator' AND p.can_adjudicate_regrades)
                    )
                ))
              );
              IF bad_ids IS NOT NULL THEN
                RAISE EXCEPTION 'AUTHZ_DOWNGRADE_UNREPRESENTABLE_GRANT_IDS=%', bad_ids;
              END IF;
            END $$;
        """)
        )

    if "authorization_audit_events" in tables:
        op.execute(
            sa.text("""
            DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM authorization_audit_events) THEN
                RAISE EXCEPTION 'AUTHZ_DOWNGRADE_AUDIT_HISTORY_PRESENT';
              END IF;
            END $$;
        """)
        )
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS trg_authorization_audit_immutable ON authorization_audit_events"
            )
        )
        op.drop_table("authorization_audit_events")
        op.execute(
            sa.text("DROP FUNCTION IF EXISTS reject_authorization_audit_mutation()")
        )
    if "project_lab_unit_authorization_policies" in tables:
        op.execute(
            sa.text("""
            DO $$ BEGIN
              IF EXISTS (
                SELECT 1 FROM project_lab_unit_authorization_policies
                WHERE grade_export_enabled OR dataset_creation_enabled
                  OR dataset_sharing_enabled
              ) THEN
                RAISE EXCEPTION 'AUTHZ_DOWNGRADE_POLICY_STATE_PRESENT';
              END IF;
            END $$;
        """)
        )
        op.drop_table("project_lab_unit_authorization_policies")
    if "authorization_grants" in tables:
        op.drop_table("authorization_grants")
