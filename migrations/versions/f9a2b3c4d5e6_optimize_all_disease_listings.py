"""Rebuild all configured disease listings once and refresh every five minutes.

Revision ID: f9a2b3c4d5e6
Revises: e8f1a2b3c4d5
"""
from hashlib import md5

from alembic import op
from sqlalchemy import text

from utils.mvw_image_listing_v2 import _build_mv_sql, _create_indexes_sql, _index_name, _mv_name

revision = 'f9a2b3c4d5e6'
down_revision = 'e8f1a2b3c4d5'
branch_labels = None
depends_on = None

def _rebuild(disease_id, name, *, optimized):
    view = _mv_name(name, disease_id)
    shadow = _index_name(view, "rebuild")
    conn = op.get_bind()
    quote = conn.dialect.identifier_preparer.quote
    schema = conn.execute(text("SELECT current_schema()")).scalar_one()
    # Build before locking the existing view. Never cascade dependent objects.
    conn.execute(text("SET LOCAL lock_timeout='3s'"))
    conn.execute(text("SET LOCAL statement_timeout='300s'"))
    existing = conn.execute(text(
        "SELECT pg_get_userbyid(c.relowner) AS owner, obj_description(c.oid) AS comment "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname=current_schema() AND c.relname=:name AND c.relkind='m'"
    ), {'name': view}).mappings().first()
    indexes = conn.execute(text(
        'SELECT indexname,indexdef FROM pg_indexes WHERE schemaname=current_schema() AND tablename=:name'
    ), {'name': view}).all()
    grants = conn.execute(text(
        "SELECT CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS grantee, "
        "a.privilege_type,a.is_grantable FROM pg_class c "
        "JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL aclexplode(c.relacl) a "
        "WHERE n.nspname=current_schema() AND c.relname=:name"
    ), {'name': view}).all()
    conn.execute(text(f'DROP MATERIALIZED VIEW IF EXISTS {shadow}'))
    conn.execute(text(_build_mv_sql(shadow, disease_id, name, include_encounter_set_images=True,
                                    optimize_task_join=optimized)))
    if indexes:
        for index_name, definition in indexes:
            shadow_index = 'gopt_' + md5(index_name.encode()).hexdigest()
            definition = definition.replace(quote(index_name), quote(shadow_index), 1)
            definition = definition.replace(f'ON {quote(schema)}.{quote(view)} ', f'ON {quote(schema)}.{quote(shadow)} ', 1)
            conn.execute(text(definition))
    else:
        for statement in _create_indexes_sql(shadow, include_encounter_set_images=True):
            conn.execute(text(statement))
    conn.execute(text(f'DROP MATERIALIZED VIEW IF EXISTS {view}'))
    conn.execute(text(f'ALTER MATERIALIZED VIEW {shadow} RENAME TO {view}'))
    # Restore stable index names after dropping the old indexes.
    for index_name, _ in indexes:
        shadow_index = 'gopt_' + md5(index_name.encode()).hexdigest()
        conn.execute(text(f'ALTER INDEX {quote(shadow_index)} RENAME TO {quote(index_name)}'))
    if existing:
        conn.execute(text(f'ALTER MATERIALIZED VIEW {view} OWNER TO {quote(existing["owner"])}'))
        if existing['comment'] is not None:
            conn.execute(text(f'COMMENT ON MATERIALIZED VIEW {view} IS :comment'),
                         {'comment': existing['comment']})
    for grantee, privilege, grantable in grants:
        if privilege not in {'SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN'}:
            raise RuntimeError('Unexpected relation privilege')
        target = 'PUBLIC' if grantee == 'PUBLIC' else quote(grantee)
        suffix = ' WITH GRANT OPTION' if grantable else ''
        conn.execute(text(f'GRANT {privilege} ON {view} TO {target}{suffix}'))


def _rebuild_all(*, upgrade):
    diseases = op.get_bind().execute(text('SELECT id,name FROM diseases ORDER BY id')).all()
    for disease_id, name in diseases:
        # The preceding revision already optimized glaucoma.
        _rebuild(disease_id, name, optimized=upgrade or disease_id == 1)


def _schedule(name, task, seconds):
    op.get_bind().execute(text("""
        INSERT INTO celery_beat_schedules
            (name,task_name,queue,enabled,schedule_type,interval_seconds,
             created_at,updated_at,last_run_at)
        VALUES (:name,:task,'maintenance',true,'interval',:seconds,
                CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
        ON CONFLICT (name) DO UPDATE SET task_name=EXCLUDED.task_name,
            queue='maintenance',enabled=true,schedule_type='interval',
            interval_seconds=EXCLUDED.interval_seconds,updated_at=CURRENT_TIMESTAMP,
            last_run_at=COALESCE(celery_beat_schedules.last_run_at,EXCLUDED.last_run_at)
    """), {'name': name, 'task': task, 'seconds': seconds})


TASK = 'celery_tasks.tasks.mv_tasks.refresh_image_listing_v2_task'
GLAUCOMA_TASK = 'celery_tasks.tasks.mv_tasks.refresh_glaucoma_listing_task'
SCHEDULE = 'Image Listing V2 Refresh (5m)'


def upgrade():
    _rebuild_all(upgrade=True)
    _schedule(SCHEDULE, TASK, 300)
    op.get_bind().execute(text("DELETE FROM celery_beat_schedules WHERE "
        "(task_name=:task AND name='Image Listing V2 Refresh (60m)') OR "
        "(task_name=:glaucoma AND name='Glaucoma Image Listing Refresh (60s)')"),
        {'task': TASK, 'glaucoma': GLAUCOMA_TASK})


def downgrade():
    _rebuild_all(upgrade=False)
    op.get_bind().execute(text('DELETE FROM celery_beat_schedules WHERE name=:name'), {'name': SCHEDULE})
    _schedule('Image Listing V2 Refresh (60m)', TASK, 3600)
    _schedule('Glaucoma Image Listing Refresh (60s)', GLAUCOMA_TASK, 60)
