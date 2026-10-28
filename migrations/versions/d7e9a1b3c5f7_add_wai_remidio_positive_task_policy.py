"""add WAI or Remidio positive task policy

Revision ID: d7e9a1b3c5f7
Revises: c4d6f8a0b2e4
"""

from alembic import op


revision = "d7e9a1b3c5f7"
down_revision = "c4d6f8a0b2e4"
branch_labels = None
depends_on = None

POLICY = "wai_or_remidio_positive_plus_negative_controls"


def upgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("ALTER TABLE grading_tasks DROP CONSTRAINT IF EXISTS ck_task_state_valid")
    conn.exec_driver_sql(
        "ALTER TABLE grading_tasks ADD CONSTRAINT ck_task_state_valid "
        "CHECK (state IN ('ai_pending','pending','resident_done','resident2_done','arbitration','final'))"
    )
    conn.exec_driver_sql(
        "ALTER TABLE upload_profile_est_package_image_schemes "
        "DROP CONSTRAINT IF EXISTS ck_up_est_pkg_image_auto_create_policy"
    )
    conn.exec_driver_sql(
        "ALTER TABLE upload_profile_est_package_image_schemes "
        "ADD CONSTRAINT ck_up_est_pkg_image_auto_create_policy CHECK (auto_create_policy IN "
        "('never','always','remidio_dr_report_present','remidio_amd_report_present',"
        "'remidio_glaucoma_report_present','positive_plus_negative_controls',"
        f"'{POLICY}'))"
    )
    conn.exec_driver_sql(
        "ALTER TABLE upload_profile_est_package_image_schemes "
        "DROP CONSTRAINT IF EXISTS ck_up_est_pkg_image_negative_controls_per_positive"
    )
    conn.exec_driver_sql(
        "ALTER TABLE upload_profile_est_package_image_schemes "
        "ADD CONSTRAINT ck_up_est_pkg_image_negative_controls_per_positive CHECK ("
        f"(auto_create_policy IN ('positive_plus_negative_controls','{POLICY}') "
        "AND negative_controls_per_positive BETWEEN 1 AND 10) OR "
        f"(auto_create_policy NOT IN ('positive_plus_negative_controls','{POLICY}') "
        "AND negative_controls_per_positive BETWEEN 0 AND 10))"
    )
    # Project 2 currently uses upload profile 10. Scope the data migration by both
    # profile and Glaucoma disease so unrelated package schemes are untouched.
    conn.exec_driver_sql(
        """
        UPDATE upload_profile_est_package_image_schemes AS image_scheme
        SET auto_create_policy = %s, negative_controls_per_positive = 1
        FROM upload_profile_est_grading_packages AS package,
             upload_profile_encounter_set_types AS profile_type,
             diseases AS disease
        WHERE image_scheme.package_id = package.id
          AND package.upload_profile_encounter_set_type_id = profile_type.id
          AND image_scheme.disease_id = disease.id
          AND profile_type.upload_profile_id = 10
          AND lower(disease.name) = 'glaucoma'
        """,
        (POLICY,),
    )


def downgrade():
    conn = op.get_bind()
    conn.exec_driver_sql(
        "UPDATE upload_profile_est_package_image_schemes "
        "SET auto_create_policy = 'always', negative_controls_per_positive = 0 "
        "WHERE auto_create_policy = %s",
        (POLICY,),
    )
    conn.exec_driver_sql("UPDATE grading_tasks SET state = 'pending' WHERE state = 'ai_pending'")
    conn.exec_driver_sql("ALTER TABLE grading_tasks DROP CONSTRAINT IF EXISTS ck_task_state_valid")
    conn.exec_driver_sql(
        "ALTER TABLE grading_tasks ADD CONSTRAINT ck_task_state_valid "
        "CHECK (state IN ('pending','resident_done','resident2_done','arbitration','final'))"
    )
    conn.exec_driver_sql(
        "ALTER TABLE upload_profile_est_package_image_schemes "
        "DROP CONSTRAINT IF EXISTS ck_up_est_pkg_image_negative_controls_per_positive"
    )
    conn.exec_driver_sql(
        "ALTER TABLE upload_profile_est_package_image_schemes "
        "ADD CONSTRAINT ck_up_est_pkg_image_negative_controls_per_positive CHECK ("
        "(auto_create_policy = 'positive_plus_negative_controls' AND negative_controls_per_positive BETWEEN 1 AND 10) OR "
        "(auto_create_policy <> 'positive_plus_negative_controls' AND negative_controls_per_positive BETWEEN 0 AND 10))"
    )
    conn.exec_driver_sql(
        "ALTER TABLE upload_profile_est_package_image_schemes "
        "DROP CONSTRAINT IF EXISTS ck_up_est_pkg_image_auto_create_policy"
    )
    conn.exec_driver_sql(
        "ALTER TABLE upload_profile_est_package_image_schemes "
        "ADD CONSTRAINT ck_up_est_pkg_image_auto_create_policy CHECK (auto_create_policy IN "
        "('never','always','remidio_dr_report_present','remidio_amd_report_present',"
        "'remidio_glaucoma_report_present','positive_plus_negative_controls'))"
    )
