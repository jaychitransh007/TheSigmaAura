-- Extend source_channel check constraint on the five observability /
-- log tables that were created with the legacy ('web', 'whatsapp')
-- allowlist. The vibe_storefront channel was introduced for the
-- Shopify-app shell (Vibe) but the constraints were never updated,
-- so every Vibe turn that tries to write a row to any of these
-- tables fails the check and the engine logs a SupabaseError 400
-- (visible in fly logs as "Failed to persist dependency validation
-- turn event"). The HTTP response to the customer still succeeds —
-- the engine catches the error — but the telemetry never lands.
--
-- Caught while debugging the customer's try-on failure on turn
-- 8ab76572; alongside the orchestrator's "Try-on generation failed"
-- (which is a separate ephemeral-storage issue) the engine also
-- couldn't persist the dependency_validation_events row, masking
-- the turn from the observability tables that drive ops alerts.

-- Each ALTER is guarded by a table-existence check. user_sentiment_history
-- has a CREATE migration in the repo (20260319120000) but never landed on
-- Aura-Staging, which aborts the whole transaction without the guard.
-- Other environments may also be missing one or more of these tables; this
-- shape lets the migration succeed everywhere and is a no-op where the
-- table doesn't exist.

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_tables
    WHERE schemaname = 'public' AND tablename = 'confidence_history'
  ) THEN
    ALTER TABLE confidence_history
      DROP CONSTRAINT IF EXISTS confidence_history_source_channel_check;
    ALTER TABLE confidence_history
      ADD CONSTRAINT confidence_history_source_channel_check
      CHECK (source_channel IN ('web', 'whatsapp', 'vibe_storefront'));
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_tables
    WHERE schemaname = 'public' AND tablename = 'policy_event_log'
  ) THEN
    ALTER TABLE policy_event_log
      DROP CONSTRAINT IF EXISTS policy_event_log_source_channel_check;
    ALTER TABLE policy_event_log
      ADD CONSTRAINT policy_event_log_source_channel_check
      CHECK (source_channel IN ('web', 'whatsapp', 'vibe_storefront'));
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_tables
    WHERE schemaname = 'public' AND tablename = 'dependency_validation_events'
  ) THEN
    ALTER TABLE dependency_validation_events
      DROP CONSTRAINT IF EXISTS dependency_validation_events_source_channel_check;
    ALTER TABLE dependency_validation_events
      ADD CONSTRAINT dependency_validation_events_source_channel_check
      CHECK (source_channel IN ('web', 'whatsapp', 'vibe_storefront'));
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_tables
    WHERE schemaname = 'public' AND tablename = 'catalog_interaction_history'
  ) THEN
    ALTER TABLE catalog_interaction_history
      DROP CONSTRAINT IF EXISTS catalog_interaction_history_source_channel_check;
    ALTER TABLE catalog_interaction_history
      ADD CONSTRAINT catalog_interaction_history_source_channel_check
      CHECK (source_channel IN ('web', 'whatsapp', 'vibe_storefront'));
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_tables
    WHERE schemaname = 'public' AND tablename = 'user_sentiment_history'
  ) THEN
    ALTER TABLE user_sentiment_history
      DROP CONSTRAINT IF EXISTS user_sentiment_history_source_channel_check;
    ALTER TABLE user_sentiment_history
      ADD CONSTRAINT user_sentiment_history_source_channel_check
      CHECK (source_channel IN ('web', 'whatsapp', 'vibe_storefront'));
  END IF;
END $$;
