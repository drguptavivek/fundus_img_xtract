from __future__ import annotations

import os

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text


REVISION = "6f2d8a9c1b47"
PREVIOUS = "0b9488e2a0f6"


def _config(test_engine) -> Config:
    database_url = test_engine.url.render_as_string(hide_password=False)
    config = Config()
    config.set_main_option("sqlalchemy.url", database_url)
    config.set_main_option("script_location", "migrations")
    os.environ["DATABASE_URL"] = database_url
    return config


def test_madhunetra_migration_upgrade_and_downgrade(test_engine):
    config = _config(test_engine)
    tables = {
        "project_encounter_ai_workflows",
        "encounter_ai_output_targets",
        "encounter_ai_inference_runs",
        "encounter_ai_image_results",
        "encounter_ai_target_results",
    }
    try:
        with test_engine.connect() as conn:
            assert tables.issubset(set(inspect(conn).get_table_names()))
            provider = conn.execute(text("SELECT provider FROM ai_model_integrations WHERE provider='wai_dr_dme'" )).scalar_one()
            assert provider == "wai_dr_dme"

        command.downgrade(config, PREVIOUS)
        with test_engine.connect() as conn:
            assert not tables.intersection(inspect(conn).get_table_names())
            columns = {row["name"] for row in inspect(conn).get_columns("ai_model_integrations")}
            assert "access_token_encrypted" not in columns
    finally:
        command.upgrade(config, REVISION)

    with test_engine.connect() as conn:
        assert tables.issubset(set(inspect(conn).get_table_names()))
