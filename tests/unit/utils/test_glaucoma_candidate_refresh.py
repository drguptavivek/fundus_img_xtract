from contextlib import contextmanager

from sqlalchemy import text

from analytics.image_listing_projection import service


def test_full_candidate_refresh_updates_adds_and_removes_rows(db_session, monkeypatch):
    db = db_session
    db.execute(text('CREATE SCHEMA candidate_refresh_test'))
    db.execute(text('SET LOCAL search_path=candidate_refresh_test, public'))
    db.execute(text('CREATE TABLE source_tasks(task_id integer PRIMARY KEY, value text)'))
    db.execute(text("INSERT INTO source_tasks VALUES (1,'old'),(2,'deleted')"))
    db.execute(text('CREATE MATERIALIZED VIEW mvw_image_listing_glaucoma_1_v2 AS SELECT * FROM source_tasks'))
    db.execute(text('CREATE UNIQUE INDEX candidate_refresh_task_id ON mvw_image_listing_glaucoma_1_v2(task_id)'))

    @contextmanager
    def scope():
        yield db

    monkeypatch.setattr(service, 'transaction_scope', scope)
    db.execute(text("UPDATE source_tasks SET value='graded/verified' WHERE task_id=1"))
    db.execute(text('DELETE FROM source_tasks WHERE task_id=2'))
    db.execute(text("INSERT INTO source_tasks VALUES (3,'new')"))
    result = service.refresh_glaucoma_listing()
    assert result.refreshed == 1
    assert db.execute(text('SELECT * FROM mvw_image_listing_glaucoma_1_v2 ORDER BY task_id')).all() == [(1,'graded/verified'),(3,'new')]
    db.execute(text('DROP MATERIALIZED VIEW mvw_image_listing_glaucoma_1_v2'))
    assert service.refresh_glaucoma_listing().status == 'not_installed'


def test_glaucoma_migration_upgrade_downgrade_and_reupgrade(db_session):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path('migrations/versions/e8f1a2b3c4d5_optimize_glaucoma_listing_refresh.py')
    spec = importlib.util.spec_from_file_location('glaucoma_refresh_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    db_session.execute(text('CREATE SCHEMA glaucoma_migration_test'))
    db_session.execute(text('SET LOCAL search_path=glaucoma_migration_test, public'))
    operations = Operations(MigrationContext.configure(db_session.connection()))
    with Operations.context(operations.migration_context):
        migration.upgrade()
        definition = db_session.execute(text("SELECT pg_get_viewdef('glaucoma_migration_test.mvw_image_listing_glaucoma_1_v2'::regclass)")).scalar()
        assert 'matched_images' in definition
        assert 'NOT MATERIALIZED' in definition
        assert db_session.execute(text("SELECT last_run_at IS NOT NULL FROM celery_beat_schedules WHERE name=:name"), {'name': migration.SCHEDULE}).scalar()
        assert db_session.execute(text("SELECT interval_seconds FROM celery_beat_schedules WHERE name=:name"), {'name': migration.SCHEDULE}).scalar() == 60
        db_session.execute(text("COMMENT ON MATERIALIZED VIEW mvw_image_listing_glaucoma_1_v2 IS 'retained comment'"))
        migration.downgrade()
        definition = db_session.execute(text("SELECT pg_get_viewdef('glaucoma_migration_test.mvw_image_listing_glaucoma_1_v2'::regclass)")).scalar()
        assert 'matched_images' not in definition
        assert db_session.execute(text("SELECT count(*) FROM celery_beat_schedules WHERE name=:name"), {'name': migration.SCHEDULE}).scalar() == 0
        migration.upgrade()
        assert db_session.execute(text("SELECT obj_description('glaucoma_migration_test.mvw_image_listing_glaucoma_1_v2'::regclass)")).scalar() == 'retained comment'
        assert db_session.execute(text("SELECT count(*) FROM pg_indexes WHERE schemaname='glaucoma_migration_test' AND tablename='mvw_image_listing_glaucoma_1_v2'")).scalar() == 26
        # A repeated upgrade must preserve indexes and the single schedule row.
        migration.upgrade()
        assert db_session.execute(text("SELECT count(*) FROM celery_beat_schedules WHERE name=:name"), {'name': migration.SCHEDULE}).scalar() == 1


def test_all_configured_disease_mvs_rebuild_and_schedule_roundtrip(db_session):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from utils.mvw_image_listing_v2 import _mv_name

    path = Path('migrations/versions/f9a2b3c4d5e6_optimize_all_disease_listings.py')
    spec = importlib.util.spec_from_file_location('all_listing_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    db_session.execute(text('CREATE SCHEMA all_listing_migration_test'))
    db_session.execute(text('SET LOCAL search_path=all_listing_migration_test, public'))
    db_session.execute(text('CREATE TABLE diseases(id integer PRIMARY KEY,name text)'))
    configured = [(1,'Glaucoma'),(2,'DR'),(95,'New Configured Disease')]
    for disease_id, name in configured:
        db_session.execute(text('INSERT INTO diseases VALUES (:id,:name)'), {'id': disease_id,'name': name})
    operations = Operations(MigrationContext.configure(db_session.connection()))
    with Operations.context(operations.migration_context):
        migration.upgrade()
        migration.upgrade()
        for disease_id, name in configured:
            view = _mv_name(name, disease_id)
            definition = db_session.execute(text('SELECT pg_get_viewdef(to_regclass(:name))'), {'name': 'all_listing_migration_test.'+view}).scalar()
            assert 'matched_images' in definition
            assert 'NOT MATERIALIZED' in definition
            assert db_session.execute(text("SELECT count(*) FROM pg_indexes WHERE schemaname='all_listing_migration_test' AND tablename=:view"), {'view': view}).scalar() == 26
        assert db_session.execute(text('SELECT interval_seconds FROM celery_beat_schedules WHERE name=:name'), {'name': migration.SCHEDULE}).scalar() == 300
        assert db_session.execute(text("SELECT count(*) FROM celery_beat_schedules WHERE name IN ('Glaucoma Image Listing Refresh (60s)','Image Listing V2 Refresh (60m)')")).scalar() == 0
        migration.downgrade()
        for disease_id, name in configured:
            definition = db_session.execute(text('SELECT pg_get_viewdef(to_regclass(:name))'), {'name': 'all_listing_migration_test.'+_mv_name(name,disease_id)}).scalar()
            assert ('matched_images' in definition) == (disease_id == 1)
        assert db_session.execute(text("SELECT interval_seconds FROM celery_beat_schedules WHERE name='Image Listing V2 Refresh (60m)'")).scalar() == 3600
        migration.upgrade()
        assert db_session.execute(text('SELECT count(*) FROM celery_beat_schedules WHERE name=:name'), {'name': migration.SCHEDULE}).scalar() == 1
