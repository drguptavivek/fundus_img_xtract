-- Add generic encounter verification columns to patient_encounters

-- SQLite syntax
ALTER TABLE patient_encounters ADD COLUMN encounter_verified_status TEXT;
ALTER TABLE patient_encounters ADD COLUMN encounter_verified_by TEXT;
ALTER TABLE patient_encounters ADD COLUMN encounter_verified_at TIMESTAMP;

-- PostgreSQL syntax (if using Postgres instead of SQLite)
-- ALTER TABLE patient_encounters
--   ADD COLUMN encounter_verified_status VARCHAR(32),
--   ADD COLUMN encounter_verified_by VARCHAR(150),
--   ADD COLUMN encounter_verified_at TIMESTAMPTZ;

-- After running the migration, consider backfilling encounter_verified_status
-- for encounters that are already DR verified:
-- UPDATE patient_encounters
-- SET encounter_verified_status = 'verified',
--     encounter_verified_by = dr_verified_by,
--     encounter_verified_at = dr_verified_at
-- WHERE dr_verified_status = 'verified' AND encounter_verified_status IS NULL;
