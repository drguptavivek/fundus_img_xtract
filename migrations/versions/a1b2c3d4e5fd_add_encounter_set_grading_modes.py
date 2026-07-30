"""Add EncounterSet grading modes.

Revision ID: a1b2c3d4e5fd
Revises: a1b2c3d4e5fc
Create Date: 2026-07-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5fd"
down_revision = "a1b2c3d4e5fc"
branch_labels = None
depends_on = None


CONFIG_PACKAGE_TABLE = "upload_profile_est_grading_packages"
RUNTIME_PACKAGE_TABLE = "encounter_set_grading_packages"


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table_name: str) -> set[str]:
    if table_name not in _tables(conn):
        return set()
    return {column["name"] for column in sa.inspect(conn).get_columns(table_name)}


def _checks(conn, table_name: str) -> set[str]:
    if table_name not in _tables(conn):
        return set()
    return {
        constraint["name"]
        for constraint in sa.inspect(conn).get_check_constraints(table_name)
        if constraint.get("name")
    }


def _add_mode_column(conn, table_name: str, check_name: str) -> None:
    if table_name not in _tables(conn):
        return
    if "grading_mode" not in _columns(conn, table_name):
        op.add_column(
            table_name,
            sa.Column("grading_mode", sa.String(length=32), nullable=False, server_default="unified"),
        )
    if check_name not in _checks(conn, table_name):
        op.create_check_constraint(
            check_name,
            table_name,
            "grading_mode IN ('unified','disease_specific')",
        )


def upgrade():
    conn = op.get_bind()
    _add_mode_column(conn, CONFIG_PACKAGE_TABLE, "ck_up_est_grading_package_mode")
    _add_mode_column(conn, RUNTIME_PACKAGE_TABLE, "ck_encounter_set_grading_package_mode")

    op.execute(_seed_disease_sql("DR Encounter Status", "Generic Ophthalmic Encounter"))
    op.execute(_seed_disease_sql("Glaucoma Encounter Status", "Generic Ophthalmic Encounter"))
    op.execute(_configure_integrated_profiles_sql())
    op.execute(_split_ungraded_integrated_runtime_packages_sql())
    op.execute(_mark_graded_mixed_runtime_packages_legacy_sql())


def downgrade():
    conn = op.get_bind()
    if CONFIG_PACKAGE_TABLE in _tables(conn):
        if "ck_up_est_grading_package_mode" in _checks(conn, CONFIG_PACKAGE_TABLE):
            op.drop_constraint("ck_up_est_grading_package_mode", CONFIG_PACKAGE_TABLE, type_="check")
        if "grading_mode" in _columns(conn, CONFIG_PACKAGE_TABLE):
            op.drop_column(CONFIG_PACKAGE_TABLE, "grading_mode")
    if RUNTIME_PACKAGE_TABLE in _tables(conn):
        if "ck_encounter_set_grading_package_mode" in _checks(conn, RUNTIME_PACKAGE_TABLE):
            op.drop_constraint("ck_encounter_set_grading_package_mode", RUNTIME_PACKAGE_TABLE, type_="check")
        if "grading_mode" in _columns(conn, RUNTIME_PACKAGE_TABLE):
            op.drop_column(RUNTIME_PACKAGE_TABLE, "grading_mode")


def _seed_disease_sql(target_name: str, source_name: str) -> str:
    target = target_name.replace("'", "''")
    source = source_name.replace("'", "''")
    return f"""
    WITH target_disease AS (
        INSERT INTO diseases (name, grading_scope, remidio_ocr_linkage)
        VALUES ('{target}', 'encounter', 'none')
        ON CONFLICT (name) DO UPDATE
        SET grading_scope = EXCLUDED.grading_scope
        RETURNING id
    ),
    source_disease AS (
        SELECT id FROM diseases WHERE name = '{source}'
    ),
    copied_labels AS (
        INSERT INTO disease_gradings (
            disease_id,
            impression,
            display_order,
            is_active,
            prioritize_for_task_selection,
            is_ungradable,
            guidelines
        )
        SELECT
            target_disease.id,
            source_labels.impression,
            source_labels.display_order,
            source_labels.is_active,
            source_labels.prioritize_for_task_selection,
            source_labels.is_ungradable,
            source_labels.guidelines
        FROM target_disease
        JOIN source_disease ON true
        JOIN disease_gradings source_labels ON source_labels.disease_id = source_disease.id
        WHERE NOT EXISTS (
            SELECT 1
            FROM disease_gradings existing
            WHERE existing.disease_id = target_disease.id
              AND existing.impression = source_labels.impression
        )
        RETURNING id
    )
    INSERT INTO gradings_features (disease_grading_id, sr_no, label)
    SELECT target_labels.id, source_features.sr_no, source_features.label
    FROM target_disease
    JOIN source_disease ON true
    JOIN disease_gradings source_labels ON source_labels.disease_id = source_disease.id
    JOIN disease_gradings target_labels
      ON target_labels.disease_id = target_disease.id
     AND target_labels.impression = source_labels.impression
    JOIN gradings_features source_features ON source_features.disease_grading_id = source_labels.id
    WHERE NOT EXISTS (
        SELECT 1
        FROM gradings_features existing
        WHERE existing.disease_grading_id = target_labels.id
          AND existing.sr_no = source_features.sr_no
    );
    """


def _configure_integrated_profiles_sql() -> str:
    sql = """
    WITH schemes AS (
        SELECT
            (SELECT id FROM diseases WHERE name = 'DR') AS dr_image_id,
            (SELECT id FROM diseases WHERE name = 'Glaucoma') AS glaucoma_image_id,
            (SELECT id FROM diseases WHERE name = 'DR Encounter Status') AS dr_encounter_id,
            (SELECT id FROM diseases WHERE name = 'Glaucoma Encounter Status') AS glaucoma_encounter_id
    ),
    integrated_mappings AS (
        SELECT est.id AS mapping_id
        FROM upload_profile_encounter_set_types est
        JOIN upload_profiles up ON up.id = est.upload_profile_id
        JOIN project_upload_profiles pup ON pup.upload_profile_id = up.id AND pup.active IS TRUE
        JOIN projects pr ON pr.id = pup.project_id
        WHERE pr.title = 'Integrated DR Glaucoma Screening'
          AND up.id IN (1, 7)
          AND est.active IS TRUE
    ),
    old_packages AS (
        SELECT pkg.*
        FROM upload_profile_est_grading_packages pkg
        JOIN integrated_mappings im ON im.mapping_id = pkg.upload_profile_encounter_set_type_id
        WHERE pkg.active IS TRUE
    ),
    dr_packages AS (
        INSERT INTO upload_profile_est_grading_packages (
            upload_profile_encounter_set_type_id,
            name,
            code,
            applicability,
            grading_mode,
            default_image_grading_scheme_id,
            display_order,
            active
        )
        SELECT im.mapping_id, 'DR EncounterSet Package', 'dr_encounter_set', 'always', 'disease_specific',
               schemes.dr_image_id, 1, true
        FROM integrated_mappings im
        CROSS JOIN schemes
        ON CONFLICT (upload_profile_encounter_set_type_id, code) DO UPDATE
        SET name = EXCLUDED.name,
            grading_mode = EXCLUDED.grading_mode,
            default_image_grading_scheme_id = EXCLUDED.default_image_grading_scheme_id,
            active = true
        RETURNING id, upload_profile_encounter_set_type_id
    ),
    glaucoma_packages AS (
        INSERT INTO upload_profile_est_grading_packages (
            upload_profile_encounter_set_type_id,
            name,
            code,
            applicability,
            grading_mode,
            default_image_grading_scheme_id,
            display_order,
            active
        )
        SELECT im.mapping_id, 'Glaucoma EncounterSet Package', 'glaucoma_encounter_set', 'always', 'disease_specific',
               schemes.glaucoma_image_id, 2, true
        FROM integrated_mappings im
        CROSS JOIN schemes
        ON CONFLICT (upload_profile_encounter_set_type_id, code) DO UPDATE
        SET name = EXCLUDED.name,
            grading_mode = EXCLUDED.grading_mode,
            default_image_grading_scheme_id = EXCLUDED.default_image_grading_scheme_id,
            active = true
        RETURNING id, upload_profile_encounter_set_type_id
    ),
    dr_image_rows AS (
        INSERT INTO upload_profile_est_package_image_schemes (
            package_id,
            disease_id,
            is_default,
            auto_create_policy,
            negative_controls_per_positive,
            display_order,
            active
        )
        SELECT dr_packages.id, schemes.dr_image_id, true,
               COALESCE(old_image.auto_create_policy, 'remidio_dr_report_present'),
               COALESCE(old_image.negative_controls_per_positive, 0),
               1, true
        FROM dr_packages
        CROSS JOIN schemes
        LEFT JOIN old_packages old_package
          ON old_package.upload_profile_encounter_set_type_id = dr_packages.upload_profile_encounter_set_type_id
        LEFT JOIN upload_profile_est_package_image_schemes old_image
          ON old_image.package_id = old_package.id
         AND old_image.disease_id = schemes.dr_image_id
        ON CONFLICT (package_id, disease_id) DO UPDATE
        SET is_default = true,
            auto_create_policy = EXCLUDED.auto_create_policy,
            negative_controls_per_positive = EXCLUDED.negative_controls_per_positive,
            active = true
        RETURNING id
    ),
    glaucoma_image_rows AS (
        INSERT INTO upload_profile_est_package_image_schemes (
            package_id,
            disease_id,
            is_default,
            auto_create_policy,
            negative_controls_per_positive,
            display_order,
            active
        )
        SELECT glaucoma_packages.id, schemes.glaucoma_image_id, true,
               COALESCE(old_image.auto_create_policy, 'remidio_glaucoma_report_present'),
               COALESCE(old_image.negative_controls_per_positive, 0),
               1, true
        FROM glaucoma_packages
        CROSS JOIN schemes
        LEFT JOIN old_packages old_package
          ON old_package.upload_profile_encounter_set_type_id = glaucoma_packages.upload_profile_encounter_set_type_id
        LEFT JOIN upload_profile_est_package_image_schemes old_image
          ON old_image.package_id = old_package.id
         AND old_image.disease_id = schemes.glaucoma_image_id
        ON CONFLICT (package_id, disease_id) DO UPDATE
        SET is_default = true,
            auto_create_policy = EXCLUDED.auto_create_policy,
            negative_controls_per_positive = EXCLUDED.negative_controls_per_positive,
            active = true
        RETURNING id
    ),
    dr_encounter_rows AS (
        INSERT INTO upload_profile_est_package_encounter_schemes (package_id, disease_id, display_order, active)
        SELECT dr_packages.id, schemes.dr_encounter_id, 1, true
        FROM dr_packages
        CROSS JOIN schemes
        ON CONFLICT (package_id, disease_id) DO UPDATE
        SET active = true
        RETURNING id
    ),
    glaucoma_encounter_rows AS (
        INSERT INTO upload_profile_est_package_encounter_schemes (package_id, disease_id, display_order, active)
        SELECT glaucoma_packages.id, schemes.glaucoma_encounter_id, 1, true
        FROM glaucoma_packages
        CROSS JOIN schemes
        ON CONFLICT (package_id, disease_id) DO UPDATE
        SET active = true
        RETURNING id
    )
    UPDATE upload_profile_est_grading_packages old_package
    SET active = false
    FROM integrated_mappings im
    WHERE old_package.upload_profile_encounter_set_type_id = im.mapping_id
      AND old_package.code NOT IN ('dr_encounter_set', 'glaucoma_encounter_set');

    WITH schemes AS (
        SELECT
            (SELECT id FROM diseases WHERE name = 'DR Encounter Status') AS dr_encounter_id
    ),
    integrated_mappings AS (
        SELECT est.id AS mapping_id
        FROM upload_profile_encounter_set_types est
        JOIN upload_profiles up ON up.id = est.upload_profile_id
        JOIN project_upload_profiles pup ON pup.upload_profile_id = up.id AND pup.active IS TRUE
        JOIN projects pr ON pr.id = pup.project_id
        WHERE pr.title = 'Integrated DR Glaucoma Screening'
          AND up.id IN (1, 7)
          AND est.active IS TRUE
    )
    UPDATE upload_profile_encounter_set_types est
    SET encounter_grading_scheme_id = schemes.dr_encounter_id
    FROM schemes, integrated_mappings im
    WHERE est.id = im.mapping_id;
    """
    return sql


def _split_ungraded_integrated_runtime_packages_sql() -> str:
    uuid_expr = (
        "lower(substr(md5(random()::text || clock_timestamp()::text), 1, 8) || '-' || "
        "substr(md5(random()::text || clock_timestamp()::text), 1, 4) || '-' || "
        "substr(md5(random()::text || clock_timestamp()::text), 1, 4) || '-' || "
        "substr(md5(random()::text || clock_timestamp()::text), 1, 4) || '-' || "
        "substr(md5(random()::text || clock_timestamp()::text), 1, 12))"
    )
    sql = """
    WITH schemes AS (
        SELECT
            (SELECT id FROM diseases WHERE name = 'DR') AS dr_image_id,
            (SELECT id FROM diseases WHERE name = 'Glaucoma') AS glaucoma_image_id,
            (SELECT id FROM diseases WHERE name = 'Generic Ophthalmic Encounter') AS generic_encounter_id,
            (SELECT id FROM diseases WHERE name = 'DR Encounter Status') AS dr_encounter_id,
            (SELECT id FROM diseases WHERE name = 'Glaucoma Encounter Status') AS glaucoma_encounter_id
    ),
    splittable AS (
        SELECT pkg.id AS old_package_id, pkg.patient_encounter_id, pe.lab_unit_id, pe.upload_profile_id
        FROM encounter_set_grading_packages pkg
        JOIN patient_encounters pe ON pe.id = pkg.patient_encounter_id
        JOIN projects pr ON pr.id = pe.project_id
        WHERE pr.title = 'Integrated DR Glaucoma Screening'
          AND pe.upload_profile_id = 7
          AND NOT EXISTS (
              SELECT 1
              FROM grading_tasks task
              JOIN grades grade ON grade.task_id = task.id
              WHERE task.encounter_set_package_id = pkg.id
          )
          AND (
              SELECT COUNT(DISTINCT task.disease_id)
              FROM grading_tasks task
              WHERE task.encounter_set_package_id = pkg.id
          ) > 1
    ),
    config_packages AS (
        SELECT pe.id AS patient_encounter_id,
               dr_pkg.id AS dr_config_package_id,
               glaucoma_pkg.id AS glaucoma_config_package_id
        FROM patient_encounters pe
        JOIN upload_profile_encounter_set_types est ON est.upload_profile_id = pe.upload_profile_id AND est.active IS TRUE
        LEFT JOIN upload_profile_est_grading_packages dr_pkg
          ON dr_pkg.upload_profile_encounter_set_type_id = est.id
         AND dr_pkg.code = 'dr_encounter_set'
        LEFT JOIN upload_profile_est_grading_packages glaucoma_pkg
          ON glaucoma_pkg.upload_profile_encounter_set_type_id = est.id
         AND glaucoma_pkg.code = 'glaucoma_encounter_set'
    ),
    dr_runtime AS (
        INSERT INTO encounter_set_grading_packages (
            uuid,
            patient_encounter_id,
            upload_profile_est_grading_package_id,
            name,
            code,
            applicability,
            grading_mode,
            state,
            metadata_json
        )
        SELECT __UUID_EXPR__, s.patient_encounter_id, cp.dr_config_package_id, 'DR EncounterSet Package',
               'dr_encounter_set', 'always', 'disease_specific', 'pending',
               jsonb_build_object('source', 'migration_split', 'legacy_package_id', s.old_package_id)
        FROM splittable s
        LEFT JOIN config_packages cp ON cp.patient_encounter_id = s.patient_encounter_id
        ON CONFLICT (patient_encounter_id, code) DO UPDATE
        SET grading_mode = EXCLUDED.grading_mode
        RETURNING id, patient_encounter_id
    ),
    glaucoma_runtime AS (
        INSERT INTO encounter_set_grading_packages (
            uuid,
            patient_encounter_id,
            upload_profile_est_grading_package_id,
            name,
            code,
            applicability,
            grading_mode,
            state,
            metadata_json
        )
        SELECT __UUID_EXPR__, s.patient_encounter_id, cp.glaucoma_config_package_id, 'Glaucoma EncounterSet Package',
               'glaucoma_encounter_set', 'always', 'disease_specific', 'pending',
               jsonb_build_object('source', 'migration_split', 'legacy_package_id', s.old_package_id)
        FROM splittable s
        LEFT JOIN config_packages cp ON cp.patient_encounter_id = s.patient_encounter_id
        ON CONFLICT (patient_encounter_id, code) DO UPDATE
        SET grading_mode = EXCLUDED.grading_mode
        RETURNING id, patient_encounter_id
    ),
    moved_dr_tasks AS (
        UPDATE grading_tasks task
        SET encounter_set_package_id = dr_runtime.id,
            task_source = 'migration_split',
            updated_at = now()
        FROM dr_runtime
        JOIN schemes ON true
        WHERE task.patient_encounter_id IS NULL
          AND task.encounter_set_image_id IS NOT NULL
          AND task.disease_id = schemes.dr_image_id
          AND task.encounter_set_package_id IN (SELECT old_package_id FROM splittable)
          AND EXISTS (
              SELECT 1 FROM encounter_set_images img
              WHERE img.id = task.encounter_set_image_id
                AND img.patient_encounter_id = dr_runtime.patient_encounter_id
          )
        RETURNING task.id
    ),
    moved_glaucoma_tasks AS (
        UPDATE grading_tasks task
        SET encounter_set_package_id = glaucoma_runtime.id,
            task_source = 'migration_split',
            updated_at = now()
        FROM glaucoma_runtime
        JOIN schemes ON true
        WHERE task.patient_encounter_id IS NULL
          AND task.encounter_set_image_id IS NOT NULL
          AND task.disease_id = schemes.glaucoma_image_id
          AND task.encounter_set_package_id IN (SELECT old_package_id FROM splittable)
          AND EXISTS (
              SELECT 1 FROM encounter_set_images img
              WHERE img.id = task.encounter_set_image_id
                AND img.patient_encounter_id = glaucoma_runtime.patient_encounter_id
          )
        RETURNING task.id
    ),
    deleted_generic_tasks AS (
        DELETE FROM grading_tasks task
        USING schemes
        WHERE task.encounter_set_package_id IN (SELECT old_package_id FROM splittable)
          AND task.grading_target_level = 'encounter'
          AND task.patient_encounter_id IS NOT NULL
          AND task.disease_id = schemes.generic_encounter_id
          AND NOT EXISTS (SELECT 1 FROM grades grade WHERE grade.task_id = task.id)
        RETURNING task.id
    ),
    dr_encounter_tasks AS (
        INSERT INTO grading_tasks (
            uuid,
            patient_encounter_id,
            encounter_set_package_id,
            disease_id,
            lab_unit_id,
            state,
            grading_target_level,
            task_source,
            created_at,
            updated_at
        )
        SELECT __UUID_EXPR__, dr_runtime.patient_encounter_id, dr_runtime.id,
               schemes.dr_encounter_id, pe.lab_unit_id, 'pending', 'encounter',
               'migration_split', now(), now()
        FROM dr_runtime
        JOIN patient_encounters pe ON pe.id = dr_runtime.patient_encounter_id
        JOIN schemes ON true
        WHERE NOT EXISTS (
            SELECT 1 FROM grading_tasks existing
            WHERE existing.patient_encounter_id = dr_runtime.patient_encounter_id
              AND existing.disease_id = schemes.dr_encounter_id
        )
        RETURNING id
    ),
    glaucoma_encounter_tasks AS (
        INSERT INTO grading_tasks (
            uuid,
            patient_encounter_id,
            encounter_set_package_id,
            disease_id,
            lab_unit_id,
            state,
            grading_target_level,
            task_source,
            created_at,
            updated_at
        )
        SELECT __UUID_EXPR__, glaucoma_runtime.patient_encounter_id, glaucoma_runtime.id,
               schemes.glaucoma_encounter_id, pe.lab_unit_id, 'pending', 'encounter',
               'migration_split', now(), now()
        FROM glaucoma_runtime
        JOIN patient_encounters pe ON pe.id = glaucoma_runtime.patient_encounter_id
        JOIN schemes ON true
        WHERE NOT EXISTS (
            SELECT 1 FROM grading_tasks existing
            WHERE existing.patient_encounter_id = glaucoma_runtime.patient_encounter_id
              AND existing.disease_id = schemes.glaucoma_encounter_id
        )
        RETURNING id
    )
    UPDATE encounter_set_grading_packages pkg
    SET state = 'final',
        metadata_json = COALESCE(pkg.metadata_json, '{}'::jsonb)
            || jsonb_build_object('migration', 'split_to_disease_specific', 'legacy_ungraded', true),
        updated_at = now()
    FROM splittable s
    WHERE pkg.id = s.old_package_id;
    """
    return sql.replace("__UUID_EXPR__", uuid_expr)


def _mark_graded_mixed_runtime_packages_legacy_sql() -> str:
    return """
    WITH mixed_graded AS (
        SELECT pkg.id
        FROM encounter_set_grading_packages pkg
        JOIN grading_tasks task ON task.encounter_set_package_id = pkg.id
        JOIN grades grade ON grade.task_id = task.id
        GROUP BY pkg.id
        HAVING COUNT(DISTINCT task.disease_id) > 1
    )
    UPDATE encounter_set_grading_packages pkg
    SET grading_mode = 'unified',
        metadata_json = COALESCE(pkg.metadata_json, '{}'::jsonb)
            || jsonb_build_object('grading_mode', 'legacy_unified_mixed'),
        updated_at = now()
    FROM mixed_graded
    WHERE pkg.id = mixed_graded.id;
    """
