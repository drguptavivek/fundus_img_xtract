"""Add project-owned automated remote inference rules.

Revision ID: e9f0a1b2c3d4
Revises: c7d8e9f0a1b2
Create Date: 2026-08-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "e9f0a1b2c3d4"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())
    if "project_automated_remote_inference_rules" not in inspector.get_table_names():
        op.create_table(
            "project_automated_remote_inference_rules",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("disease_id", sa.Integer(), nullable=False),
            sa.Column("ai_model_id", sa.Integer(), nullable=False),
            sa.Column("upload_kind", sa.String(length=32), nullable=False),
            sa.Column("trigger_timing", sa.String(length=32), server_default="on_image_received", nullable=False),
            sa.Column("encounter_eligibility", sa.String(length=64), server_default="always", nullable=False),
            sa.Column("image_selection", sa.String(length=64), server_default="all_eligible_images", nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("upload_kind IN ('direct_image','pregraded','remidio','encounter_set')", name="ck_project_automated_remote_inference_upload_kind"),
            sa.CheckConstraint("trigger_timing IN ('on_image_received','on_report_received','after_verification')", name="ck_project_automated_remote_inference_trigger"),
            sa.CheckConstraint("encounter_eligibility IN ('always','if_matching_report_present','if_matching_report_absent','if_any_report_present')", name="ck_project_automated_remote_inference_eligibility"),
            sa.CheckConstraint("image_selection IN ('all_eligible_images','disc_focused_images','macula_focused_images','disc_or_macula_images')", name="ck_project_automated_remote_inference_image_selection"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["disease_id"], ["diseases.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["ai_model_id"], ["ai_models.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("project_id", "disease_id", "ai_model_id", "upload_kind", name="uq_project_automated_remote_inference_rule"),
        )
        op.create_index("ix_project_automated_remote_inference_project_active", "project_automated_remote_inference_rules", ["project_id", "active"])
        op.create_index("ix_project_automated_remote_inference_rules_project_id", "project_automated_remote_inference_rules", ["project_id"])
        op.create_index("ix_project_automated_remote_inference_rules_disease_id", "project_automated_remote_inference_rules", ["disease_id"])
        op.create_index("ix_project_automated_remote_inference_rules_ai_model_id", "project_automated_remote_inference_rules", ["ai_model_id"])
        op.create_index("ix_project_automated_remote_inference_rules_upload_kind", "project_automated_remote_inference_rules", ["upload_kind"])
        op.create_index("ix_project_automated_remote_inference_rules_active", "project_automated_remote_inference_rules", ["active"])

    # Preserve only the currently effective project assignments. Upload-profile
    # AI workflow rows are intentionally not migrated: they were a separate,
    # conflicting source and require the documented manual review.
    op.execute(sa.text("""
        INSERT INTO project_automated_remote_inference_rules
            (project_id, disease_id, ai_model_id, upload_kind, trigger_timing,
             encounter_eligibility, image_selection, active, display_order,
             created_at, updated_at)
        SELECT assignment.project_id, rule.disease_id, rule.ai_model_id,
               rule.upload_kind,
               CASE WHEN rule.trigger_timing = 'manual_only'
                    THEN 'on_image_received' ELSE rule.trigger_timing END,
               rule.encounter_eligibility, rule.image_selection,
               assignment.active AND policy.active AND rule.active,
               rule.display_order, NOW(), NOW()
          FROM project_remote_inference_policies assignment
          JOIN remote_inference_policies policy
            ON policy.id = assignment.remote_inference_policy_id
          JOIN remote_inference_policy_rules rule
            ON rule.policy_id = policy.id
        ON CONFLICT (project_id, disease_id, ai_model_id, upload_kind) DO NOTHING
    """))
    op.execute(sa.text("""
        UPDATE project_automated_remote_inference_rules target
           SET active = false, updated_at = NOW()
         WHERE active = true
           AND NOT EXISTS (
               SELECT 1
                 FROM project_upload_profiles mapping
                 JOIN upload_profiles profile ON profile.id = mapping.upload_profile_id
                 JOIN upload_profile_kinds kind ON kind.upload_profile_id = profile.id
                WHERE mapping.project_id = target.project_id
                  AND mapping.active = true AND profile.active = true
                  AND kind.upload_kind = target.upload_kind
                  AND (
                    (target.upload_kind <> 'encounter_set' AND EXISTS (
                        SELECT 1 FROM upload_profile_diseases disease
                         WHERE disease.upload_profile_id = profile.id
                           AND disease.disease_id = target.disease_id
                    ))
                    OR
                    (target.upload_kind = 'encounter_set' AND EXISTS (
                        SELECT 1
                          FROM upload_profile_encounter_set_types config
                         WHERE config.upload_profile_id = profile.id AND config.active = true
                           AND (
                             EXISTS (
                               SELECT 1 FROM upload_profile_est_image_grading_schemes scheme
                                WHERE scheme.upload_profile_encounter_set_type_id = config.id
                                  AND scheme.disease_id = target.disease_id AND scheme.active = true
                             )
                             OR EXISTS (
                               SELECT 1
                                 FROM upload_profile_est_grading_packages package
                                 JOIN upload_profile_est_package_image_schemes scheme
                                   ON scheme.package_id = package.id
                                WHERE package.upload_profile_encounter_set_type_id = config.id
                                  AND package.active = true AND package.applicability <> 'disabled'
                                  AND scheme.disease_id = target.disease_id AND scheme.active = true
                             )
                           )
                    ))
                  )
           )
    """))

    # Retain legacy records for audit only. They are inactive and no application
    # runtime or admin endpoint reads them after this revision.
    op.execute(sa.text("UPDATE upload_profile_ai_workflows SET active = false WHERE active = true"))
    op.execute(sa.text("UPDATE project_remote_inference_policies SET active = false WHERE active = true"))
    op.execute(sa.text("UPDATE remote_inference_policies SET active = false WHERE active = true"))


def downgrade():
    inspector = inspect(op.get_bind())
    if "project_automated_remote_inference_rules" in inspector.get_table_names():
        op.drop_table("project_automated_remote_inference_rules")
