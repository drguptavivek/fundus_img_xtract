"""Optimize the application glaucoma listing and refresh it every minute.

Revision ID: e8f1a2b3c4d5
Revises: d7e9a1b3c5f7
"""
from hashlib import md5

from alembic import op
from sqlalchemy import text

from utils.mvw_image_listing_v2 import _build_mv_sql, _create_indexes_sql

revision = 'e8f1a2b3c4d5'
down_revision = 'd7e9a1b3c5f7'
branch_labels = None
depends_on = None

VIEW = 'mvw_image_listing_glaucoma_1_v2'
SHADOW = VIEW + '_rebuild'
SCHEDULE = 'Glaucoma Image Listing Refresh (60s)'
TASK = 'celery_tasks.tasks.mv_tasks.refresh_glaucoma_listing_task'


def _rebuild(*, optimized):
    conn = op.get_bind()
    quote = conn.dialect.identifier_preparer.quote
    schema = conn.execute(text("SELECT current_schema()")).scalar_one()
    # Build before locking the existing view. Never cascade dependent objects.
    conn.execute(text("SET LOCAL lock_timeout='3s'"))
    conn.execute(text("SET LOCAL statement_timeout='300s'"))
    name = conn.execute(text('SELECT name FROM diseases WHERE id=1')).scalar()
    if name is None or name.lower() != 'glaucoma':
        raise RuntimeError('Expected glaucoma disease id=1')
    existing = conn.execute(text(
        "SELECT pg_get_userbyid(c.relowner) AS owner, obj_description(c.oid) AS comment "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname=current_schema() AND c.relname=:name AND c.relkind='m'"
    ), {'name': VIEW}).mappings().first()
    indexes = conn.execute(text(
        'SELECT indexname,indexdef FROM pg_indexes WHERE schemaname=current_schema() AND tablename=:name'
    ), {'name': VIEW}).all()
    grants = conn.execute(text(
        "SELECT CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS grantee, "
        "a.privilege_type,a.is_grantable FROM pg_class c "
        "JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL aclexplode(c.relacl) a "
        "WHERE n.nspname=current_schema() AND c.relname=:name"
    ), {'name': VIEW}).all()
    conn.execute(text(f'DROP MATERIALIZED VIEW IF EXISTS {SHADOW}'))
    conn.execute(text(_build_mv_sql(SHADOW, 1, name, include_encounter_set_images=True,
                                    optimize_task_join=optimized)))
    if indexes:
        for index_name, definition in indexes:
            shadow_index = 'gopt_' + md5(index_name.encode()).hexdigest()
            definition = definition.replace(quote(index_name), quote(shadow_index), 1)
            definition = definition.replace(f'ON {quote(schema)}.{quote(VIEW)} ', f'ON {quote(schema)}.{quote(SHADOW)} ', 1)
            conn.execute(text(definition))
    else:
        for statement in _create_indexes_sql(SHADOW, include_encounter_set_images=True):
            conn.execute(text(statement))
    conn.execute(text(f'DROP MATERIALIZED VIEW IF EXISTS {VIEW}'))
    conn.execute(text(f'ALTER MATERIALIZED VIEW {SHADOW} RENAME TO {VIEW}'))
    # Restore stable index names after dropping the old indexes.
    for index_name, _ in indexes:
        shadow_index = 'gopt_' + md5(index_name.encode()).hexdigest()
        conn.execute(text(f'ALTER INDEX {quote(shadow_index)} RENAME TO {quote(index_name)}'))
    if existing:
        conn.execute(text(f'ALTER MATERIALIZED VIEW {VIEW} OWNER TO {quote(existing["owner"])}'))
        if existing['comment'] is not None:
            conn.execute(text(f'COMMENT ON MATERIALIZED VIEW {VIEW} IS :comment'),
                         {'comment': existing['comment']})
    for grantee, privilege, grantable in grants:
        if privilege not in {'SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN'}:
            raise RuntimeError('Unexpected relation privilege')
        target = 'PUBLIC' if grantee == 'PUBLIC' else quote(grantee)
        suffix = ' WITH GRANT OPTION' if grantable else ''
        conn.execute(text(f'GRANT {privilege} ON {VIEW} TO {target}{suffix}'))


def upgrade():
    _rebuild(optimized=True)
    op.get_bind().execute(text("""
        INSERT INTO celery_beat_schedules
            (name,task_name,queue,enabled,schedule_type,interval_seconds,created_at,updated_at,last_run_at)
        VALUES (:name,:task,'maintenance',true,'interval',60,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP - INTERVAL '60 seconds')
        ON CONFLICT (name) DO UPDATE SET task_name=EXCLUDED.task_name,queue='maintenance',
            enabled=true,schedule_type='interval',interval_seconds=60,updated_at=CURRENT_TIMESTAMP,
            last_run_at=COALESCE(celery_beat_schedules.last_run_at,EXCLUDED.last_run_at)
    """), {'name': SCHEDULE, 'task': TASK})


def downgrade():
    op.get_bind().execute(text('DELETE FROM celery_beat_schedules WHERE name=:name'), {'name': SCHEDULE})
    _rebuild(optimized=False)
