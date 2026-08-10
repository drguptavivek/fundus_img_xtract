"""backfill DR-DME EncounterSet scopes

Revision ID: 531cf24d8a10
Revises: 420be25b2699
Create Date: 2026-08-10 12:30:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "531cf24d8a10"
down_revision: Union[str, Sequence[str], None] = "420be25b2699"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


MARKER = "531cf24d8a10"


def upgrade() -> None:
    """Make pre-enforcement DR policies complete DR-DME linked packages."""
    conn = op.get_bind()
    conn.execute(sa.text("""
        INSERT INTO diseases (name, grading_scope, remidio_ocr_linkage)
        VALUES ('DME Encounter Status', 'encounter', 'none')
        ON CONFLICT (name) DO NOTHING
    """))
    dme_set_scope = conn.execute(sa.text("""
        SELECT grading_scope FROM diseases WHERE name = 'DME Encounter Status'
    """)).scalar_one()
    if dme_set_scope != "encounter":
        raise RuntimeError("DME Encounter Status exists but is not encounter-scoped")

    conn.execute(sa.text("""
        WITH target AS (
            SELECT id FROM diseases WHERE name = 'DME Encounter Status'
        ), source AS (
            SELECT id FROM diseases WHERE name = 'DR Encounter Status'
        )
        INSERT INTO disease_gradings (
            disease_id, impression, display_order, is_active,
            prioritize_for_task_selection, is_ungradable, guidelines
        )
        SELECT target.id, grading.impression, grading.display_order,
               grading.is_active, grading.prioritize_for_task_selection,
               grading.is_ungradable, grading.guidelines
        FROM target
        CROSS JOIN source
        JOIN disease_gradings grading ON grading.disease_id = source.id
        ON CONFLICT (disease_id, impression) DO NOTHING
    """))

    # The profile-level allow-list must include DME or a future admin save would
    # reject the package even though its package policy is complete.
    conn.execute(sa.text("""
        WITH diseases_by_name AS (
            SELECT
                (SELECT id FROM diseases WHERE name = 'DR') AS dr_id,
                (SELECT id FROM diseases WHERE name = 'DME') AS dme_id
        ), dr_mappings AS (
            SELECT DISTINCT package.upload_profile_encounter_set_type_id AS mapping_id
            FROM upload_profile_est_grading_packages package
            CROSS JOIN diseases_by_name disease
            WHERE package.active IS TRUE
              AND package.grading_mode = 'disease_specific'
              AND COALESCE(
                    (package.scope_config_json->>'root_image_grading_scheme_id')::integer,
                    package.default_image_grading_scheme_id
                  ) = disease.dr_id
        )
        INSERT INTO upload_profile_est_image_grading_schemes (
            upload_profile_encounter_set_type_id, disease_id,
            is_default, display_order, active
        )
        SELECT mapping.mapping_id, disease.dme_id, false,
               COALESCE((
                   SELECT max(existing.display_order) + 1
                   FROM upload_profile_est_image_grading_schemes existing
                   WHERE existing.upload_profile_encounter_set_type_id = mapping.mapping_id
               ), 1), true
        FROM dr_mappings mapping
        CROSS JOIN diseases_by_name disease
        ON CONFLICT (upload_profile_encounter_set_type_id, disease_id)
        DO UPDATE SET active = true
    """))

    conn.execute(sa.text("""
        WITH diseases_by_name AS (
            SELECT
                (SELECT id FROM diseases WHERE name = 'DR') AS dr_id,
                (SELECT id FROM diseases WHERE name = 'DME') AS dme_id
        ), dr_packages AS (
            SELECT package.id
            FROM upload_profile_est_grading_packages package
            CROSS JOIN diseases_by_name disease
            WHERE package.active IS TRUE
              AND package.grading_mode = 'disease_specific'
              AND COALESCE(
                    (package.scope_config_json->>'root_image_grading_scheme_id')::integer,
                    package.default_image_grading_scheme_id
                  ) = disease.dr_id
        )
        INSERT INTO upload_profile_est_package_image_schemes (
            package_id, disease_id, is_default, auto_create_policy,
            negative_controls_per_positive, metadata_field_key,
            metadata_match_value, display_order, active
        )
        SELECT package.id, disease.dme_id, false,
               root_scheme.auto_create_policy,
               root_scheme.negative_controls_per_positive,
               root_scheme.metadata_field_key,
               root_scheme.metadata_match_value,
               root_scheme.display_order + 1, true
        FROM dr_packages package
        CROSS JOIN diseases_by_name disease
        JOIN upload_profile_est_package_image_schemes root_scheme
          ON root_scheme.package_id = package.id
         AND root_scheme.disease_id = disease.dr_id
        ON CONFLICT (package_id, disease_id) DO UPDATE
        SET active = true,
            auto_create_policy = EXCLUDED.auto_create_policy,
            negative_controls_per_positive = EXCLUDED.negative_controls_per_positive,
            metadata_field_key = EXCLUDED.metadata_field_key,
            metadata_match_value = EXCLUDED.metadata_match_value
    """))

    conn.execute(sa.text("""
        WITH diseases_by_name AS (
            SELECT
                (SELECT id FROM diseases WHERE name = 'DR') AS dr_id,
                (SELECT id FROM diseases WHERE name = 'DME Encounter Status') AS dme_set_id
        ), dr_packages AS (
            SELECT package.id
            FROM upload_profile_est_grading_packages package
            CROSS JOIN diseases_by_name disease
            WHERE package.active IS TRUE
              AND package.grading_mode = 'disease_specific'
              AND COALESCE(
                    (package.scope_config_json->>'root_image_grading_scheme_id')::integer,
                    package.default_image_grading_scheme_id
                  ) = disease.dr_id
        )
        INSERT INTO upload_profile_est_package_encounter_schemes (
            package_id, disease_id, display_order, active
        )
        SELECT package.id, disease.dme_set_id,
               COALESCE((
                   SELECT max(existing.display_order) + 1
                   FROM upload_profile_est_package_encounter_schemes existing
                   WHERE existing.package_id = package.id
               ), 1), true
        FROM dr_packages package
        CROSS JOIN diseases_by_name disease
        ON CONFLICT (package_id, disease_id) DO UPDATE SET active = true
    """))

    conn.execute(sa.text("""
        WITH diseases_by_name AS (
            SELECT
                (SELECT id FROM diseases WHERE name = 'DR') AS dr_id,
                (SELECT id FROM diseases WHERE name = 'DME') AS dme_id,
                (SELECT id FROM diseases WHERE name = 'DME Encounter Status') AS dme_set_id
        )
        UPDATE upload_profile_est_grading_packages package
        SET scope_config_json = jsonb_set(
                jsonb_set(
                    COALESCE(package.scope_config_json, '{}'::jsonb),
                    '{scopes}',
                    COALESCE(package.scope_config_json->'scopes', '[]'::jsonb)
                    || jsonb_build_array(jsonb_build_object(
                        'scope_disease_id', disease.dme_id,
                        'image_grading_scheme_ids', jsonb_build_array(disease.dme_id),
                        'encounter_grading_scheme_id', disease.dme_set_id,
                        'parent_scope_disease_id', disease.dr_id,
                        'link_role', 'linked'
                    )),
                    true
                ),
                '{linked_scope_backfill}',
                to_jsonb(CAST(:marker AS text)),
                true
            ),
            policy_revision = package.policy_revision + 1,
            updated_at = now()
        FROM diseases_by_name disease
        WHERE package.active IS TRUE
          AND package.grading_mode = 'disease_specific'
          AND COALESCE(
                (package.scope_config_json->>'root_image_grading_scheme_id')::integer,
                package.default_image_grading_scheme_id
              ) = disease.dr_id
          AND NOT EXISTS (
              SELECT 1
              FROM jsonb_array_elements(
                  COALESCE(package.scope_config_json->'scopes', '[]'::jsonb)
              ) scope
              WHERE (scope->>'scope_disease_id')::integer = disease.dme_id
          )
    """), {"marker": MARKER})


def downgrade() -> None:
    """Remove only policy rows tagged by this backfill; preserve grade schemas."""
    conn = op.get_bind()
    conn.execute(sa.text("""
        WITH diseases_by_name AS (
            SELECT
                (SELECT id FROM diseases WHERE name = 'DME') AS dme_id,
                (SELECT id FROM diseases WHERE name = 'DME Encounter Status') AS dme_set_id
        ), tagged_packages AS (
            SELECT id
            FROM upload_profile_est_grading_packages
            WHERE scope_config_json->>'linked_scope_backfill' = :marker
        )
        DELETE FROM upload_profile_est_package_encounter_schemes scheme
        USING tagged_packages package, diseases_by_name disease
        WHERE scheme.package_id = package.id
          AND scheme.disease_id = disease.dme_set_id
    """), {"marker": MARKER})
    conn.execute(sa.text("""
        WITH disease AS (
            SELECT id AS dme_id FROM diseases WHERE name = 'DME'
        ), tagged_packages AS (
            SELECT id
            FROM upload_profile_est_grading_packages
            WHERE scope_config_json->>'linked_scope_backfill' = :marker
        )
        DELETE FROM upload_profile_est_package_image_schemes scheme
        USING tagged_packages package, disease
        WHERE scheme.package_id = package.id
          AND scheme.disease_id = disease.dme_id
    """), {"marker": MARKER})
    conn.execute(sa.text("""
        WITH disease AS (
            SELECT id AS dme_id FROM diseases WHERE name = 'DME'
        )
        UPDATE upload_profile_est_grading_packages package
        SET scope_config_json = jsonb_set(
                package.scope_config_json - 'linked_scope_backfill',
                '{scopes}',
                COALESCE((
                    SELECT jsonb_agg(scope_element)
                    FROM jsonb_array_elements(package.scope_config_json->'scopes') scope_element
                    WHERE (scope_element->>'scope_disease_id')::integer <> disease.dme_id
                ), '[]'::jsonb),
                true
            ),
            policy_revision = greatest(package.policy_revision - 1, 1),
            updated_at = now()
        FROM disease
        WHERE package.scope_config_json->>'linked_scope_backfill' = :marker
    """), {"marker": MARKER})
    conn.execute(sa.text("""
        WITH disease AS (
            SELECT id AS dme_id FROM diseases WHERE name = 'DME'
        )
        DELETE FROM upload_profile_est_image_grading_schemes profile_scheme
        USING disease
        WHERE profile_scheme.disease_id = disease.dme_id
          AND NOT EXISTS (
              SELECT 1
              FROM upload_profile_est_grading_packages package
              JOIN upload_profile_est_package_image_schemes package_scheme
                ON package_scheme.package_id = package.id
              WHERE package.upload_profile_encounter_set_type_id =
                    profile_scheme.upload_profile_encounter_set_type_id
                AND package_scheme.disease_id = disease.dme_id
          )
    """))
