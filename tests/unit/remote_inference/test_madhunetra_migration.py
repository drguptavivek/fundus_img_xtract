from __future__ import annotations

import os
from contextlib import contextmanager
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool


REVISION = "6f2d8a9c1b47"
PREVIOUS = "0b9488e2a0f6"


def _config(test_engine) -> Config:
    database_url = test_engine.url.render_as_string(hide_password=False)
    config = Config()
    config.set_main_option("sqlalchemy.url", database_url)
    config.set_main_option("script_location", "migrations")
    os.environ["DATABASE_URL"] = database_url
    return config


@contextmanager
def _disposable_database(test_engine):
    """Give destructive migration checks a database no other test can use."""
    database_name = f"fundus_migration_{uuid4().hex}"
    admin_engine = create_engine(
        test_engine.url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    migration_engine = None
    try:
        with admin_engine.connect() as conn:
            conn.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
        migration_engine = create_engine(
            test_engine.url.set(database=database_name),
            poolclass=NullPool,
        )
        yield migration_engine
    finally:
        if migration_engine is not None:
            migration_engine.dispose()
        try:
            with admin_engine.connect() as conn:
                conn.exec_driver_sql(
                    f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'
                )
        finally:
            admin_engine.dispose()


def test_madhunetra_migration_upgrade_and_downgrade(test_engine):
    tables = {
        "project_encounter_ai_workflows",
        "encounter_ai_output_targets",
        "encounter_ai_inference_runs",
        "encounter_ai_image_results",
        "encounter_ai_target_results",
    }
    previous_database_url = os.environ.get("DATABASE_URL")
    try:
        with _disposable_database(test_engine) as migration_engine:
            config = _config(migration_engine)
            command.upgrade(config, REVISION)
            with migration_engine.connect() as conn:
                assert tables.issubset(set(inspect(conn).get_table_names()))
                provider = conn.execute(
                    text(
                        "SELECT provider FROM ai_model_integrations "
                        "WHERE provider='wai_dr_dme'"
                    )
                ).scalar_one()
                assert provider == "wai_dr_dme"

            command.downgrade(config, PREVIOUS)
            with migration_engine.connect() as conn:
                assert not tables.intersection(inspect(conn).get_table_names())
                columns = {
                    row["name"]
                    for row in inspect(conn).get_columns("ai_model_integrations")
                }
                assert "access_token_encrypted" not in columns

            command.upgrade(config, REVISION)
            with migration_engine.connect() as conn:
                assert tables.issubset(set(inspect(conn).get_table_names()))
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
