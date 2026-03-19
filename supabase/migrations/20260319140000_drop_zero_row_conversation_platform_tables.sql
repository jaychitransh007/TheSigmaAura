-- Cleanup orphaned zero-row tables from the removed conversation_platform runtime.
-- Verified in staging before this migration:
--   media_assets: 0 rows
--   profile_snapshots: 0 rows
--   context_snapshots: 0 rows
--   recommendation_runs: 0 rows
--   recommendation_items: 0 rows
--   checkout_preparations: 0 rows
--   checkout_preparation_items: 0 rows
--   feedback_events.recommendation_run_id: 0 non-null rows

ALTER TABLE feedback_events
  DROP COLUMN IF EXISTS recommendation_run_id;

DROP TABLE IF EXISTS checkout_preparation_items;
DROP TABLE IF EXISTS checkout_preparations;
DROP TABLE IF EXISTS recommendation_items;
DROP TABLE IF EXISTS recommendation_runs;
DROP TABLE IF EXISTS context_snapshots;
DROP TABLE IF EXISTS profile_snapshots;
DROP TABLE IF EXISTS media_assets;
