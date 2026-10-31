-- Benchmark only candidate objects. No source data is mutated.
\timing on
SET statement_timeout = '30s';
SET lock_timeout = '3s';
SELECT refresh_glaucoma_listing_incremental_candidate(ARRAY(SELECT task_id FROM glaucoma_listing_incremental_candidate ORDER BY task_id LIMIT 1));
SELECT refresh_glaucoma_listing_incremental_candidate(ARRAY(SELECT task_id FROM glaucoma_listing_incremental_candidate ORDER BY task_id LIMIT 10));
SELECT refresh_glaucoma_listing_incremental_candidate(ARRAY(SELECT task_id FROM glaucoma_listing_incremental_candidate ORDER BY task_id LIMIT 100));
SELECT refresh_glaucoma_listing_incremental_candidate(ARRAY(SELECT task_id FROM glaucoma_listing_incremental_candidate ORDER BY task_id LIMIT 1000));
-- Fresh full candidate provides the comparison baseline.
REFRESH MATERIALIZED VIEW CONCURRENTLY mvw_image_listing_glaucoma_1_v2_fast_candidate;
SELECT count(*) AS row_differences FROM (
    (SELECT to_jsonb(v) FROM glaucoma_listing_incremental_candidate v
     EXCEPT ALL SELECT to_jsonb(v) FROM mvw_image_listing_glaucoma_1_v2_fast_candidate v)
    UNION ALL
    (SELECT to_jsonb(v) FROM mvw_image_listing_glaucoma_1_v2_fast_candidate v
     EXCEPT ALL SELECT to_jsonb(v) FROM glaucoma_listing_incremental_candidate v)
) differences;
SELECT count(*) AS indexes FROM pg_indexes WHERE tablename='glaucoma_listing_incremental_candidate';
