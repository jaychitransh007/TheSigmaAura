-- Make snapshot tables self-sufficient and remove redundant analysis tables.

ALTER TABLE IF EXISTS user_analysis_snapshots
  ADD COLUMN IF NOT EXISTS started_at timestamptz,
  ADD COLUMN IF NOT EXISTS completed_at timestamptz,
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

ALTER TABLE IF EXISTS user_interpretation_snapshots
  ADD COLUMN IF NOT EXISTS analysis_snapshot_id uuid,
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

DO $$
DECLARE
  rec record;
BEGIN
  FOR rec IN
    SELECT rel.relname AS table_name, con.conname AS constraint_name
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
    WHERE nsp.nspname = 'public'
      AND rel.relname IN ('user_analysis_snapshots', 'user_interpretation_snapshots')
      AND con.contype = 'f'
  LOOP
    EXECUTE format(
      'ALTER TABLE public.%I DROP CONSTRAINT IF EXISTS %I',
      rec.table_name,
      rec.constraint_name
    );
  END LOOP;
END
$$;

ALTER TABLE IF EXISTS user_analysis_snapshots
  ALTER COLUMN analysis_run_id DROP NOT NULL;

ALTER TABLE IF EXISTS user_interpretation_snapshots
  ALTER COLUMN analysis_run_id DROP NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'user_interpretation_snapshots_analysis_snapshot_id_fkey'
  ) THEN
    ALTER TABLE public.user_interpretation_snapshots
      ADD CONSTRAINT user_interpretation_snapshots_analysis_snapshot_id_fkey
      FOREIGN KEY (analysis_snapshot_id) REFERENCES public.user_analysis_snapshots(id) ON DELETE CASCADE;
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_user_interpretation_snapshots_analysis_snapshot
  ON user_interpretation_snapshots(analysis_snapshot_id);

DROP TABLE IF EXISTS user_analysis_attributes;
DROP TABLE IF EXISTS user_derived_interpretations;
DROP TABLE IF EXISTS user_analysis_runs;
