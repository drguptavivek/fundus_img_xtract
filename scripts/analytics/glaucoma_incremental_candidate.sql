-- Isolated prototype. Run with psql -v ON_ERROR_STOP=1.
-- Existing application MVs and source tables are never modified.
-- Caller supplies ALL affected task IDs, including deleted/moved tasks.
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '30s';
CREATE TABLE IF NOT EXISTS glaucoma_listing_incremental_candidate AS
    TABLE mvw_image_listing_glaucoma_1_v2_fast_candidate;
CREATE UNIQUE INDEX IF NOT EXISTS glaucoma_listing_incremental_candidate_task_id
    ON glaucoma_listing_incremental_candidate(task_id);

-- Retain the source candidate's read indexes for a fair benchmark.
DO $$
DECLARE idx record;
BEGIN
    FOR idx IN SELECT indexname, indexdef FROM pg_indexes
        WHERE schemaname = current_schema()
        AND tablename = 'mvw_image_listing_glaucoma_1_v2_fast_candidate'
        AND indexdef NOT LIKE 'CREATE UNIQUE INDEX%'
    LOOP
        EXECUTE replace(
            replace(replace(idx.indexdef, idx.indexname,
                'glaucoma_incremental_' || md5(idx.indexname)),
                'CREATE INDEX ', 'CREATE INDEX IF NOT EXISTS '),
            'mvw_image_listing_glaucoma_1_v2_fast_candidate',
            'glaucoma_listing_incremental_candidate');
    END LOOP;
END $$;

CREATE OR REPLACE FUNCTION refresh_glaucoma_listing_incremental_candidate(task_ids integer[])
RETURNS integer LANGUAGE plpgsql AS $$
DECLARE
    definition text;
    marker constant text := 'WHERE (t.disease_id = 1)';
    inserted integer;
BEGIN
    IF task_ids IS NULL OR cardinality(task_ids) = 0 THEN
        RETURN 0;
    END IF;
    IF cardinality(task_ids) > 1000 OR array_position(task_ids, NULL) IS NOT NULL THEN
        RAISE EXCEPTION 'Supply 1..1000 non-null affected task IDs';
    END IF;
    -- Serialize candidate writers; readers see the old or committed new batch.
    PERFORM pg_advisory_xact_lock(hashtextextended(
        current_schema() || '.glaucoma_listing_incremental_candidate', 0));
    definition := pg_get_viewdef('mvw_image_listing_glaucoma_1_v2_fast_candidate'::regclass, false);
    IF (length(definition) - length(replace(definition, marker, ''))) / length(marker) <> 1 THEN
        RAISE EXCEPTION 'Unexpected source definition; refusing unfiltered refresh';
    END IF;
    definition := replace(definition, marker,
        'WHERE (t.disease_id = 1) AND t.id = ANY($1)');
    definition := rtrim(rtrim(definition), ';');
    DELETE FROM glaucoma_listing_incremental_candidate WHERE task_id = ANY(task_ids);
    EXECUTE 'INSERT INTO glaucoma_listing_incremental_candidate ' || definition USING task_ids;
    GET DIAGNOSTICS inserted = ROW_COUNT;
    RETURN inserted;
END $$;
COMMIT;
