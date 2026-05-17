-- Extend onboarding_profile_snapshots.snapshot_reason check constraint
-- to allow field_update and acquisition_updated.
--
-- These reason values are written by user/repository.py's
-- update_partial_fields() (field_update — every incremental profile
-- save) and update_acquisition_metadata() (acquisition_updated).
-- They've been written in code since PR 57aab02 (Apr 11 2026 — the
-- incremental profile save / resume flow) but the original constraint
-- from 20260310153000_onboarding_analysis_history_snapshots.sql was
-- never extended to allow them. The result: every partial profile
-- patch on the Vibe app's in-chat onboarding flow returns 502 because
-- the snapshot insert fails the check, even though the underlying
-- profile PATCH succeeded.
--
-- Caught while debugging the customer's DOB/Gender card submit
-- returning HTTP 500 on the Vibe storefront — turn_id n/a, profile
-- patch was 200 but the snapshot insert was 400.

ALTER TABLE onboarding_profile_snapshots
  DROP CONSTRAINT IF EXISTS onboarding_profile_snapshots_snapshot_reason_check;

ALTER TABLE onboarding_profile_snapshots
  ADD CONSTRAINT onboarding_profile_snapshots_snapshot_reason_check
  CHECK (snapshot_reason IN (
    'created',
    'otp_verified',
    'profile_saved',
    'image_uploaded',
    'onboarding_completed',
    'state_change',
    'field_update',
    'acquisition_updated'
  ));
