-- Path B schema rationalization (2026-05-09 stylist follow-up).
--
-- Stylist's architectural critique on the post-Step-2a schema (PR #237):
-- - Vision systems should predict only what is reliably visible from
--   images. The 5 weather performance axes added in Step 2a
--   (BreathabilityLevel, DryTime, WaterResistance, ThermalInsulation,
--   WrinkleResistance) require fabric-composition / spec data that
--   the vision model cannot reliably extract. Push them into a
--   separate merchant-data enrichment path later, not vision.
--
-- - Shape behavior is the missing primitive in the schema. Adopt the 4
--   endorsed ShapeArchitecture axes (VolumePlacement, AsymmetryType,
--   AttachmentStructure, MotionBehavior). Defer the 4 lower-ROI axes
--   (ProjectionType, StructuralRhythm, EdgeGeometry, VolumeIntensity)
--   to Phase 2 ontology work.
--
-- This migration is the database side of the change. The canonical
-- schema (garment_attributes.json) and vision-enrichment prompt are
-- updated in the same PR.
--
-- Step 2b (vision re-enrichment) will run on this rationalised schema —
-- no rows have been populated for the 5 dropped columns since the
-- previous migration shipped after Step 2b was deferred to Path B.
-- Therefore DROPPING is safe with no data loss.

-- ─────────────────────────────────────────────────────────────────────
-- Drop the 5 weather performance columns added in
-- 20260515000000_catalog_enriched_v3_axes.sql.
-- ─────────────────────────────────────────────────────────────────────
alter table public.catalog_enriched
  drop column if exists "BreathabilityLevel",
  drop column if exists "BreathabilityLevel_confidence",
  drop column if exists "DryTime",
  drop column if exists "DryTime_confidence",
  drop column if exists "WaterResistance",
  drop column if exists "WaterResistance_confidence",
  drop column if exists "ThermalInsulation",
  drop column if exists "ThermalInsulation_confidence",
  drop column if exists "WrinkleResistance",
  drop column if exists "WrinkleResistance_confidence";

-- ─────────────────────────────────────────────────────────────────────
-- Add the 4 endorsed ShapeArchitecture axes.
-- Stylist intent per axis — see vision-enrichment prompt
-- (system_prompt.txt) for the full disambiguation rules.
-- ─────────────────────────────────────────────────────────────────────
alter table public.catalog_enriched
  -- VolumePlacement: where on the garment volume concentrates
  -- (puff sleeve = sleeve; peplum = waist; mermaid flare = hem).
  add column if not exists "VolumePlacement" text null,
  add column if not exists "VolumePlacement_confidence" double precision null,
  -- AsymmetryType: how the garment breaks symmetry (one-shoulder,
  -- high-low hem, side-draped saree, asymmetric closure).
  add column if not exists "AsymmetryType" text null,
  add column if not exists "AsymmetryType_confidence" double precision null,
  -- AttachmentStructure: extra structural elements beyond the main
  -- garment (attached dupatta / cape / drape / sash / panel).
  -- Solves "some part hanging which isn't a dupatta" problem for
  -- couture and Indo-Western styling.
  add column if not exists "AttachmentStructure" text null,
  add column if not exists "AttachmentStructure_confidence" double precision null,
  -- MotionBehavior: how the garment behaves when worn (static / fluid
  -- / swish / flutter / trail / bounce / dramatic). Critical for
  -- sangeet, dance contexts, and reel-friendly Gen Z styling.
  add column if not exists "MotionBehavior" text null,
  add column if not exists "MotionBehavior_confidence" double precision null;

-- No new indexes — same rationale as the previous migration.
-- These axes filter via the existing pgvector + jsonb infrastructure.
