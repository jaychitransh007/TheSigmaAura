-- Step 2a of the canonical sequence (PR #233): add 12 new attribute
-- axes to ``catalog_enriched`` so the upcoming vision re-enrichment
-- can populate them.
--
-- Source: stylist reviews (May 2026 Phase 4.2 deliverables) — bodyframe,
-- occasion, weather, palette. Each axis has a corresponding entry in
-- ``modules/style_engine/configs/config/garment_attributes.json``.
--
-- Pattern follows the existing table: <name> text + <name>_confidence
-- double precision, both nullable. Re-enrichment will populate; rows
-- enriched before this migration retain NULL until re-run.
--
-- This migration is purely additive. No existing column is modified
-- or dropped. The FabricTexture decomposition (moving sheen / metallic
-- / matte values out of FabricTexture into the new SurfaceFinish axis)
-- is a separate cleanup once the held YAML patches land — for now,
-- both axes coexist; vision-enrichment may produce values for both.

alter table public.catalog_enriched
  -- Bodyframe additions (proposed 2026-05-09)
  add column if not exists "ShoulderExposure" text null,
  add column if not exists "ShoulderExposure_confidence" double precision null,
  add column if not exists "SleeveVolume" text null,
  add column if not exists "SleeveVolume_confidence" double precision null,
  add column if not exists "BlouseLength" text null,
  add column if not exists "BlouseLength_confidence" double precision null,
  -- Occasion additions
  add column if not exists "BorderContrast" text null,
  add column if not exists "BorderContrast_confidence" double precision null,
  add column if not exists "FabricTransparency" text null,
  add column if not exists "FabricTransparency_confidence" double precision null,
  -- Weather + palette additions: optical-finish decomposition
  -- (FabricTexture currently overloads tactile + optical + construction;
  -- SurfaceFinish carves out the optical sub-axis, including the
  -- mirror-shine / antique / brushed metallic distinction palette
  -- review flagged for muted-palette retrieval).
  add column if not exists "SurfaceFinish" text null,
  add column if not exists "SurfaceFinish_confidence" double precision null,
  add column if not exists "LayeringVisibility" text null,
  add column if not exists "LayeringVisibility_confidence" double precision null,
  -- Weather performance axes (Indian-monsoon-driven; partly visible
  -- from images, partly inferable from FabricTexture / FabricWeight).
  add column if not exists "BreathabilityLevel" text null,
  add column if not exists "BreathabilityLevel_confidence" double precision null,
  add column if not exists "DryTime" text null,
  add column if not exists "DryTime_confidence" double precision null,
  add column if not exists "WaterResistance" text null,
  add column if not exists "WaterResistance_confidence" double precision null,
  add column if not exists "ThermalInsulation" text null,
  add column if not exists "ThermalInsulation_confidence" double precision null,
  add column if not exists "WrinkleResistance" text null,
  add column if not exists "WrinkleResistance_confidence" double precision null;

-- No new indexes — these attributes are filtered server-side via the
-- existing pgvector + jsonb infrastructure, not by direct column scan.
-- Add indexes per-attribute only if a specific query pattern justifies it.
