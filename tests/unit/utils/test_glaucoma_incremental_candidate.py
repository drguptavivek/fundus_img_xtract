from pathlib import Path

import pytest
from sqlalchemy import text


@pytest.fixture
def projection(db_session):
    # A private schema prevents collision with application and other test data.
    db_session.execute(text('CREATE SCHEMA incremental_candidate_test'))
    db_session.execute(text('SET LOCAL search_path = incremental_candidate_test, public'))
    db_session.execute(text('CREATE TABLE grading_tasks(id integer PRIMARY KEY, disease_id integer, value text)'))
    db_session.execute(text("INSERT INTO grading_tasks VALUES (1,1,'old'),(2,1,'keep'),(3,2,'other')"))
    db_session.execute(text('CREATE VIEW mvw_image_listing_glaucoma_1_v2_fast_candidate AS SELECT t.id AS task_id, t.value FROM grading_tasks t JOIN grading_tasks other ON other.id=t.id WHERE (t.disease_id = 1)'))
    script = Path('scripts/analytics/glaucoma_incremental_candidate.sql').read_text()
    # The fixture owns the rollback; do not commit its outer transaction.
    script = script.replace('BEGIN;', '', 1).removesuffix('COMMIT;\n')
    db_session.execute(text(script))
    return db_session


def test_incremental_updates_deletes_moves_and_keeps_unaffected_rows(projection):
    db = projection
    db.execute(text("UPDATE grading_tasks SET value='new' WHERE id=1"))
    db.execute(text('DELETE FROM grading_tasks WHERE id=2'))
    db.execute(text("INSERT INTO grading_tasks VALUES (4,1,'added')"))
    assert db.execute(text('SELECT refresh_glaucoma_listing_incremental_candidate(ARRAY[1,2,4,4])')).scalar() == 2
    assert db.execute(text('SELECT * FROM glaucoma_listing_incremental_candidate ORDER BY task_id')).all() == [(1, 'new'), (4, 'added')]
    db.execute(text('UPDATE grading_tasks SET disease_id=2 WHERE id=1'))
    db.execute(text('SELECT refresh_glaucoma_listing_incremental_candidate(ARRAY[1])'))
    assert db.execute(text('SELECT * FROM glaucoma_listing_incremental_candidate')).all() == [(4, 'added')]


def test_incremental_empty_batch_and_invalid_definition_fail_closed(projection):
    db = projection
    assert db.execute(text('SELECT refresh_glaucoma_listing_incremental_candidate(ARRAY[]::integer[])')).scalar() == 0
    db.execute(text('CREATE OR REPLACE VIEW mvw_image_listing_glaucoma_1_v2_fast_candidate AS SELECT t.id AS task_id,t.value FROM grading_tasks t'))
    with pytest.raises(Exception, match='Unexpected source definition'):
        with db.begin_nested():
            db.execute(text('SELECT refresh_glaucoma_listing_incremental_candidate(ARRAY[1])'))
    assert db.execute(text('SELECT count(*) FROM glaucoma_listing_incremental_candidate')).scalar() == 2
