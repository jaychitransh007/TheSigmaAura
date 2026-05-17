-- Extend source_channel check constraint on the observability / log
-- tables that were created with the legacy ('web', 'whatsapp')
-- allowlist. The vibe_storefront channel was introduced for the
-- Shopify-app shell (Vibe) but the constraints were never updated,
-- so every Vibe turn that tries to write a row to any of these
-- tables fails the check and the engine logs a SupabaseError 400
-- ("Failed to persist dependency validation turn event" in fly logs).
--
-- Loop body uses dynamic SQL (EXECUTE format) so the table list is a
-- single array of names; adding another table later means one extra
-- entry in the array, not another 5-line ALTER block.
-- Each table guarded by IF EXISTS — user_sentiment_history's CREATE
-- migration (20260319120000) was never applied to Aura-Staging, and
-- a bare ALTER on a missing table aborts the whole transaction.
-- DROP + ADD are run as two ALTER statements rather than merged
-- (Postgres ALTER TABLE accepts multiple sub-clauses, but DROP
-- CONSTRAINT IF EXISTS + ADD CONSTRAINT in one statement raises
-- a syntax warning on older PG versions; split form is portable).

DO $$
DECLARE
  tbl text;
BEGIN
  FOREACH tbl IN ARRAY ARRAY[
    'confidence_history',
    'policy_event_log',
    'dependency_validation_events',
    'catalog_interaction_history',
    'user_sentiment_history'
  ]
  LOOP
    IF EXISTS (
      SELECT 1 FROM pg_tables
      WHERE schemaname = 'public' AND tablename = tbl
    ) THEN
      EXECUTE format(
        'ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I',
        tbl,
        tbl || '_source_channel_check'
      );
      EXECUTE format(
        'ALTER TABLE %I ADD CONSTRAINT %I CHECK (source_channel IN (''web'', ''whatsapp'', ''vibe_storefront''))',
        tbl,
        tbl || '_source_channel_check'
      );
    END IF;
  END LOOP;
END $$;
